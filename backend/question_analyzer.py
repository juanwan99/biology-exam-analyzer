import json
import re
import base64
import time
import asyncio
from hashlib import sha256
from pathlib import Path
from logger import get_logger
from config import PROMPT_DIR
from llm_client import llm_call, get_last_llm_call_metadata as get_last_call_metadata
from llm_media import media_input_refs, messages_with_media
from metadata_contracts import LLMCallRecord
from vision_context import extract_visual_context

logger = get_logger()

SCORE_SHARE_NORMALIZATION_MAX_DEVIATION = 0.10


def _llm_call_trace(metadata: dict | None = None) -> tuple[str, str, int, dict]:
    metadata = dict(metadata or {})
    try:
        trace = get_last_call_metadata() or {}
    except Exception:
        trace = {}
    provider = trace.get("provider") or "llm_client"
    model = trace.get("model") or "configured_provider_chain"
    fallback_count = int(trace.get("fallback_count") or 0)
    for key in ("provider_errors", "status", "operation", "fact_count", "grounding_score", "model_policy"):
        if trace.get(key) is not None:
            metadata[key] = trace.get(key)
    return provider, model, fallback_count, metadata


def _question_images_to_media_items(question_images: list | None) -> list[dict[str, str]]:
    media_items: list[dict[str, str]] = []
    for img_bytes in question_images or []:
        if not img_bytes:
            continue
        media_items.append({
            "type": "image",
            "base64": base64.b64encode(img_bytes).decode("utf-8"),
        })
    return media_items


def _question_messages(prompt: str, media_items: list | None) -> list[dict]:
    if media_items:
        return messages_with_media(prompt, media_items)
    return [{"role": "user", "content": [{"type": "text", "text": prompt}]}]


class QuestionAnalyzer:
    """LLM 分析器：题目拆分和分析（统一 fallback 客户端）。"""

    def __init__(self):
        self.logger = get_logger()
        self.logger.info("LLM 分析器初始化完成")

    @staticmethod
    def extract_json(text: str) -> str:
        """
        从模型返回中提取纯JSON
        处理可能的Markdown代码块包裹并清理控制字符
        """
        # 移除markdown代码块标记
        text = text.strip()

        # 尝试提取 ```json ... ``` 或 ``` ... ``` 中的内容
        json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_match:
            logger.debug("[JSON提取] 检测到Markdown代码块，已提取")
            text = json_match.group(1).strip()

        # 清理JSON字符串中的控制字符（保留 \n \t \r，但转义其他控制字符）
        # 先尝试解析，如果失败则进行清理
        try:
            # 快速测试是否可以直接解析
            json.loads(text)
            return text
        except json.JSONDecodeError:
            # 需要清理控制字符
            # 替换所有ASCII控制字符（0x00-0x1F），除了合法的转义字符
            cleaned = ''.join(
                char if ord(char) >= 32 or char in '\n\r\t' else ' '
                for char in text
            )
            logger.debug("[JSON提取] 已清理控制字符")
            return cleaned

    @staticmethod
    def _coerce_float(value, mapping: dict = None):
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            raw = value.strip()
            if raw.endswith("%"):
                try:
                    return float(raw[:-1]) / 100
                except ValueError:
                    pass
            try:
                return float(raw)
            except ValueError:
                key = raw.lower()
                if mapping and key in mapping:
                    return mapping[key]
                if mapping and raw in mapping:
                    return mapping[raw]
        return value

    @classmethod
    def _normalize_fine_grained_result(cls, data: dict) -> tuple[dict, list[str]]:
        """Normalize common LLM schema drifts without inventing analysis content."""
        notes = []
        if not isinstance(data, dict):
            return data, notes

        def _first_text(source, keys: tuple[str, ...] = ()) -> str:
            if isinstance(source, str):
                return source.strip()
            if isinstance(source, (list, tuple)):
                for item in source:
                    text = _first_text(item, keys)
                    if text:
                        return text
                return ""
            if isinstance(source, dict):
                for key in keys:
                    value = source.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                    if isinstance(value, (list, tuple, dict)):
                        nested = _first_text(value, keys)
                        if nested:
                            return nested
                    if value not in (None, "", []):
                        return str(value).strip()
            return ""

        def _is_placeholder_knowledge_point(value: str) -> bool:
            text = str(value or "").strip()
            if not text:
                return False
            return bool(
                re.fullmatch(r"(?i)(kp|k|knowledge[_\s-]*point)[_\s-]*\d+", text)
                or re.fullmatch(r"知识点\d+", text)
                or re.fullmatch(r"教材知识点\d+", text)
                or re.fullmatch(r"判断(?:选项)?[A-DＡ-Ｄ](?:项)?(?:正确|错误|正误)?", text)
                or re.fullmatch(r"(?:选项)?[A-DＡ-Ｄ](?:项)?(?:正确|错误|正误)?判断", text)
                or re.fullmatch(r"[A-DＡ-Ｄ]选项(?:正确|错误|正误)?", text)
            )

        def _first_non_placeholder_text(source, keys: tuple[str, ...]) -> str:
            for key in keys:
                text = _first_text(source, (key,))
                if text and not _is_placeholder_knowledge_point(text):
                    return text
            text = _first_text(source, keys)
            return "" if _is_placeholder_knowledge_point(text) else text

        difficulty_label_map = {
            "easy": "简单", "simple": "简单", "low": "简单", "简单": "简单", "低": "简单",
            "medium": "中等", "middle": "中等", "moderate": "中等", "中等": "中等", "中": "中等",
            "一般": "中等", "适中": "中等", "中等偏易": "中等", "较易": "中等", "偏易": "中等",
            "hard": "困难", "difficult": "困难", "high": "困难", "困难": "困难", "高": "困难",
            "较难": "困难", "偏难": "困难", "中等偏难": "困难", "很难": "困难", "高难": "困难", "难": "困难",
        }

        def _difficulty_label_from_units() -> str:
            values = []
            score_map = {
                "easy": 3.0, "simple": 3.0, "low": 3.0, "简单": 3.0, "低": 3.0,
                "medium": 5.5, "middle": 5.5, "moderate": 5.5, "中等": 5.5, "中": 5.5,
                "一般": 5.5, "适中": 5.5, "中等偏易": 4.8, "较易": 4.2, "偏易": 4.5,
                "hard": 8.0, "difficult": 8.0, "high": 8.0, "困难": 8.0, "高": 8.0,
                "较难": 7.5, "偏难": 7.2, "中等偏难": 6.8, "很难": 8.8, "高难": 8.8, "难": 8.0,
            }
            for seu in data.get("scoring_units") or []:
                if not isinstance(seu, dict):
                    continue
                value = cls._coerce_float(seu.get("difficulty_estimate"), score_map)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    values.append(float(value))
            if not values:
                return "中等"
            average = sum(values) / len(values)
            if average <= 4:
                return "简单"
            if average <= 7:
                return "中等"
            return "困难"

        if "answer" in data and not isinstance(data.get("answer"), str):
            data["answer"] = json.dumps(data["answer"], ensure_ascii=False)
            notes.append("answer_object_to_json_string")
        if isinstance(data.get("difficulty"), str):
            raw_difficulty = data["difficulty"].strip()
            normalized_difficulty = difficulty_label_map.get(
                raw_difficulty.lower(),
                difficulty_label_map.get(raw_difficulty),
            )
            if normalized_difficulty and normalized_difficulty != data["difficulty"]:
                data["difficulty"] = normalized_difficulty
                notes.append("difficulty_text_to_label")
        elif isinstance(data.get("difficulty"), (int, float)) and not isinstance(data.get("difficulty"), bool):
            numeric_difficulty = float(data["difficulty"])
            if numeric_difficulty <= 4:
                data["difficulty"] = "简单"
            elif numeric_difficulty <= 7:
                data["difficulty"] = "中等"
            else:
                data["difficulty"] = "困难"
            notes.append("difficulty_number_to_label")
        elif "difficulty" in data and data.get("difficulty") not in (None, ""):
            difficulty_text = _first_text(
                data.get("difficulty"),
                ("difficulty", "label", "name", "value", "level", "d", "diff"),
            )
            normalized_difficulty = difficulty_label_map.get(
                difficulty_text.lower(),
                difficulty_label_map.get(difficulty_text),
            )
            if normalized_difficulty:
                data["difficulty"] = normalized_difficulty
                notes.append("difficulty_object_to_label")
            elif difficulty_text:
                data["difficulty"] = difficulty_text
                notes.append("difficulty_object_to_text")
            else:
                data["difficulty"] = _difficulty_label_from_units()
                notes.append("difficulty_defaulted_from_units")
        if isinstance(data.get("common_mistakes"), str):
            data["common_mistakes"] = [data["common_mistakes"].strip()]
            notes.append("common_mistakes_string_to_list")
        knowledge_point_aliases = {}
        if isinstance(data.get("knowledge_points"), list):
            for point in data["knowledge_points"]:
                if not isinstance(point, dict):
                    continue
                alias = _first_text(point, ("id", "kp_id", "k_id", "code", "ref"))
                label = _first_non_placeholder_text(
                    point,
                    ("knowledge_point", "point", "name", "label", "kp"),
                )
                if alias and label:
                    knowledge_point_aliases[alias.strip().upper()] = label
            normalized_points = []
            changed = False
            for point in data["knowledge_points"]:
                text = _first_text(
                    point,
                    ("knowledge_point", "point", "name", "label", "kp", "kp_id", "id"),
                )
                if text:
                    normalized_points.append(text)
                    changed = changed or not isinstance(point, str)
                elif isinstance(point, str):
                    normalized_points.append(point)
            if changed:
                data["knowledge_points"] = normalized_points
                notes.append("knowledge_points_dicts_to_strings")
        top_level_knowledge_fallbacks = [
            str(point).strip()
            for point in data.get("knowledge_points") or []
            if isinstance(point, str)
            and str(point).strip()
            and not _is_placeholder_knowledge_point(str(point))
        ]

        bloom_map = {
            "识记": 1, "记忆": 1, "remember": 1, "remembering": 1,
            "理解": 2, "understand": 2, "understanding": 2,
            "应用": 3, "apply": 3, "applying": 3,
            "分析": 4, "analyze": 4, "analysing": 4, "analyzing": 4,
            "评价": 5, "评估": 5, "evaluate": 5, "evaluating": 5,
            "创造": 6, "create": 6, "creating": 6,
        }
        difficulty_map = {
            "easy": 3.0, "simple": 3.0, "low": 3.0, "简单": 3.0, "低": 3.0,
            "medium": 5.5, "middle": 5.5, "中等": 5.5, "中": 5.5,
            "moderate": 5.5, "一般": 5.5, "适中": 5.5,
            "中等偏易": 4.8, "较易": 4.2, "偏易": 4.5,
            "hard": 8.0, "difficult": 8.0, "困难": 8.0, "高": 8.0,
            "high": 8.0, "较难": 7.5, "偏难": 7.2,
            "中等偏难": 6.8, "很难": 8.8, "高难": 8.8, "难": 8.0,
        }
        confidence_map = {
            "high": 0.85, "medium": 0.65, "low": 0.45,
            "高": 0.85, "中": 0.65, "低": 0.45,
        }

        scoring_units = data.get("scoring_units") or []
        for index, seu in enumerate(scoring_units, 1):
            if not isinstance(seu, dict):
                continue
            if not seu.get("seu_id"):
                for alt_key in ("id", "unit_id", "score_id", "label", "name"):
                    if seu.get(alt_key):
                        seu["seu_id"] = str(seu[alt_key])
                        notes.append(f"{alt_key}_to_seu_id")
                        break
                else:
                    seu["seu_id"] = f"seu_{index}"
                    notes.append("seu_id_defaulted")
            if not seu.get("label"):
                label = _first_text(
                    seu,
                    (
                        "knowledge_point",
                        "point",
                        "kp",
                        "name",
                        "reasoning_brief",
                        "description",
                        "seu_id",
                    ),
                )
                seu["label"] = label[:30] if label else f"采分点{index}"
                notes.append("seu_label_defaulted")
            if not isinstance(seu.get("knowledge_links"), list) or not seu.get("knowledge_links"):
                kp = _first_text(
                    seu,
                    ("knowledge_point", "point", "kp", "knowledge", "name", "label"),
                )
                if kp:
                    seu["knowledge_links"] = [{"knowledge_point": kp, "share": 1.0}]
                    notes.append("seu_knowledge_point_to_links")
            elif any(not isinstance(link, dict) for link in seu.get("knowledge_links") or []):
                seu["knowledge_links"] = [
                    {"knowledge_point": str(link), "share": 1.0}
                    if not isinstance(link, dict) else link
                    for link in seu.get("knowledge_links") or []
                ]
                notes.append("knowledge_links_strings_to_dicts")
            original = seu.get("score_share")
            coerced = cls._coerce_float(original)
            if coerced != original:
                seu["score_share"] = coerced
                notes.append("score_share_to_float")

            original = seu.get("allocation_confidence")
            coerced = cls._coerce_float(original, confidence_map)
            if coerced != original:
                seu["allocation_confidence"] = coerced
                notes.append("allocation_confidence_to_float")

            bloom = seu.get("bloom_level")
            if isinstance(bloom, str):
                normalized = bloom_map.get(bloom.strip().lower(), bloom_map.get(bloom.strip()))
                if normalized is not None:
                    seu["bloom_level"] = normalized
                    notes.append("bloom_level_to_int")

            original = seu.get("difficulty_estimate")
            coerced = cls._coerce_float(original, difficulty_map)
            if coerced != original:
                seu["difficulty_estimate"] = coerced
                notes.append("difficulty_estimate_to_float")

            if seu.get("allocation_source") not in ("explicit", "inferred"):
                seu["allocation_source"] = "inferred"
                notes.append("allocation_source_defaulted")

            for link in seu.get("knowledge_links") or []:
                if not isinstance(link, dict):
                    continue
                if not link.get("knowledge_point"):
                    for alt_key in ("kp_id", "point", "name", "knowledge"):
                        if link.get(alt_key):
                            link["knowledge_point"] = link[alt_key]
                            notes.append(f"{alt_key}_to_knowledge_point")
                            break
                    else:
                        if seu.get("label"):
                            link["knowledge_point"] = str(seu["label"])
                            notes.append("seu_label_to_knowledge_point")
                        elif link.get("k_id") or link.get("id"):
                            link["knowledge_point"] = str(link.get("k_id") or link.get("id"))
                            notes.append("id_to_knowledge_point")
                if _is_placeholder_knowledge_point(link.get("knowledge_point")):
                    placeholder = str(link.get("knowledge_point")).strip().upper()
                    replacement = knowledge_point_aliases.get(placeholder)
                    if not replacement:
                        replacement = _first_non_placeholder_text(
                            seu,
                            (
                                "knowledge_point",
                                "point",
                                "kp",
                                "knowledge",
                                "name",
                                "label",
                                "reasoning_brief",
                                "description",
                            ),
                        )
                    if not replacement and top_level_knowledge_fallbacks:
                        replacement = top_level_knowledge_fallbacks[
                            (index - 1) % len(top_level_knowledge_fallbacks)
                        ]
                    if replacement:
                        link["knowledge_point"] = replacement[:30]
                        notes.append("placeholder_knowledge_point_replaced")
                original = link.get("share")
                coerced = cls._coerce_float(original)
                if coerced != original:
                    link["share"] = coerced
                    notes.append("knowledge_link_share_to_float")

        if isinstance(data.get("knowledge_points"), list):
            replacement_points = []
            for seu in scoring_units:
                if not isinstance(seu, dict):
                    continue
                for link in seu.get("knowledge_links") or []:
                    if not isinstance(link, dict):
                        continue
                    point = str(link.get("knowledge_point") or "").strip()
                    if point and not _is_placeholder_knowledge_point(point) and point not in replacement_points:
                        replacement_points.append(point)
            if replacement_points and any(_is_placeholder_knowledge_point(point) for point in data["knowledge_points"]):
                data["knowledge_points"] = replacement_points[: max(3, len(data["knowledge_points"]))]
                notes.append("placeholder_knowledge_points_from_scoring_units")

        if isinstance(scoring_units, list) and scoring_units:
            shares = []
            for seu in scoring_units:
                if not isinstance(seu, dict) or not isinstance(seu.get("score_share"), (int, float)):
                    shares = []
                    break
                shares.append(float(seu["score_share"]))
            share_sum = sum(shares)
            deviation = abs(share_sum - 1.0)
            if shares and share_sum > 0 and 0.02 < deviation <= SCORE_SHARE_NORMALIZATION_MAX_DEVIATION:
                for seu, share in zip(scoring_units, shares):
                    seu["score_share"] = share / share_sum
                metadata = data.setdefault("_normalization_metadata", {})
                metadata["score_share_sum_normalized_from"] = round(share_sum, 6)
                metadata["score_share_sum_normalized_to"] = 1.0
                notes.append("score_share_sum_normalized")

        if isinstance(data.get("diagnostic_units"), str):
            data["diagnostic_units"] = [data["diagnostic_units"]]
            notes.append("diagnostic_units_string_to_list")
        if isinstance(data.get("diagnostic_units"), list):
            normalized_diagnostic_units = []
            changed = False
            for index, unit in enumerate(data.get("diagnostic_units") or [], 1):
                if isinstance(unit, dict):
                    normalized_diagnostic_units.append(unit)
                    continue
                text = _first_text(unit)
                if text:
                    normalized_diagnostic_units.append({
                        "du_id": f"du_{index}",
                        "option_or_trap": text[:24],
                        "distractor_type": "reasoning_trap",
                        "misconception": text[:30],
                        "trap_strength": 2,
                        "if_selected_means": [text[:30]],
                    })
                    changed = True
                else:
                    normalized_diagnostic_units.append(unit)
            if changed:
                data["diagnostic_units"] = normalized_diagnostic_units
                notes.append("diagnostic_units_strings_to_dicts")

        for index, unit in enumerate(data.get("diagnostic_units") or [], 1):
            if not isinstance(unit, dict):
                continue
            if not unit.get("du_id"):
                for alt_key in ("diagnostic_id", "id", "unit_id", "trap_id", "du", "d", "label", "name"):
                    if unit.get(alt_key):
                        unit["du_id"] = str(unit[alt_key])
                        notes.append(f"{alt_key}_to_du_id")
                        break
                else:
                    unit["du_id"] = f"du_{index}"
                    notes.append("du_id_defaulted")
            if not unit.get("option_or_trap"):
                for alt_key in ("option", "trap", "option_label", "label", "name", "title", "t", "text", "du_id"):
                    if unit.get(alt_key):
                        unit["option_or_trap"] = str(unit[alt_key])
                        notes.append(f"{alt_key}_to_option_or_trap")
                        break
                else:
                    unit["option_or_trap"] = f"trap_{index}"
                    notes.append("option_or_trap_defaulted")
            if not unit.get("distractor_type"):
                for alt_key in ("type", "category", "trap_type", "kind"):
                    if unit.get(alt_key):
                        unit["distractor_type"] = str(unit[alt_key])
                        notes.append(f"{alt_key}_to_distractor_type")
                        break
            if not unit.get("misconception"):
                for alt_key in ("misunderstanding", "label", "description", "mistake", "error", "m", "reason", "issue", "pitfall", "text", "trap"):
                    if unit.get(alt_key):
                        unit["misconception"] = str(unit[alt_key])
                        notes.append(f"{alt_key}_to_misconception")
                        break
            if not unit.get("knowledge_boundary"):
                for alt_key in ("boundary", "knowledge_point", "knowledge", "kp", "analysis", "explanation"):
                    if unit.get(alt_key):
                        unit["knowledge_boundary"] = str(unit[alt_key])
                        notes.append(f"{alt_key}_to_knowledge_boundary")
                        break
            if not unit.get("if_selected_means"):
                for alt_key in ("means", "meaning", "effect", "if_selected", "diagnosis"):
                    if unit.get(alt_key):
                        unit["if_selected_means"] = unit[alt_key]
                        notes.append(f"{alt_key}_to_if_selected_means")
                        break
            means = unit.get("if_selected_means")
            if isinstance(means, str):
                unit["if_selected_means"] = [means]
                notes.append("if_selected_means_to_list")
            original = unit.get("trap_strength")
            coerced = cls._coerce_float(
                original,
                {
                    "low": 1, "weak": 1, "medium": 2, "middle": 2, "high": 3, "strong": 3,
                    "低": 1, "弱": 1, "较弱": 1,
                    "中": 2, "中等": 2, "一般": 2, "中等强度": 2,
                    "高": 3, "强": 3, "较强": 3, "很强": 3, "高强度": 3,
                },
            )
            if isinstance(coerced, (int, float)):
                value = float(coerced)
                if 0 < value <= 1:
                    if value >= 0.67:
                        value = 3
                    elif value >= 0.34:
                        value = 2
                    else:
                        value = 1
                else:
                    value = round(value)
                coerced = max(1, min(3, int(value)))
            if coerced != original and coerced in (1, 2, 3):
                unit["trap_strength"] = coerced
                notes.append("trap_strength_to_int")

        if isinstance(data.get("stimulus_units"), str):
            data["stimulus_units"] = [data["stimulus_units"]]
            notes.append("stimulus_units_string_to_list")
        if isinstance(data.get("stimulus_units"), list):
            normalized_stimulus_units = []
            changed = False
            for index, unit in enumerate(data.get("stimulus_units") or [], 1):
                if isinstance(unit, dict):
                    normalized_stimulus_units.append(unit)
                    continue
                text = _first_text(unit)
                if text:
                    normalized_stimulus_units.append({
                        "su_id": f"su_{index}",
                        "stimulus_type": "text",
                        "complexity": 2,
                        "is_core": True,
                        "description": text[:30],
                    })
                    changed = True
                else:
                    normalized_stimulus_units.append(unit)
            if changed:
                data["stimulus_units"] = normalized_stimulus_units
                notes.append("stimulus_units_strings_to_dicts")

        stimulus_type_aliases = {
            "image": "chart", "figure": "chart", "fig": "chart", "graph": "chart",
            "图": "chart", "图片": "chart", "图像": "chart", "图示": "chart",
            "表": "table", "表格": "table",
            "流程": "flowchart", "流程图": "flowchart", "实验流程": "flowchart",
            "系谱": "pedigree", "系谱图": "pedigree",
            "装置": "device", "实验装置": "device",
            "多材料": "multi", "综合材料": "multi",
        }

        for index, unit in enumerate(data.get("stimulus_units") or [], 1):
            if not isinstance(unit, dict):
                continue
            if not unit.get("su_id"):
                for alt_key in ("stu_id", "id", "su", "s", "label", "name"):
                    if unit.get(alt_key):
                        unit["su_id"] = str(unit[alt_key])
                        notes.append(f"{alt_key}_to_su_id")
                        break
                else:
                    unit["su_id"] = f"su_{index}"
                    notes.append("su_id_defaulted")
            if not unit.get("description"):
                for alt_key in ("label", "name", "content", "summary", "text", "s", "stem", "material", "source", "su_id"):
                    if unit.get(alt_key):
                        unit["description"] = str(unit[alt_key])[:30]
                        notes.append(f"{alt_key}_to_stimulus_description")
                        break
                else:
                    unit["description"] = f"题干材料{index}"
                    notes.append("stimulus_description_defaulted")
            if not unit.get("stimulus_type"):
                raw = str(unit.get("type") or unit.get("kind") or "").lower()
                if raw in {"text", "chart", "table", "pedigree", "device", "flowchart", "multi"}:
                    unit["stimulus_type"] = raw
                    notes.append("type_to_stimulus_type")
                elif raw in stimulus_type_aliases:
                    unit["stimulus_type"] = stimulus_type_aliases[raw]
                    notes.append("type_to_stimulus_type")
                else:
                    unit["stimulus_type"] = "text"
                    notes.append("stimulus_type_defaulted")
            original = unit.get("complexity")
            coerced = cls._coerce_float(
                original,
                {
                    "low": 1, "medium": 2, "high": 3,
                    "简单": 1, "低": 1,
                    "中": 2, "中等": 2,
                    "困难": 3, "高": 3,
                },
            )
            if isinstance(coerced, float):
                coerced = int(round(coerced))
            if coerced != original and coerced in (1, 2, 3):
                unit["complexity"] = coerced
                notes.append("stimulus_complexity_to_int")

        return data, sorted(set(notes))

    async def split_questions(self, image_bytes: list, extracted_text: str = None) -> list:
        """
        第一次调用：拆分试卷为单独题目

        Args:
            image_bytes: 文档图片字节流列表
            extracted_text: 从Word提取的纯文字（可选，用于提升识别准确率）

        Returns:
            [
                {
                    "id": 1,
                    "content": "题目文本内容",
                    "image_indices": [0, 1]  # 对应原始图片的索引
                }
            ]
        """
        logger.info(f"[拆分] 开始调用LLM，图片数量: {len(image_bytes)}")

        # 加载拆分Prompt
        prompt_path = str(PROMPT_DIR / "split_prompt.txt")
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                split_prompt = f.read()
            logger.debug(f"[拆分] Prompt加载成功，长度: {len(split_prompt)} 字符")
        except FileNotFoundError:
            split_prompt = self._get_default_split_prompt()
            logger.warning(f"[拆分] 使用默认Prompt（未找到{prompt_path}）")

        # 如果有提取的文字，添加到 Prompt 前面
        if extracted_text:
            logger.info(f"[拆分] 检测到Word提取文字，长度: {len(extracted_text)} 字符")
            enhanced_prompt = f"""**重要提示**：以下是从Word文档中提取的纯文字内容（100%准确），请优先使用这些文字而非OCR识别图片：

---开始提取文字---
{extracted_text}
---结束提取文字---

{split_prompt}

**注意**：图片仅用于查看题目布局和图表，文字内容请使用上面提取的纯文字。"""
            split_prompt = enhanced_prompt
        else:
            logger.debug("[拆分] 未检测到提取文字，使用纯OCR模式")

        split_media_items = _question_images_to_media_items(image_bytes)
        for idx, _ in enumerate(split_media_items):
            logger.debug(f"[拆分] 已添加图片 {idx + 1}/{len(split_media_items)}")

        try:
            logger.debug("[拆分] 准备调用 llm_call（统一 fallback 客户端）")
            logger.debug("[拆分] 请求参数 - max_tokens: 8192, temperature: 0")

            response_text = await llm_call(
                messages=_question_messages(split_prompt, split_media_items),
                max_tokens=8192,
                temperature=0,
                timeout=120.0,
                purpose="question_split",
            )
            finish_reason = "stop"  # fallback 客户端已处理截断重试

            logger.info(f"[拆分] API响应长度: {len(response_text) if response_text else 0}")
            logger.debug(f"[拆分] 完成原因: {finish_reason}")
            logger.debug(f"[拆分] 原始返回:\n{response_text}")

            # 检查是否被截断（优先检查）
            if finish_reason == 'length':
                logger.error(f"[拆分] 内容被截断！响应长度: {len(response_text) if response_text else 0}")
                logger.error(f"[拆分] 可能原因：试卷题目过多或内容过长，超出max_tokens限制")
                raise ValueError("题目拆分内容被截断，请优化prompt或增加max_tokens")

            # 检查返回是否为空
            if not response_text or response_text.strip() == "":
                logger.error("[拆分] API返回为空！")
                raise ValueError("API返回内容为空")

            # 提取并解析JSON
            json_text = self.extract_json(response_text)
            questions = json.loads(json_text)
            split_metadata = {
                "response_length": len(response_text),
                "question_count": len(questions) if isinstance(questions, list) else 0,
                "finish_reason": finish_reason,
            }
            provider, model, fallback_count, split_metadata = _llm_call_trace(split_metadata)
            split_call = LLMCallRecord(
                call_id="exam-split-questions",
                purpose="split_questions",
                prompt_id="biology.split_questions",
                prompt_hash=sha256(split_prompt.encode("utf-8")).hexdigest(),
                provider=provider,
                model=model,
                input_refs={
                    "image_count": len(image_bytes),
                    "has_extracted_text": bool(extracted_text),
                    "extracted_text_length": len(extracted_text or ""),
                },
                parsed_schema="SplitQuestionList",
                confidence=1.0,
                fallback_count=fallback_count,
                metadata=split_metadata,
            ).model_dump()
            if isinstance(questions, list):
                for question in questions:
                    if isinstance(question, dict):
                        question.setdefault("_llm_calls", []).append(split_call)
            logger.info(f"[拆分] 成功识别 {len(questions)} 道题目")
            return questions

        except json.JSONDecodeError as e:
            logger.error(f"[拆分] JSON解析失败: {e}\n原始文本: {response_text}")
            raise
        except Exception as e:
            logger.error(f"[拆分] API调用失败: {str(e)}", exc_info=True)
            raise

    async def analyze_question(
        self,
        question_text: str,
        question_images: list,
        question_id: int,
        question_type: str = "unknown",
        section_header: str = None,
        evidence_context_provider=None,
        evidence_ranking_enabled: bool | str | None = None,
        agent_search_enabled: bool | str | None = None,
    ) -> dict:
        """
        第二次调用：分析单道题目

        Args:
            question_text: 题目文本
            question_images: 题目相关图片
            question_id: 题目ID
            question_type: 题目类型 (single_choice/multiple_choice/fill_blank/short_answer/experiment/unknown)
            section_header: 分节标题 (如"一、单选题（1-15题，每题2分，共30分）")

        Returns:
            {
                "knowledge_points": ["遗传学", "基因分离定律"],
                "detailed_analysis": "步骤1:...",
                "difficulty": "中等",
                "common_mistakes": ["..."],
                "answer": "...",  # 根据题型返回不同格式
                "sub_questions": [...]  # 如果有子题
            }
        """
        logger.info(f"[分析] 开始分析题目 {question_id}，题型: {question_type}，分节: {section_header}")

        # 优先加载 v2 prompt（细粒度 SEU/DU/SU 分析）
        use_v2 = False
        v2_path = PROMPT_DIR / "analysis_prompt_v2.txt"
        v1_path = PROMPT_DIR / "analysis_prompt.txt"
        try:
            if v2_path.exists():
                with open(str(v2_path), 'r', encoding='utf-8') as f:
                    analysis_prompt_template = f.read()
                use_v2 = True
                logger.info(f"[分析] 题目{question_id} 使用 v2 prompt（细粒度分析）")
            else:
                with open(str(v1_path), 'r', encoding='utf-8') as f:
                    analysis_prompt_template = f.read()
                logger.debug(f"[分析] 题目{question_id} 使用 v1 prompt")
        except FileNotFoundError:
            analysis_prompt_template = self._get_default_analysis_prompt()
            logger.warning(f"[分析] 使用默认Prompt")

        prompt_hash = sha256(analysis_prompt_template.encode("utf-8")).hexdigest()
        analysis_prompt_id = "biology.question_analysis." + ("v" + "2" if use_v2 else "v1")
        evidence_context_meta = None
        evidence_context_text = ""
        question_media_items = _question_images_to_media_items(question_images)
        question_media_refs = media_input_refs(question_media_items)
        visual_context_text = ""
        visual_call_record = None
        is_long_analysis = question_type in ("short_answer", "non_choice") or len(question_text) > 500
        analysis_timeout = 240.0 if is_long_analysis else 120.0
        analysis_max_tokens = 16000 if is_long_analysis else 12000

        def build_call_record(payload: dict, parsed_schema: str, confidence: float,
                              validation_errors: list = None, *,
                              prompt_id: str = None, prompt_hash_value: str = None,
                              response_len: int = None, call_suffix: str = "analysis",
                              retry_count: int = 0, metadata_extra: dict = None) -> dict:
            metadata = {
                "response_length": response_len if response_len is not None else response_length,
                "analysis_version": payload.get("_analysis_version", ""),
            }
            if metadata_extra:
                metadata.update(metadata_extra)
            if evidence_context_meta:
                metadata["evidence_context"] = evidence_context_meta
            if visual_context_text:
                metadata["visual_context_source"] = "qwen_vision"
            provider, model, fallback_count, metadata = _llm_call_trace(metadata)
            call = LLMCallRecord(
                call_id=f"question-{question_id}-{call_suffix}",
                question_id=question_id,
                purpose="question_analysis",
                prompt_id=prompt_id or analysis_prompt_id,
                prompt_hash=prompt_hash_value or prompt_hash,
                provider=provider,
                model=model,
                input_refs={
                    "question_id": question_id,
                    "question_type": question_type,
                    "section_header": section_header,
                    "image_count": len(question_media_items),
                    **question_media_refs,
                },
                parsed_schema=parsed_schema,
                confidence=confidence,
                validation_errors=validation_errors or [],
                fallback_count=fallback_count,
                retry_count=retry_count,
                metadata=metadata,
            )
            return call.model_dump()

        def attach_call_record(payload: dict, parsed_schema: str, confidence: float,
                               validation_errors: list = None, *,
                               existing_calls: list = None, **call_kwargs) -> dict:
            calls = list(existing_calls or [])
            calls.append(build_call_record(
                payload,
                parsed_schema,
                confidence,
                validation_errors,
                **call_kwargs,
            ))
            if evidence_context_meta:
                payload["_evidence_context"] = evidence_context_meta
            payload["_llm_calls"] = calls
            return payload

        # 替换参数
        analysis_prompt = analysis_prompt_template.replace("{question_type}", question_type)
        analysis_prompt = analysis_prompt.replace("{section_header}", section_header or "未提供")

        # 构造完整Prompt
        prompt_sections = [analysis_prompt]
        from services.evidence_context import (
            QuestionEvidenceContextBuilder,
            evidence_ranking_enabled as _evidence_ranking_enabled,
        )
        def _is_transient_evidence_context_error(exc: Exception) -> bool:
            text = str(exc).lower()
            transient_markers = (
                "access token failed",
                "transporterror",
                "proxyerror",
                "remote end closed connection",
                "connectionpool",
                "read timed out",
                "connect timeout",
                "temporarily unavailable",
                "connection reset",
            )
            return any(marker in text for marker in transient_markers)

        if _evidence_ranking_enabled(evidence_ranking_enabled):
            provider = evidence_context_provider or QuestionEvidenceContextBuilder()
            evidence_context = None
            evidence_context_errors = []
            for attempt in range(3):
                try:
                    evidence_context = await provider.build_question_context(
                        question_text=question_text,
                        question_id=question_id,
                        question_type=question_type,
                        section_header=section_header,
                        agent_search_enabled=agent_search_enabled,
                    )
                    break
                except Exception as exc:
                    evidence_context_errors.append(str(exc))
                    if attempt < 2 and _is_transient_evidence_context_error(exc):
                        wait_seconds = 2 ** attempt
                        logger.warning(
                            "[证据重排] 题目%s transient error，%ss 后重试 %s/2: %s",
                            question_id,
                            wait_seconds,
                            attempt + 1,
                            str(exc)[:160],
                        )
                        await asyncio.sleep(wait_seconds)
                        continue
                    raise RuntimeError(
                        f"题目{question_id}证据重排失败（证据排序服务）: {exc}"
                    ) from exc
            evidence_context_text = str(evidence_context.get("context_text") or "").strip()
            if not evidence_context_text:
                raise RuntimeError(
                    f"题目{question_id}证据重排失败（证据排序服务）: empty context"
                )
            prompt_sections.append(evidence_context_text)
            evidence_context_meta = evidence_context.get("metadata") or {}
            if evidence_context_errors:
                evidence_context_meta["retry_errors"] = evidence_context_errors

        if question_media_items:
            visual_context_text, visual_call_record = await extract_visual_context(
                question_media_items,
                question_text=question_text,
                question_id=question_id,
                question_type=question_type,
                section_header=section_header or "",
                timeout=min(analysis_timeout, 120.0),
            )
            prompt_sections.append(visual_context_text)

        full_prompt = "\n\n".join(prompt_sections + [f"题目内容：\n{question_text}"])
        initial_calls = [visual_call_record] if visual_call_record else []

        def _last_provider_error_messages() -> list[str]:
            try:
                trace = get_last_call_metadata() or {}
            except Exception:
                trace = {}
            messages = []
            for error in trace.get("provider_errors") or []:
                if isinstance(error, dict):
                    messages.append(str(error.get("message") or ""))
            return messages

        def _is_length_provider_failure(exc: Exception) -> bool:
            error_messages = [str(exc)] + _last_provider_error_messages()
            for _, provider_exc in getattr(exc, "errors", []) or []:
                error_messages.append(str(provider_exc))
            error_text = " ".join(error_messages).lower()
            return "finish_reason=length" in error_text

        def _infer_fallback_total_score() -> float:
            question_match = re.search(r"[（(]\s*(\d+(?:\.\d+)?)\s*分\s*[）)]", question_text or "")
            if question_match:
                return float(question_match.group(1))
            header = section_header or ""
            english_match = re.search(
                r"(\d+(?:\.\d+)?)\s*points?",
                f"{question_text or ''} {header}",
                flags=re.IGNORECASE,
            )
            if english_match:
                return float(english_match.group(1))
            header_match = re.search(r"每(?:小)?题\s*(\d+(?:\.\d+)?)\s*分|每小题\s*(\d+(?:\.\d+)?)\s*分", header)
            if header_match:
                return float(next(group for group in header_match.groups() if group))
            if question_type in ("single_choice", "multiple_choice"):
                return 2.0
            return 0.0

        def _fallback_knowledge_points() -> list[str]:
            text = question_text or ""
            if any(marker in text for marker in ("CGG", "三核苷酸", "动态突变", "脆性X")):
                return ["基因突变"]
            if any(marker in text for marker in ("基因", "遗传", "杂交", "配子")):
                return ["遗传的基本规律"]
            if any(marker in text for marker in ("生态", "食物链", "营养级", "群落")):
                return ["生态系统"]
            if any(marker in text for marker in ("蛋白", "转录", "翻译")):
                return ["基因表达"]
            return []

        async def _deterministic_length_recovery(initial_reason: str, retry_count: int = 3) -> dict:
            fallback_prompt_hash = sha256(
                f"deterministic_length_recovery:{question_type}:{section_header or ''}".encode("utf-8")
            ).hexdigest()
            result = {
                "knowledge_points": _fallback_knowledge_points(),
                "detailed_analysis": "DeepSeek连续截断，已生成保底分析并标记为需人工复核。",
                "difficulty": "中等",
                "common_mistakes": ["模型输出连续截断导致细粒度审题缺失"],
                "answer": "",
                "total_score": _infer_fallback_total_score(),
                "bloom_level": 3,
                "_extraction_confidence": 0.2,
                "_analysis_version": "v1_length_recovery_deterministic",
                "_fine_grained": {
                    "scoring_units": [],
                    "diagnostic_units": [],
                    "stimulus_units": [],
                },
                "_validation_errors": [
                    "llm_length_recovery_deterministic_fallback",
                    f"initial_error: {initial_reason}",
                ],
            }
            logger.error(
                f"[分析] 题目{question_id} DeepSeek连续截断，启用确定性保底分析: {initial_reason}"
            )
            return attach_call_record(
                result,
                "AnalysisResult",
                0.2,
                result["_validation_errors"],
                existing_calls=initial_calls,
                prompt_id="biology.question_analysis.v1.length_recovery.deterministic",
                prompt_hash_value=fallback_prompt_hash,
                response_len=0,
                call_suffix="analysis-length-recovery-deterministic",
                retry_count=retry_count,
                metadata_extra={
                    "initial_error": initial_reason,
                    "initial_provider_errors": _last_provider_error_messages(),
                    "recovery_mode": "deterministic_length_fallback",
                    "recovery_status": "degraded",
                },
            )

        async def _compact_analysis_retry(initial_reason: str, initial_response_length: int = 0) -> dict:
            logger.warning(f"[分析] 题目{question_id} 触发 compact v2 重试: {initial_reason}")
            compact_prompt = self._get_compact_analysis_retry_prompt(
                question_type=question_type,
                section_header=section_header,
            )
            compact_prompt_hash = sha256(compact_prompt.encode("utf-8")).hexdigest()
            compact_prompt_id = "biology.question_analysis.v2.compact_retry"
            compact_timeout = min(max(analysis_timeout, 180.0), 220.0)
            compact_max_tokens = min(analysis_max_tokens, 8192)
            try:
                compact_response = await asyncio.wait_for(
                    llm_call(
                        messages=_question_messages(
                            "\n\n".join(
                                part for part in [
                                    compact_prompt,
                                    visual_context_text[:1500],
                                    f"Question content:\n{question_text[:3500]}",
                                ]
                                if part
                            ),
                            [],
                        ),
                        max_tokens=compact_max_tokens,
                        temperature=0,
                        timeout=compact_timeout,
                        purpose="question_analysis_retry",
                    ),
                    timeout=compact_timeout + 5.0,
                )
            except asyncio.TimeoutError as compact_exc:
                return await _ultra_compact_analysis_retry(
                    f"{initial_reason}; compact_retry_timeout: {compact_exc}",
                    retry_count=2,
                )
            except Exception as compact_exc:
                if _is_length_provider_failure(compact_exc):
                    return await _ultra_compact_analysis_retry(
                        f"{initial_reason}; compact_retry_failed: {compact_exc}",
                        retry_count=2,
                    )
                raise
            compact_response_length = len(compact_response) if compact_response else 0
            compact_json = self.extract_json(compact_response)
            if not compact_json.startswith('{'):
                start = compact_json.find('{')
                if start != -1:
                    compact_json = compact_json[start:]
            if not compact_json.endswith('}'):
                end = compact_json.rfind('}')
                if end != -1:
                    compact_json = compact_json[:end + 1]
            try:
                compact_result = json.loads(compact_json)
                compact_result, normalization_notes = self._normalize_fine_grained_result(compact_result)
                from llm_schemas import (FineGrainedResult, validate_llm_output,
                                         compute_summary_from_units, validate_score_conservation)
                validated, ext_conf, val_errors = validate_llm_output(
                    compact_result,
                    FineGrainedResult,
                    f"题目{question_id} compact v2",
                )
                fg = FineGrainedResult(**validated)
            except Exception as compact_parse_exc:
                return await _ultra_compact_analysis_retry(
                    f"{initial_reason}; compact_retry_parse_failed: {compact_parse_exc}",
                    retry_count=2,
                )
            expected_total_score = fg.total_score if isinstance(fg.total_score, (int, float)) and fg.total_score > 0 else None
            if expected_total_score is None:
                is_conserved = False
                conservation_errors = ["fine_grained total_score missing_or_non_positive"]
            else:
                is_conserved, conservation_errors = validate_score_conservation(fg, expected_total_score)
            if not is_conserved:
                val_errors = (val_errors or []) + conservation_errors
                ext_conf = min(ext_conf, 0.6)
            summary = compute_summary_from_units(fg)
            validated.update(summary)
            validated["_fine_grained"] = {
                "scoring_units": [s.model_dump() if hasattr(s, 'model_dump') else s for s in fg.scoring_units],
                "diagnostic_units": [d.model_dump() if hasattr(d, 'model_dump') else d for d in fg.diagnostic_units],
                "stimulus_units": [s.model_dump() if hasattr(s, 'model_dump') else s for s in fg.stimulus_units],
            }
            validated["_extraction_confidence"] = ext_conf
            validated["_analysis_version"] = "v2_compact_retry"
            if val_errors:
                validated["_validation_errors"] = val_errors
            validated = attach_call_record(
                validated,
                "FineGrainedResult",
                ext_conf,
                val_errors,
                existing_calls=initial_calls,
                prompt_id=compact_prompt_id,
                prompt_hash_value=compact_prompt_hash,
                response_len=compact_response_length,
                call_suffix="analysis-compact-retry",
                retry_count=1,
                metadata_extra={
                    "initial_error": initial_reason,
                    "initial_response_length": initial_response_length,
                    "initial_provider_errors": _last_provider_error_messages(),
                    "normalization_notes": normalization_notes,
                    "recovery_mode": "compact_v2",
                    "recovery_status": "ok" if not val_errors else "validation_warnings",
                },
            )
            logger.info(f"[分析] 题目{question_id} compact v2 重试完成 (confidence={ext_conf}, conserved={is_conserved}, SEU={len(fg.scoring_units)})")
            return await self._retry_missing_evidence_units(
                analysis_payload=validated,
                question_id=question_id,
                question_type=question_type,
                section_header=section_header,
                question_text=question_text,
                question_media_items=question_media_items,
                visual_context_text=visual_context_text,
                timeout=analysis_timeout,
            )

        async def _analyze_one_subquestion(sub_idx: int, sub_meta: dict, all_subs: list, big_total: float):
            """RC7 方案A：单子问定向分析。喂全题干 + 只产第 sub_idx 问 SEU（局部 score_share 和=1.0）。
            预算小阶梯（4096→2048 治 length）+ 同预算瞬时重试（治 DeepSeek 空内容/providers failed 抖动）。
            子问级故障隔离：单子问失败不波及其它子问（由 _split_merge_analysis 串行编排兜底回退）。"""
            from llm_schemas import FineGrainedResult, validate_llm_output
            brief_list = "；".join(
                f"第{j}问({s.get('brief','')})" for j, s in enumerate(all_subs, start=1))
            sub_pts = sub_meta.get("points") or round((sub_meta.get("score_share") or 0) * big_total) or "若干"
            sub_prompt = (
                "你是生物学审题专家。下面是整道大题的完整题干与子问清单。\n"
                f"本次【只分析第{sub_idx}问】（{sub_meta.get('brief','')}，约{sub_pts}分），"
                f"只为这一问产出采分点 scoring_units(SEU)，不要分析其它子问。\n"
                f"子问清单：{brief_list}\n"
                "硬性规则：\n"
                f"1. 只产第{sub_idx}问的 SEU；本问 scoring_units 的 score_share 在【本问内部】合计=1.0。\n"
                "2. 每个 SEU 的 knowledge_links 的 share 在该 SEU 内合计=1.0。\n"
                "3. bloom_level 必须是 1-6 的整数（不是中文）。\n"
                "4. 严格输出 JSON（不要解释、不要 markdown）：\n"
                "{\"scoring_units\":[{\"seu_id\":\"seu_1\",\"label\":\"\",\"score_share\":0.0,"
                "\"knowledge_links\":[{\"knowledge_point\":\"\",\"share\":1.0}],\"bloom_level\":3,"
                "\"reasoning_brief\":\"\"}],\"diagnostic_units\":[],\"stimulus_units\":[],\"detailed_analysis\":\"\"}\n"
                f"题型:{question_type} 板块:{section_header or ''}"
            )
            sub_timeout = max(analysis_timeout, 480.0)
            for sub_budget in (64000,):
                _transient_left = 1
                while True:
                    try:
                        sub_resp = await asyncio.wait_for(
                            llm_call(
                                messages=_question_messages(
                                    "\n\n".join(part for part in [
                                        sub_prompt,
                                        (visual_context_text or "")[:1200],
                                        f"题目内容：\n{question_text}",
                                    ] if part),
                                    [],
                                ),
                                max_tokens=sub_budget,
                                temperature=0,
                                timeout=sub_timeout,
                                purpose="question_analysis_subquestion",
                            ),
                            timeout=sub_timeout + 5.0,
                        )
                    except Exception as sub_exc:
                        if _is_length_provider_failure(sub_exc):
                            break
                        if _transient_left > 0:
                            _transient_left -= 1
                            logger.warning(f"[分析] 题目{question_id} 第{sub_idx}问瞬时失败重试: {sub_exc}")
                            continue
                        logger.warning(f"[分析] 题目{question_id} 第{sub_idx}问调用失败: {sub_exc}")
                        return None
                    sub_clean = self.extract_json(sub_resp)
                    if not sub_clean.startswith('{'):
                        _s = sub_clean.find('{')
                        sub_clean = sub_clean[_s:] if _s != -1 else sub_clean
                    if not sub_clean.endswith('}'):
                        _e = sub_clean.rfind('}')
                        sub_clean = sub_clean[:_e + 1] if _e != -1 else sub_clean
                    try:
                        sub_obj = json.loads(sub_clean)
                        sub_obj, _ = self._normalize_fine_grained_result(sub_obj)
                        sub_validated, _conf, _errs = validate_llm_output(
                            sub_obj, FineGrainedResult, f"题目{question_id} 第{sub_idx}问")
                        sub_fg = FineGrainedResult(**sub_validated)
                    except Exception as sub_parse_exc:
                        if _transient_left > 0:
                            _transient_left -= 1
                            logger.warning(f"[分析] 题目{question_id} 第{sub_idx}问解析失败重试: {sub_parse_exc}")
                            continue
                        logger.warning(f"[分析] 题目{question_id} 第{sub_idx}问解析失败: {sub_parse_exc}")
                        return None
                    if not sub_fg.scoring_units:
                        return None
                    return {
                        "scoring_units": [u.model_dump() for u in sub_fg.scoring_units],
                        "diagnostic_units": [u.model_dump() for u in sub_fg.diagnostic_units],
                        "stimulus_units": [u.model_dump() for u in sub_fg.stimulus_units],
                        "detailed_analysis": sub_validated.get("detailed_analysis", ""),
                    }
            return None

        async def _split_merge_analysis(initial_reason: str):
            """RC7 方案A：大题按子问拆分→定向输出→合并。复用 extractor(缓存近免费)拿子问分段+权重。
            子问调用【并行】（DeepSeek 500 并发，子问并行安全；旧串行前提是 16384 cap 下的误判）。
            extract 失败 / 子问<2 / 任一子问失败 → 返回 None，调用方回退现有整题阶梯（安全网保留）。"""
            big_total = _infer_fallback_total_score()
            if not big_total or big_total < 8:
                return None
            try:
                from feature_extractor import extract_big_question_features
                bigq = await extract_big_question_features(
                    question_text, question_type=question_type, total_score=big_total)
            except Exception as extract_exc:
                logger.warning(f"[分析] 题目{question_id} split-merge extract 异常 {extract_exc}，回退阶梯")
                return None
            if not (isinstance(bigq, dict) and bigq.get("subquestions")):
                return None
            sub_metas = bigq["subquestions"]
            if len(sub_metas) < 2:
                return None
            logger.warning(f"[分析] 题目{question_id} 触发 split-merge：{len(sub_metas)} 子问拆分（并行）({initial_reason})")
            _sub_tasks = [
                _analyze_one_subquestion(_i, _sm, sub_metas, big_total)
                for _i, _sm in enumerate(sub_metas, start=1)
            ]
            _sub_raw = await asyncio.gather(*_sub_tasks, return_exceptions=True)
            results = []
            for _i, _r in enumerate(_sub_raw, start=1):
                if isinstance(_r, Exception):
                    logger.warning(f"[分析] 题目{question_id} 第{_i}问 split 异常: {_r}")
                    results.append(None)
                else:
                    results.append(_r)
            ok_results, ok_metas = [], []
            for _idx, _r in enumerate(results):
                if isinstance(_r, dict) and _r.get("scoring_units"):
                    ok_results.append(_r)
                    ok_metas.append(sub_metas[_idx])
                else:
                    logger.warning(f"[分析] 题目{question_id} 第{_idx+1}问 split 失败")
            if len(ok_results) < len(sub_metas):
                logger.warning(f"[分析] 题目{question_id} split-merge 子问不全 ({len(ok_results)}/{len(sub_metas)})，回退阶梯")
                return None
            from fine_grained_merge import merge_subquestion_results
            merged = merge_subquestion_results(ok_results, ok_metas, big_total)
            from llm_schemas import (FineGrainedResult, validate_llm_output,
                                     compute_summary_from_units, validate_score_conservation)
            try:
                validated, ext_conf, val_errors = validate_llm_output(
                    merged, FineGrainedResult, f"题目{question_id} split-merge")
                fg = FineGrainedResult(**validated)
            except Exception as merge_exc:
                logger.warning(f"[分析] 题目{question_id} split-merge 合并构造失败 {merge_exc}，回退阶梯")
                return None
            is_conserved, conservation_errors = validate_score_conservation(fg, fg.total_score)
            if not is_conserved:
                val_errors = (val_errors or []) + conservation_errors
                ext_conf = min(ext_conf, 0.6)
            summary = compute_summary_from_units(fg)
            validated.update(summary)
            validated["_fine_grained"] = {
                "scoring_units": [u.model_dump() if hasattr(u, 'model_dump') else u for u in fg.scoring_units],
                "diagnostic_units": [u.model_dump() if hasattr(u, 'model_dump') else u for u in fg.diagnostic_units],
                "stimulus_units": [u.model_dump() if hasattr(u, 'model_dump') else u for u in fg.stimulus_units],
            }
            validated["_extraction_confidence"] = ext_conf
            validated["_analysis_version"] = "v2_split_merge"
            if val_errors:
                validated["_validation_errors"] = val_errors
            validated = attach_call_record(
                validated, "FineGrainedResult", ext_conf, val_errors,
                existing_calls=initial_calls,
                prompt_id="biology.question_analysis.v2.split_merge",
                prompt_hash_value=sha256(("split_merge:" + str(question_type)).encode("utf-8")).hexdigest(),
                response_len=0,
                call_suffix="analysis-split-merge",
                retry_count=1,
                metadata_extra={
                    "initial_error": initial_reason,
                    "recovery_mode": "split_merge",
                    "subquestion_count": len(sub_metas),
                    "recovery_status": "ok" if not val_errors else "validation_warnings",
                },
            )
            logger.info(f"[分析] 题目{question_id} split-merge 完成 (子问={len(sub_metas)}, SEU={len(fg.scoring_units)}, conserved={is_conserved})")
            return await self._retry_missing_evidence_units(
                analysis_payload=validated,
                question_id=question_id,
                question_type=question_type,
                section_header=section_header,
                question_text=question_text,
                question_media_items=question_media_items,
                visual_context_text=visual_context_text,
                timeout=analysis_timeout,
            )

        async def _ultra_compact_analysis_retry(initial_reason: str, retry_count: int = 2) -> dict:
            logger.warning(f"[分析] 题目{question_id} 触发 ultra-compact v2 重试: {initial_reason}")
            provider_errors_before = _last_provider_error_messages()
            ultra_prompt = self._get_ultra_compact_analysis_retry_prompt(
                question_type=question_type,
                section_header=section_header,
            )
            ultra_prompt_hash = sha256(ultra_prompt.encode("utf-8")).hexdigest()
            ultra_timeout = min(max(analysis_timeout, 140.0), 180.0)
            try:
                ultra_response = await asyncio.wait_for(
                    llm_call(
                        messages=_question_messages(
                            "\n\n".join(
                                part for part in [
                                    ultra_prompt,
                                    visual_context_text[:600],
                                    f"Question content:\n{question_text[:2200]}",
                                ]
                                if part
                            ),
                            [],
                        ),
                        max_tokens=4096,
                        temperature=0,
                        timeout=ultra_timeout,
                        purpose="question_analysis_retry",
                    ),
                    timeout=ultra_timeout + 5.0,
                )
            except Exception as ultra_exc:
                return await _micro_compact_analysis_retry(
                    f"{initial_reason}; ultra_compact_retry_failed: {ultra_exc}",
                    retry_count=retry_count + 1,
                )

            ultra_response_length = len(ultra_response) if ultra_response else 0
            ultra_json = self.extract_json(ultra_response)
            if not ultra_json.startswith('{'):
                start = ultra_json.find('{')
                if start != -1:
                    ultra_json = ultra_json[start:]
            if not ultra_json.endswith('}'):
                end = ultra_json.rfind('}')
                if end != -1:
                    ultra_json = ultra_json[:end + 1]
            try:
                ultra_result = json.loads(ultra_json)
                ultra_result, normalization_notes = self._normalize_fine_grained_result(ultra_result)
                from llm_schemas import (FineGrainedResult, validate_llm_output,
                                         compute_summary_from_units, validate_score_conservation)
                validated, ext_conf, val_errors = validate_llm_output(
                    ultra_result,
                    FineGrainedResult,
                    f"题目{question_id} ultra compact v2",
                )
                fg = FineGrainedResult(**validated)
            except Exception as ultra_parse_exc:
                return await _micro_compact_analysis_retry(
                    f"{initial_reason}; ultra_compact_retry_parse_failed: {ultra_parse_exc}",
                    retry_count=retry_count + 1,
                )

            expected_total_score = fg.total_score if isinstance(fg.total_score, (int, float)) and fg.total_score > 0 else None
            if expected_total_score is None:
                is_conserved = False
                conservation_errors = ["fine_grained total_score missing_or_non_positive"]
            else:
                is_conserved, conservation_errors = validate_score_conservation(fg, expected_total_score)
            if not is_conserved:
                val_errors = (val_errors or []) + conservation_errors
                ext_conf = min(ext_conf, 0.6)
            summary = compute_summary_from_units(fg)
            validated.update(summary)
            validated["_fine_grained"] = {
                "scoring_units": [s.model_dump() if hasattr(s, 'model_dump') else s for s in fg.scoring_units],
                "diagnostic_units": [d.model_dump() if hasattr(d, 'model_dump') else d for d in fg.diagnostic_units],
                "stimulus_units": [s.model_dump() if hasattr(s, 'model_dump') else s for s in fg.stimulus_units],
            }
            validated["_extraction_confidence"] = ext_conf
            validated["_analysis_version"] = "v2_ultra_compact_retry"
            if val_errors:
                validated["_validation_errors"] = val_errors
            validated = attach_call_record(
                validated,
                "FineGrainedResult",
                ext_conf,
                val_errors,
                existing_calls=initial_calls,
                prompt_id="biology.question_analysis.v2.ultra_compact_retry",
                prompt_hash_value=ultra_prompt_hash,
                response_len=ultra_response_length,
                call_suffix="analysis-ultra-compact-retry",
                retry_count=retry_count,
                metadata_extra={
                    "initial_error": initial_reason,
                    "initial_provider_errors": provider_errors_before,
                    "normalization_notes": normalization_notes,
                    "recovery_mode": "ultra_compact_v2",
                    "recovery_status": "ok" if not val_errors else "validation_warnings",
                    "input_trim": {
                        "visual_context_chars": min(len(visual_context_text or ""), 600),
                        "question_text_chars": min(len(question_text or ""), 2200),
                    },
                },
            )
            logger.info(
                f"[分析] 题目{question_id} ultra-compact v2 重试完成 "
                f"(confidence={ext_conf}, conserved={is_conserved}, SEU={len(fg.scoring_units)}, "
                f"DU={len(fg.diagnostic_units)}, SU={len(fg.stimulus_units)})"
            )
            return await self._retry_missing_evidence_units(
                analysis_payload=validated,
                question_id=question_id,
                question_type=question_type,
                section_header=section_header,
                question_text=question_text,
                question_media_items=question_media_items,
                visual_context_text=visual_context_text,
                timeout=analysis_timeout,
            )

        async def _micro_compact_analysis_retry(initial_reason: str, retry_count: int = 3) -> dict:
            logger.warning(f"[分析] 题目{question_id} 触发 micro-compact v2 重试: {initial_reason}")
            provider_errors_before = _last_provider_error_messages()
            micro_prompt = self._get_micro_compact_analysis_retry_prompt(
                question_type=question_type,
                section_header=section_header,
                total_score=_infer_fallback_total_score(),
            )
            micro_prompt_hash = sha256(micro_prompt.encode("utf-8")).hexdigest()
            micro_timeout = min(max(analysis_timeout, 100.0), 140.0)
            try:
                micro_response = await asyncio.wait_for(
                    llm_call(
                        messages=_question_messages(
                            "\n\n".join(
                                part for part in [
                                    micro_prompt,
                                    visual_context_text[:300],
                                    f"Question content:\n{question_text[:1200]}",
                                ]
                                if part
                            ),
                            [],
                        ),
                        max_tokens=2048,
                        temperature=0,
                        timeout=micro_timeout,
                        purpose="question_analysis_retry",
                    ),
                    timeout=micro_timeout + 5.0,
                )
            except Exception as micro_exc:
                if _should_attempt_skeletal_fine_grained_retry():
                    return await _skeletal_fine_grained_retry(
                        f"{initial_reason}; micro_compact_retry_failed: {micro_exc}",
                        retry_count=retry_count + 1,
                    )
                return await _minimal_analysis_retry(
                    f"{initial_reason}; micro_compact_retry_failed: {micro_exc}",
                    retry_count=retry_count + 1,
                )

            micro_response_length = len(micro_response) if micro_response else 0
            micro_json = self.extract_json(micro_response)
            if not micro_json.startswith('{'):
                start = micro_json.find('{')
                if start != -1:
                    micro_json = micro_json[start:]
            if not micro_json.endswith('}'):
                end = micro_json.rfind('}')
                if end != -1:
                    micro_json = micro_json[:end + 1]
            try:
                micro_result = json.loads(micro_json)
                micro_result, normalization_notes = self._normalize_fine_grained_result(micro_result)
                from llm_schemas import (FineGrainedResult, validate_llm_output,
                                         compute_summary_from_units, validate_score_conservation)
                validated, ext_conf, val_errors = validate_llm_output(
                    micro_result,
                    FineGrainedResult,
                    f"题目{question_id} micro compact v2",
                )
                fg = FineGrainedResult(**validated)
            except Exception as micro_parse_exc:
                return await _minimal_analysis_retry(
                    f"{initial_reason}; micro_compact_retry_parse_failed: {micro_parse_exc}",
                    retry_count=retry_count + 1,
                )

            expected_total_score = fg.total_score if isinstance(fg.total_score, (int, float)) and fg.total_score > 0 else None
            if expected_total_score is None:
                is_conserved = False
                conservation_errors = ["fine_grained total_score missing_or_non_positive"]
            else:
                is_conserved, conservation_errors = validate_score_conservation(fg, expected_total_score)
            if not is_conserved:
                val_errors = (val_errors or []) + conservation_errors
                ext_conf = min(ext_conf, 0.6)
            summary = compute_summary_from_units(fg)
            validated.update(summary)
            validated["_fine_grained"] = {
                "scoring_units": [s.model_dump() if hasattr(s, 'model_dump') else s for s in fg.scoring_units],
                "diagnostic_units": [d.model_dump() if hasattr(d, 'model_dump') else d for d in fg.diagnostic_units],
                "stimulus_units": [s.model_dump() if hasattr(s, 'model_dump') else s for s in fg.stimulus_units],
            }
            validated["_extraction_confidence"] = ext_conf
            validated["_analysis_version"] = "v2_micro_compact_retry"
            if val_errors:
                validated["_validation_errors"] = val_errors
            validated = attach_call_record(
                validated,
                "FineGrainedResult",
                ext_conf,
                val_errors,
                existing_calls=initial_calls,
                prompt_id="biology.question_analysis.v2.micro_compact_retry",
                prompt_hash_value=micro_prompt_hash,
                response_len=micro_response_length,
                call_suffix="analysis-micro-compact-retry",
                retry_count=retry_count,
                metadata_extra={
                    "initial_error": initial_reason,
                    "initial_provider_errors": provider_errors_before,
                    "normalization_notes": normalization_notes,
                    "recovery_mode": "micro_compact_v2",
                    "recovery_status": "ok" if not val_errors else "validation_warnings",
                    "input_trim": {
                        "visual_context_chars": min(len(visual_context_text or ""), 300),
                        "question_text_chars": min(len(question_text or ""), 1200),
                    },
                },
            )
            logger.info(
                f"[分析] 题目{question_id} micro-compact v2 重试完成 "
                f"(confidence={ext_conf}, conserved={is_conserved}, SEU={len(fg.scoring_units)}, "
                f"DU={len(fg.diagnostic_units)}, SU={len(fg.stimulus_units)})"
            )
            return await self._retry_missing_evidence_units(
                analysis_payload=validated,
                question_id=question_id,
                question_type=question_type,
                section_header=section_header,
                question_text=question_text,
                question_media_items=question_media_items,
                visual_context_text=visual_context_text,
                timeout=analysis_timeout,
            )

        def _should_attempt_skeletal_fine_grained_retry() -> bool:
            qtype = str(question_type or "").lower()
            is_choice = qtype in {"single_choice", "multiple_choice"} or "选择" in str(question_type or "")
            has_media = bool(question_media_items)
            total_score = _infer_fallback_total_score()
            if is_choice:
                return has_media and (total_score >= 4 or len(question_text or "") >= 240)
            return total_score >= 8 or len(question_text or "") >= 800

        def _short_text(value, limit: int, default: str = "") -> str:
            text = " ".join(str(value or "").strip().split())
            return (text or default)[:limit]

        def _short_list(value, limit: int, fallback: list[str], item_limit: int = 10) -> list[str]:
            if isinstance(value, str):
                raw_items = re.split(r"[、,，;；/\n]+", value)
            elif isinstance(value, list):
                raw_items = value
            else:
                raw_items = []
            items = []
            for item in raw_items:
                text = _short_text(item, item_limit)
                if text and text not in items:
                    items.append(text)
            for item in fallback:
                text = _short_text(item, item_limit)
                if len(items) >= limit:
                    break
                if text and text not in items:
                    items.append(text)
            return items[:limit]

        def _canonical_skeletal_knowledge_points(raw_points: list[str]) -> list[str]:
            points = raw_points or _fallback_knowledge_points()
            try:
                from analysis_calibration import canonicalize_knowledge_point, is_non_textbook_skill_point
                from knowledge_mapper import KnowledgeMapper

                mapper = KnowledgeMapper()
                canonical_points = []
                for point in points:
                    if is_non_textbook_skill_point(point):
                        continue
                    canonical, _ = canonicalize_knowledge_point(point, knowledge_mapper=mapper)
                    if canonical and canonical not in canonical_points:
                        canonical_points.append(canonical)
                return canonical_points or points
            except Exception:
                return points

        def _difficulty_label(value) -> str:
            text = str(value or "").strip().lower()
            if "困难" in text or "hard" in text or "difficult" in text or text in {"高", "难"}:
                return "困难"
            if "简单" in text or "easy" in text or text in {"低", "simple"}:
                return "简单"
            return "中等"

        def _difficulty_estimate(label: str) -> float:
            if label == "困难":
                return 8.8
            if label == "简单":
                return 4.2
            return 6.8

        def _bloom_level(value, difficulty_label_value: str) -> int:
            try:
                bloom = int(float(value))
            except (TypeError, ValueError):
                bloom = 5 if difficulty_label_value == "困难" else 4
            return max(1, min(6, bloom))

        async def _skeletal_fine_grained_retry(initial_reason: str, retry_count: int = 5) -> dict:
            logger.warning(f"[分析] 题目{question_id} 触发 skeletal fine-grained 重试: {initial_reason}")
            provider_errors_before = _last_provider_error_messages()
            skeletal_prompt = (
                "你是 DeepSeek V4 Pro。前序输出过长；现在只做极短审题恢复。\n"
                "只输出一行 JSON，禁止 markdown/解释/完整答案/逐小问展开，总长度必须小于220个汉字。\n"
                "字段只能是：{\"k\":[\"教材点1\",\"教材点2\",\"教材点3\"],\"d\":\"困难\","
                "\"b\":5,\"l\":[\"点1\",\"点2\",\"点3\"],\"t\":\"误区\",\"s\":\"材料\","
                "\"a\":\"\",\"r\":\"短评\"}\n"
                "k 为教材知识点，l 恰好3个采分标签；所有字符串不超过8个汉字；a 可为空。\n"
                f"分节：{section_header or '未知'}；题型：{question_type}。\n"
                f"视觉线索：{visual_context_text[:120]}\n"
                f"题干：{question_text[:500]}"
            )
            skeletal_prompt_hash = sha256(skeletal_prompt.encode("utf-8")).hexdigest()
            skeletal_timeout = min(max(analysis_timeout, 80.0), 120.0)
            try:
                skeletal_response = await asyncio.wait_for(
                    llm_call(
                        messages=_question_messages(skeletal_prompt, []),
                        max_tokens=1536,
                        temperature=0,
                        timeout=skeletal_timeout,
                        purpose="question_analysis_retry",
                    ),
                    timeout=skeletal_timeout + 5.0,
                )
            except Exception as skeletal_exc:
                return await _deterministic_length_recovery(
                    f"{initial_reason}; skeletal_retry_failed: {skeletal_exc}",
                    retry_count=retry_count + 1,
                )

            skeletal_response_length = len(skeletal_response) if skeletal_response else 0
            try:
                skeletal_json = self.extract_json(skeletal_response)
                if not skeletal_json.startswith('{'):
                    start = skeletal_json.find('{')
                    if start != -1:
                        skeletal_json = skeletal_json[start:]
                if not skeletal_json.endswith('}'):
                    end = skeletal_json.rfind('}')
                    if end != -1:
                        skeletal_json = skeletal_json[:end + 1]
                skeletal = json.loads(skeletal_json)
            except Exception as skeletal_parse_exc:
                return await _deterministic_length_recovery(
                    f"{initial_reason}; skeletal_retry_parse_failed: {skeletal_parse_exc}",
                    retry_count=retry_count + 1,
                )

            diff_label = _difficulty_label(skeletal.get("d") or skeletal.get("diff") or skeletal.get("difficulty"))
            bloom = _bloom_level(skeletal.get("b") or skeletal.get("bloom") or skeletal.get("bloom_level"), diff_label)
            knowledge_points = _canonical_skeletal_knowledge_points(
                _short_list(
                    skeletal.get("k") or skeletal.get("kp") or skeletal.get("knowledge_points"),
                    3,
                    _fallback_knowledge_points() or ["遗传的基本规律", "基因突变", "基因表达与性状的关系"],
                    item_limit=18,
                )
            )
            labels = _short_list(
                skeletal.get("l") or skeletal.get("labels") or skeletal.get("scoring_labels"),
                3,
                knowledge_points + ["证据定位", "机制分析", "综合评价"],
                item_limit=8,
            )
            trap = _short_text(skeletal.get("t") or skeletal.get("trap") or skeletal.get("mistake"), 12, "证据混淆")
            stimulus = _short_text(skeletal.get("s") or skeletal.get("stimulus"), 14, "题干材料")
            answer = _short_text(skeletal.get("a") or skeletal.get("answer"), 20, "")
            analysis_brief = _short_text(skeletal.get("r") or skeletal.get("analysis"), 28, "长题压缩审题恢复")
            total_score = int(round(_infer_fallback_total_score()))
            diff_estimate = _difficulty_estimate(diff_label)
            shares = [0.34, 0.33, 0.33]
            scoring_units = []
            for index, share in enumerate(shares):
                kp = knowledge_points[min(index, len(knowledge_points) - 1)]
                scoring_units.append(
                    {
                        "seu_id": f"seu_{index + 1}",
                        "label": labels[index],
                        "score_share": share,
                        "allocation_source": "inferred",
                        "allocation_confidence": 0.65,
                        "knowledge_links": [{"knowledge_point": kp, "share": 1.0}],
                        "bloom_level": bloom,
                        "competency_weights": {
                            "生命观念": 0.15,
                            "科学思维": 0.55,
                            "科学探究": 0.25,
                            "社会责任": 0.05,
                        },
                        "difficulty_estimate": min(10.0, diff_estimate + (0.2 if index == 2 else 0.0)),
                        "reasoning_brief": labels[index],
                    }
                )
            skeletal_result = {
                "scoring_units": scoring_units,
                "diagnostic_units": [
                    {
                        "du_id": "du_1",
                        "option_or_trap": "trap_1",
                        "distractor_type": "reading_trap",
                        "misconception": trap,
                        "trap_strength": 3 if diff_label == "困难" else 2,
                        "knowledge_boundary": knowledge_points[0],
                        "if_selected_means": [trap],
                    }
                ],
                "stimulus_units": [
                    {
                        "su_id": "su_1",
                        "stimulus_type": "multi" if question_media_items else "text",
                        "complexity": 3 if diff_label == "困难" else 2,
                        "is_core": True,
                        "description": stimulus,
                    }
                ],
                "answer": answer,
                "total_score": total_score,
                "detailed_analysis": analysis_brief,
                "difficulty": diff_label,
                "knowledge_points": knowledge_points,
                "common_mistakes": [trap],
            }

            from llm_schemas import (
                FineGrainedResult,
                compute_summary_from_units,
                validate_llm_output,
                validate_score_conservation,
            )

            skeletal_result, normalization_notes = self._normalize_fine_grained_result(skeletal_result)
            validated, ext_conf, val_errors = validate_llm_output(
                skeletal_result,
                FineGrainedResult,
                f"题目{question_id} skeletal fine-grained retry",
            )
            fg = FineGrainedResult(**validated)
            is_conserved, conservation_errors = validate_score_conservation(fg, fg.total_score)
            if not is_conserved:
                val_errors = (val_errors or []) + conservation_errors
                ext_conf = min(ext_conf, 0.6)
            summary = compute_summary_from_units(fg)
            validated.update(summary)
            validated["_fine_grained"] = {
                "scoring_units": [s.model_dump() if hasattr(s, 'model_dump') else s for s in fg.scoring_units],
                "diagnostic_units": [d.model_dump() if hasattr(d, 'model_dump') else d for d in fg.diagnostic_units],
                "stimulus_units": [s.model_dump() if hasattr(s, 'model_dump') else s for s in fg.stimulus_units],
            }
            validated["_extraction_confidence"] = min(ext_conf, 0.85)
            validated["_analysis_version"] = "v2_skeletal_fine_grained_retry"
            if val_errors:
                validated["_validation_errors"] = val_errors
            logger.info(
                f"[分析] 题目{question_id} skeletal fine-grained 重试完成 "
                f"(confidence={validated['_extraction_confidence']}, SEU={len(fg.scoring_units)})"
            )
            return attach_call_record(
                validated,
                "FineGrainedResult",
                validated["_extraction_confidence"],
                val_errors,
                existing_calls=initial_calls,
                prompt_id="biology.question_analysis.v2.skeletal_fine_grained_retry",
                prompt_hash_value=skeletal_prompt_hash,
                response_len=skeletal_response_length,
                call_suffix="analysis-skeletal-fine-grained-retry",
                retry_count=retry_count,
                metadata_extra={
                    "initial_error": initial_reason,
                    "initial_provider_errors": provider_errors_before,
                    "normalization_notes": normalization_notes,
                    "recovery_mode": "llm_guided_skeletal_fine_grained",
                    "recovery_status": "ok" if not val_errors else "validation_warnings",
                    "input_trim": {
                        "visual_context_chars": min(len(visual_context_text or ""), 240),
                        "question_text_chars": min(len(question_text or ""), 900),
                    },
                },
            )

        async def _minimal_analysis_retry(initial_reason: str, retry_count: int = 1) -> dict:
            logger.warning(f"[分析] 题目{question_id} 触发 minimal JSON 重试: {initial_reason}")
            provider_errors_before = _last_provider_error_messages()
            minimal_prompt = (
                "You are the DeepSeek primary reviewer for a high-school biology exam item.\n"
                "Return ONLY one compact JSON object. Do not include markdown or extra text.\n"
                "Required keys: knowledge_points, detailed_analysis, difficulty, common_mistakes, "
                "answer, total_score, bloom_level.\n"
                "Do not include scoring_units, diagnostic_units, stimulus_units, sub_questions, tables, or explanations outside JSON.\n"
                "Limits: knowledge_points <= 5 short strings; common_mistakes <= 3 short strings; "
                "detailed_analysis <= 120 Chinese characters; answer <= 80 Chinese characters; "
                "difficulty must be one of 简单, 中等, 困难; bloom_level must be an integer 1-6.\n"
                f"Section: {section_header or 'unknown'}\n"
                f"Question type: {question_type}\n"
                f"Visual context, if any:\n{visual_context_text[:1200]}\n"
                f"Question content:\n{question_text[:3500]}"
            )
            minimal_prompt_hash = sha256(minimal_prompt.encode("utf-8")).hexdigest()
            minimal_timeout = min(max(analysis_timeout, 150.0), 180.0)
            try:
                minimal_response = await asyncio.wait_for(
                    llm_call(
                        messages=_question_messages(minimal_prompt, []),
                        max_tokens=3072,
                        temperature=0,
                        timeout=minimal_timeout,
                        purpose="question_analysis_retry",
                    ),
                    timeout=minimal_timeout + 5.0,
                )
            except Exception as minimal_exc:
                if _should_attempt_skeletal_fine_grained_retry():
                    return await _skeletal_fine_grained_retry(
                        f"{initial_reason}; minimal_retry_failed: {minimal_exc}",
                        retry_count=retry_count + 1,
                    )
                return await _deterministic_length_recovery(
                    f"{initial_reason}; minimal_retry_failed: {minimal_exc}",
                    retry_count=retry_count + 1,
                )
            minimal_response_length = len(minimal_response) if minimal_response else 0
            minimal_json = self.extract_json(minimal_response)
            if not minimal_json.startswith('{'):
                start = minimal_json.find('{')
                if start != -1:
                    minimal_json = minimal_json[start:]
            if not minimal_json.endswith('}'):
                end = minimal_json.rfind('}')
                if end != -1:
                    minimal_json = minimal_json[:end + 1]
            minimal_result = json.loads(minimal_json)
            from llm_schemas import validate_llm_output, AnalysisResult
            result, ext_conf, val_errors = validate_llm_output(
                minimal_result,
                AnalysisResult,
                f"题目{question_id} minimal length retry",
            )
            result["_extraction_confidence"] = ext_conf
            result["_analysis_version"] = "v1_length_recovery"
            result["_fine_grained"] = {
                "scoring_units": [],
                "diagnostic_units": [],
                "stimulus_units": [],
            }
            if val_errors:
                result["_validation_errors"] = val_errors
            logger.info(f"[分析] 题目{question_id} minimal JSON 重试完成 (confidence={ext_conf})")
            result = attach_call_record(
                result,
                "AnalysisResult",
                ext_conf,
                val_errors,
                existing_calls=initial_calls,
                prompt_id="biology.question_analysis.v1.length_recovery",
                prompt_hash_value=minimal_prompt_hash,
                response_len=minimal_response_length,
                call_suffix="analysis-length-recovery",
                retry_count=retry_count,
                metadata_extra={
                    "initial_error": initial_reason,
                    "initial_provider_errors": provider_errors_before,
                    "recovery_mode": "minimal_json",
                    "recovery_status": "ok" if not val_errors else "validation_warnings",
                },
            )
            return await self._retry_missing_evidence_units(
                analysis_payload=result,
                question_id=question_id,
                question_type=question_type,
                section_header=section_header,
                question_text=question_text,
                question_media_items=question_media_items,
                visual_context_text=visual_context_text,
                timeout=analysis_timeout,
            )

        try:
            logger.debug(f"[分析] 准备调用 llm_call 分析题目{question_id}")
            logger.debug(f"[分析] 请求包含 {len(question_media_items)} 张图片")
            if question_images:
                total_img_size = sum(len(img) for img in question_images if img)
                logger.debug(f"[分析] 图片总大小: {total_img_size / 1024:.2f} KB")

            response_text = await asyncio.wait_for(
                llm_call(
                    messages=_question_messages(full_prompt, []),
                    max_tokens=analysis_max_tokens,
                    temperature=0,
                    timeout=analysis_timeout,
                    purpose="question_analysis",
                ),
                timeout=analysis_timeout + 10.0,
            )
            finish_reason = "stop"  # fallback 客户端已处理截断重试

            response_length = len(response_text) if response_text else 0
            logger.info(f"[分析] 题目{question_id} API响应长度: {response_length}")
            logger.debug(f"[分析] 题目{question_id} 完成原因: {finish_reason}")
            logger.info(f"[分析] 题目{question_id} 原始返回:\n{response_text[:500]}")  # 只显示前500字符

            # 检查是否被截断
            if finish_reason == 'length':
                logger.error(f"[分析] 题目{question_id} 内容被截断！响应长度: {response_length}")
                logger.warning(f"[分析] 建议：如果经常出现截断，请优化prompt或增加max_tokens")
                raise RuntimeError(f"question analysis truncated: question {question_id}")

            # 检查返回是否为空
            if not response_text or response_text.strip() == "":
                logger.error(f"[分析] 题目{question_id} API返回为空！")
                raise ValueError(f"题目{question_id} API返回内容为空")

            # 提取并解析JSON（兜底：找最外层 { ... }）
            json_text = self.extract_json(response_text)
            if not json_text.startswith('{'):
                start = json_text.find('{')
                if start != -1:
                    json_text = json_text[start:]
            if not json_text.endswith('}'):
                end = json_text.rfind('}')
                if end != -1:
                    json_text = json_text[:end + 1]
            logger.debug(f"[分析] 题目{question_id} 提取的JSON前500字符:\n{json_text[:500]}")

            try:
                result = json.loads(json_text)
                v2_fallback_errors = []

                if use_v2 and not result.get("scoring_units"):
                    raise ValueError("v2_structured_analysis_missing_scoring_units")

                if use_v2 and result.get("scoring_units"):
                    # v2 细粒度解析路径（F-001 修复：全链路 try/except 保证 fallback）
                    try:
                        from llm_schemas import (FineGrainedResult, validate_llm_output,
                                                 compute_summary_from_units, validate_score_conservation)
                        result, normalization_notes = self._normalize_fine_grained_result(result)
                        normalization_metadata = result.get("_normalization_metadata") or {}
                        # R2-001 修复：在 Pydantic 归一化前检查原始 score_share
                        raw_seus = result.get("scoring_units", [])
                        score_share_penalty = 0
                        if isinstance(raw_seus, list) and raw_seus:
                            raw_share_sum = normalization_metadata.get("score_share_sum_normalized_from")
                            if raw_share_sum is None:
                                raw_share_sum = sum(s.get("score_share", 0) for s in raw_seus if isinstance(s, dict))
                            deviation = abs(raw_share_sum - 1.0)
                            if deviation > 0.05:
                                logger.warning(f"[分析] 题目{question_id} 原始 score_share 总和={raw_share_sum:.3f}，偏离 1.0")
                                if deviation > 0.3:
                                    logger.warning(f"[分析] 题目{question_id} 偏差>{0.3}，v2 不可信，fallback 到 v1")
                                    raise ValueError(f"score_share 偏差过大: {raw_share_sum:.3f}")
                                score_share_penalty = min(deviation * 0.5, 0.2)

                        validated, ext_conf, val_errors = validate_llm_output(result, FineGrainedResult, f"题目{question_id} v2")
                        if score_share_penalty > 0:
                            ext_conf = max(0.5, ext_conf - score_share_penalty)
                        if ext_conf >= 0.5:
                            fg = FineGrainedResult(**validated)
                            expected_total_score = fg.total_score if isinstance(fg.total_score, (int, float)) and fg.total_score > 0 else None
                            if expected_total_score is None:
                                is_conserved = False
                                conservation_errors = ["fine_grained total_score missing_or_non_positive"]
                            else:
                                is_conserved, conservation_errors = validate_score_conservation(fg, expected_total_score)
                            if not is_conserved:
                                logger.warning(f"[分析] 题目{question_id} 分值守恒检查失败: {conservation_errors}")
                                val_errors = (val_errors or []) + conservation_errors
                                ext_conf = min(ext_conf, 0.6)
                            # 记录未被归一化的偏差（审计用）；近似偏差写入 call metadata，不作为解析失败。
                            if isinstance(raw_seus, list) and raw_seus and not normalization_metadata.get("score_share_sum_normalized_from"):
                                raw_sum = sum(s.get("score_share", 0) for s in raw_seus if isinstance(s, dict))
                                if abs(raw_sum - 1.0) > 0.02:
                                    val_errors = (val_errors or []) + [f"原始 score_share 总和={raw_sum:.3f}，未归一化"]
                            summary = compute_summary_from_units(fg)
                            validated.update(summary)
                            validated["_fine_grained"] = {
                                "scoring_units": [s.model_dump() if hasattr(s, 'model_dump') else s for s in fg.scoring_units],
                                "diagnostic_units": [d.model_dump() if hasattr(d, 'model_dump') else d for d in fg.diagnostic_units],
                                "stimulus_units": [s.model_dump() if hasattr(s, 'model_dump') else s for s in fg.stimulus_units],
                            }
                            validated["_extraction_confidence"] = ext_conf
                            validated["_analysis_version"] = "v2"
                            if val_errors:
                                validated["_validation_errors"] = val_errors
                            logger.info(f"[分析] 题目{question_id} v2分析完成 (confidence={ext_conf}, conserved={is_conserved}, SEU={len(fg.scoring_units)}, DU={len(fg.diagnostic_units)})")
                            metadata_extra = {"normalization_notes": normalization_notes} if normalization_notes else {}
                            if normalization_metadata:
                                metadata_extra["normalization_metadata"] = normalization_metadata
                            if not metadata_extra:
                                metadata_extra = None
                            validated = attach_call_record(
                                validated,
                                "FineGrainedResult",
                                ext_conf,
                                val_errors,
                                existing_calls=initial_calls,
                                metadata_extra=metadata_extra,
                            )
                            validated = await self._retry_missing_evidence_units(
                                analysis_payload=validated,
                                question_id=question_id,
                                question_type=question_type,
                                section_header=section_header,
                                question_text=question_text,
                                question_media_items=question_media_items,
                                visual_context_text=visual_context_text,
                                timeout=analysis_timeout,
                            )
                            return validated
                        else:
                            logger.warning(f"[分析] 题目{question_id} v2解析置信度过低({ext_conf})，fallback到v1校验")
                            v2_fallback_errors.append(f"v2_low_confidence:{ext_conf}")
                    except Exception as v2_err:
                        logger.warning(f"[分析] 题目{question_id} v2解析异常，fallback到v1: {v2_err}")
                        v2_fallback_errors.append(f"v2_exception:{v2_err}")

                # v1 解析路径（fallback 或原始 v1 prompt）
                from llm_schemas import validate_llm_output, AnalysisResult
                is_v2_fallback = use_v2 and result.get("scoring_units") is not None
                result, ext_conf, val_errors = validate_llm_output(result, AnalysisResult, f"题目{question_id}")
                if v2_fallback_errors:
                    val_errors = (val_errors or []) + v2_fallback_errors
                    result["_fallback_from_v2"] = True
                if is_v2_fallback:
                    v1_critical = ["knowledge_points", "detailed_analysis"]
                    missing = [f for f in v1_critical if not result.get(f)]
                    if missing:
                        ext_conf = min(ext_conf, 0.4)
                        val_errors = (val_errors or []) + [f"v2 fallback 后 v1 关键字段缺失: {missing}"]
                        logger.warning(f"[分析] 题目{question_id} v2 fallback 后关键字段缺失: {missing}")
                result["_extraction_confidence"] = ext_conf
                result["_analysis_version"] = "v1_from_v2_fallback" if v2_fallback_errors else "v1"
                if val_errors:
                    result["_validation_errors"] = val_errors
                logger.info(f"[分析] 题目{question_id} 分析完成 (extraction_confidence={ext_conf})")
                result = attach_call_record(
                    result,
                    "AnalysisResult",
                    ext_conf,
                    val_errors,
                    existing_calls=initial_calls,
                )
                return result
            except json.JSONDecodeError as json_err:
                logger.error(f"[分析] 题目{question_id} JSON解析失败: {str(json_err)}")
                logger.error(f"[分析] 问题JSON末尾500字符:\n{json_text[-500:]}")

                # 如果是因为截断导致的 JSON 格式错误，直接报错，避免生成伪分析。
                if finish_reason == 'length':
                    raise RuntimeError(f"question analysis truncated: question {question_id}")
                if use_v2:
                    logger.warning(f"[分析] 题目{question_id} 尝试 compact v2 prompt 重试")
                    compact_prompt = self._get_compact_analysis_retry_prompt(
                        question_type=question_type,
                        section_header=section_header,
                    )
                    compact_prompt_hash = sha256(compact_prompt.encode("utf-8")).hexdigest()
                    compact_prompt_id = "biology.question_analysis.v2.json_repair"
                    json_repair_timeout = min(max(analysis_timeout, 150.0), 180.0)
                    json_repair_max_tokens = min(analysis_max_tokens, 4096)
                    compact_response = await asyncio.wait_for(
                        llm_call(
                            messages=_question_messages(
                                "\n\n".join(
                                    part for part in [
                                        compact_prompt,
                                        visual_context_text[:1500],
                                        f"题目内容：\n{question_text[:3500]}",
                                    ]
                                    if part
                                ),
                                [],
                            ),
                            max_tokens=json_repair_max_tokens,
                            temperature=0,
                            timeout=json_repair_timeout,
                            purpose="question_analysis_retry",
                        ),
                        timeout=json_repair_timeout + 5.0,
                    )
                    compact_response_length = len(compact_response) if compact_response else 0
                    compact_json = self.extract_json(compact_response)
                    if not compact_json.startswith('{'):
                        start = compact_json.find('{')
                        if start != -1:
                            compact_json = compact_json[start:]
                    if not compact_json.endswith('}'):
                        end = compact_json.rfind('}')
                        if end != -1:
                            compact_json = compact_json[:end + 1]

                    compact_result = json.loads(compact_json)
                    compact_result, normalization_notes = self._normalize_fine_grained_result(compact_result)
                    from llm_schemas import (FineGrainedResult, validate_llm_output,
                                             compute_summary_from_units, validate_score_conservation)
                    validated, ext_conf, val_errors = validate_llm_output(
                        compact_result,
                        FineGrainedResult,
                        f"题目{question_id} compact v2",
                    )
                    fg = FineGrainedResult(**validated)
                    expected_total_score = fg.total_score if isinstance(fg.total_score, (int, float)) and fg.total_score > 0 else None
                    if expected_total_score is None:
                        is_conserved = False
                        conservation_errors = ["fine_grained total_score missing_or_non_positive"]
                    else:
                        is_conserved, conservation_errors = validate_score_conservation(fg, expected_total_score)
                    if not is_conserved:
                        val_errors = (val_errors or []) + conservation_errors
                        ext_conf = min(ext_conf, 0.6)
                    summary = compute_summary_from_units(fg)
                    validated.update(summary)
                    validated["_fine_grained"] = {
                        "scoring_units": [s.model_dump() if hasattr(s, 'model_dump') else s for s in fg.scoring_units],
                        "diagnostic_units": [d.model_dump() if hasattr(d, 'model_dump') else d for d in fg.diagnostic_units],
                        "stimulus_units": [s.model_dump() if hasattr(s, 'model_dump') else s for s in fg.stimulus_units],
                    }
                    validated["_extraction_confidence"] = ext_conf
                    validated["_analysis_version"] = "v2_json_repair"
                    if val_errors:
                        validated["_validation_errors"] = val_errors
                    logger.info(f"[分析] 题目{question_id} compact v2 重试完成 (confidence={ext_conf}, conserved={is_conserved}, SEU={len(fg.scoring_units)})")
                    validated = attach_call_record(
                        validated,
                        "FineGrainedResult",
                        ext_conf,
                        val_errors,
                        existing_calls=initial_calls,
                        prompt_id=compact_prompt_id,
                        prompt_hash_value=compact_prompt_hash,
                        response_len=compact_response_length,
                        call_suffix="analysis-repair",
                        retry_count=1,
                        metadata_extra={
                            "initial_parse_error": str(json_err),
                            "initial_response_length": response_length,
                            "normalization_notes": normalization_notes,
                        },
                    )
                    validated = await self._retry_missing_evidence_units(
                        analysis_payload=validated,
                        question_id=question_id,
                        question_type=question_type,
                        section_header=section_header,
                        question_text=question_text,
                        question_media_items=question_media_items,
                        visual_context_text=visual_context_text,
                        timeout=analysis_timeout,
                    )
                    return validated

                # 非截断导致的JSON错误，继续抛出
                raise

        except json.JSONDecodeError as e:
            logger.error(f"[分析] 题目{question_id} JSON解析失败（外层捕获）: {e}")
            raise
        except Exception as e:
            if use_v2 and (isinstance(e, asyncio.TimeoutError) or _is_length_provider_failure(e)):
                try:
                    _split_result = await _split_merge_analysis(str(e))
                except Exception as _sm_exc:
                    logger.warning(f"[分析] 题目{question_id} split-merge 顶层异常 {_sm_exc}，回退阶梯")
                    _split_result = None
                if _split_result is not None:
                    return _split_result
                return await _compact_analysis_retry(str(e))
            logger.error(f"[分析] 题目{question_id} API调用失败: {str(e)}", exc_info=True)
            raise

    @staticmethod
    def _needs_evidence_units(payload: dict, question_type: str = "unknown") -> bool:
        if not isinstance(payload, dict):
            return False
        fine_grained = payload.get("_fine_grained") if isinstance(payload.get("_fine_grained"), dict) else payload
        total_score = payload.get("total_score") or fine_grained.get("total_score") or 0
        try:
            total_score = float(total_score)
        except (TypeError, ValueError):
            total_score = 0.0
        is_big_question = total_score >= 8 or question_type in ("short_answer", "non_choice", "experiment")
        if not is_big_question:
            return False
        stimulus_units = fine_grained.get("stimulus_units") or []
        return (
            not fine_grained.get("diagnostic_units")
            or not stimulus_units
            or QuestionAnalyzer._stimulus_units_blank(stimulus_units)
        )

    @staticmethod
    def _stimulus_units_blank(units: list) -> bool:
        if not units:
            return False
        for unit in units:
            if not isinstance(unit, dict):
                return True
            description = str(unit.get("description") or "").strip()
            try:
                complexity = float(unit.get("complexity") or 0)
            except (TypeError, ValueError):
                complexity = 0.0
            if description and (bool(unit.get("is_core")) or complexity > 1):
                return False
        return True

    @staticmethod
    def _fallback_stimulus_units(
        question_text: str,
        question_media_items: list | None = None,
        visual_context_text: str = "",
    ) -> list[dict]:
        source = " ".join(str(visual_context_text or "").split())
        if not source:
            source = " ".join(str(question_text or "").split())
        description = source[:30] if source else "题干材料"
        media_types = {
            str(item.get("type") or item.get("media_type") or "").lower()
            for item in (question_media_items or [])
            if isinstance(item, dict)
        }
        if "table" in media_types:
            stimulus_type = "table"
        elif "image" in media_types or question_media_items:
            stimulus_type = "multi"
        else:
            stimulus_type = "text"
        return [
            {
                "su_id": "su_1",
                "stimulus_type": stimulus_type,
                "complexity": 3 if question_media_items else 2,
                "is_core": True,
                "description": description,
            }
        ]

    async def _retry_missing_evidence_units(
        self,
        *,
        analysis_payload: dict,
        question_id: int,
        question_type: str,
        section_header: str,
        question_text: str,
        timeout: float,
        question_media_items: list | None = None,
        visual_context_text: str = "",
    ) -> dict:
        if not self._needs_evidence_units(analysis_payload, question_type):
            return analysis_payload

        fine_grained = analysis_payload.get("_fine_grained")
        if not isinstance(fine_grained, dict):
            return analysis_payload

        prompt = self._get_evidence_units_retry_prompt(
            question_type=question_type,
            section_header=section_header,
            scoring_units=fine_grained.get("scoring_units") or [],
        )
        prompt_hash = sha256(prompt.encode("utf-8")).hexdigest()
        response_text = ""
        validation_errors = []
        confidence = 0.0

        try:
            response_text = await llm_call(
                messages=_question_messages(
                    "\n\n".join(
                        part for part in [
                            prompt,
                            visual_context_text,
                            f"题目内容：\n{question_text}",
                        ]
                        if part
                    ),
                    [],
                ),
                max_tokens=4096,
                temperature=0,
                timeout=min(timeout, 120.0),
                purpose="missing_evidence_repair",
            )
            json_text = self.extract_json(response_text)
            if not json_text.startswith('{'):
                start = json_text.find('{')
                if start != -1:
                    json_text = json_text[start:]
            if not json_text.endswith('}'):
                end = json_text.rfind('}')
                if end != -1:
                    json_text = json_text[:end + 1]
            evidence = json.loads(json_text)
            evidence, normalization_notes = self._normalize_fine_grained_result(evidence)

            from llm_schemas import DiagnosticUnit, StimulusUnit

            raw_dus = evidence.get("diagnostic_units") or []
            raw_sus = evidence.get("stimulus_units") or []
            valid_dus = []
            valid_sus = []

            for index, unit in enumerate(raw_dus):
                try:
                    valid_dus.append(DiagnosticUnit.model_validate(unit).model_dump())
                except Exception as exc:
                    validation_errors.append(f"diagnostic_units[{index}]: {exc}")

            for index, unit in enumerate(raw_sus):
                try:
                    valid_sus.append(StimulusUnit.model_validate(unit).model_dump())
                except Exception as exc:
                    validation_errors.append(f"stimulus_units[{index}]: {exc}")

            if valid_dus:
                fine_grained["diagnostic_units"] = valid_dus
                analysis_payload["diagnostic_units"] = valid_dus
            else:
                validation_errors.append("diagnostic_units_empty_after_retry")

            if valid_sus:
                fine_grained["stimulus_units"] = valid_sus
                analysis_payload["stimulus_units"] = valid_sus
            else:
                validation_errors.append("stimulus_units_empty_after_retry")

            confidence = 1.0 if valid_dus and valid_sus and not validation_errors else 0.5
            logger.info(
                f"[分析] 题目{question_id} evidence units 补充完成 "
                f"(DU={len(valid_dus)}, SU={len(valid_sus)}, confidence={confidence})"
            )
        except Exception as exc:
            validation_errors.append(str(exc))
            logger.warning(f"[分析] 题目{question_id} evidence units 补充失败: {exc}")

        current_sus = fine_grained.get("stimulus_units") or []
        if not current_sus or self._stimulus_units_blank(current_sus):
            fallback_sus = self._fallback_stimulus_units(
                question_text=question_text,
                question_media_items=question_media_items,
                visual_context_text=visual_context_text,
            )
            fine_grained["stimulus_units"] = fallback_sus
            analysis_payload["stimulus_units"] = fallback_sus
            validation_errors.append("stimulus_units_deterministic_repair")
            logger.info(f"[分析] 题目{question_id} stimulus units 确定性补齐完成")

        retry_metadata = {
            "response_length": len(response_text or ""),
            "validation_errors": validation_errors,
            "repair_attempt": 1,
            "repair_for": "question_analysis.evidence_units",
            "diagnostic_units_count": len(fine_grained.get("diagnostic_units") or []),
            "stimulus_units_count": len(fine_grained.get("stimulus_units") or []),
        }
        if 'normalization_notes' in locals() and normalization_notes:
            retry_metadata["normalization_notes"] = normalization_notes
        provider, model, fallback_count, retry_metadata = _llm_call_trace(retry_metadata)
        call = LLMCallRecord(
            call_id=f"question-{question_id}-evidence-retry",
            question_id=question_id,
            purpose="missing_evidence_repair",
            prompt_id="biology.question_analysis.v2.evidence_retry",
            prompt_hash=prompt_hash,
            provider=provider,
            model=model,
            input_refs={
                "question_id": question_id,
                "question_type": question_type,
                "section_header": section_header,
                "scoring_unit_count": len(fine_grained.get("scoring_units") or []),
                **media_input_refs(question_media_items or []),
            },
            parsed_schema="EvidenceUnitsResult",
            confidence=confidence,
            validation_errors=validation_errors,
            fallback_count=fallback_count,
            retry_count=0,
            metadata=retry_metadata,
        )
        analysis_payload.setdefault("_llm_calls", []).append(call.model_dump())
        return analysis_payload

    @staticmethod
    def _get_compact_analysis_retry_prompt(question_type: str, section_header: str = None) -> str:
        section = section_header or "未提供"
        return (
            f"分节信息：{section}\n"
            f"题型：{question_type}\n"
            "你是高中生物试题元数据分析器。上一次完整 schema 输出不可解析，现在只做紧凑重试。\n"
            "只返回一个合法 JSON 对象，不要 markdown，不要解释。\n"
            "必须包含字段：scoring_units, diagnostic_units, stimulus_units, answer, total_score, "
            "detailed_analysis, difficulty, knowledge_points, common_mistakes。\n"
            "scoring_units 输出 3-4 个，按小问或采分点合并，score_share 总和必须等于 1.0。\n"
            "每个 scoring_unit 必须包含：seu_id, label, score_share, allocation_source, "
            "allocation_confidence, knowledge_links, bloom_level, competency_weights, "
            "difficulty_estimate, reasoning_brief。\n"
            "knowledge_links 每个单元只输出 1 个，share=1.0。\n"
            "competency_weights 必须含 生命观念、科学思维、科学探究、社会责任，四项总和等于 1.0。\n"
            "knowledge_points 最多 4 个；common_mistakes 最多 2 个；answer 和 detailed_analysis 各不超过 80 个汉字。\n"
            "大题只输出 2 个 diagnostic_units 和 1 个 stimulus_units；"
            "只有选择题且确无材料时才允许 stimulus_units=[]。所有 label/reason 字段不超过 24 个汉字。"
        )

    @staticmethod
    def _get_ultra_compact_analysis_retry_prompt(question_type: str, section_header: str = None) -> str:
        section = section_header or "未提供"
        return (
            f"分节信息：{section}\n"
            f"题型：{question_type}\n"
            "你是高中生物试题元数据分析器。前两次输出过长，现在只做超短结构化恢复。\n"
            "只返回一个 minified JSON 对象，不要 markdown，不要解释，整体不超过 1500 个汉字。\n"
            "必须包含字段：scoring_units, diagnostic_units, stimulus_units, answer, total_score, "
            "detailed_analysis, difficulty, knowledge_points, common_mistakes。\n"
            "scoring_units 必须恰好 3 个，score_share 分别接近 0.34,0.33,0.33 且总和为 1.0；"
            "每个对象含 seu_id,label,score_share,allocation_source,allocation_confidence,"
            "knowledge_links,bloom_level,competency_weights,difficulty_estimate,reasoning_brief。\n"
            "knowledge_links 每个 SEU 只给 1 个，share=1.0；label 和 reasoning_brief 不超过 12 个汉字。\n"
            "diagnostic_units 必须恰好 2 个，每个含 du_id,option_or_trap,distractor_type,"
            "misconception,trap_strength,knowledge_boundary,if_selected_means；字符串不超过 12 个汉字。\n"
            "stimulus_units 必须恰好 1 个，含 su_id,stimulus_type,complexity,is_core,description；"
            "description 不超过 14 个汉字。\n"
            "competency_weights 必须含 生命观念、科学思维、科学探究、社会责任，四项总和等于 1.0。\n"
            "knowledge_points 最多 3 个；common_mistakes 最多 2 个；answer 和 detailed_analysis 各不超过 40 个汉字；"
            "difficulty 只能是 简单、中等、困难。"
        )

    @staticmethod
    def _get_micro_compact_analysis_retry_prompt(
        question_type: str,
        section_header: str = None,
        total_score: float = 0,
    ) -> str:
        section = section_header or "未提供"
        score = int(total_score) if isinstance(total_score, (int, float)) and total_score > 0 else 0
        return (
            f"分节信息：{section}\n"
            f"题型：{question_type}\n"
            f"total_score 必须填 {score}。\n"
            "前序输出太长。现在只返回一个极小 JSON，不要解释，不要 markdown，不要逐小问作答。\n"
            "整体限 900 个汉字以内；answer 可为空字符串；detailed_analysis 固定为一句短语。\n"
            "严格使用这些顶层字段：scoring_units,diagnostic_units,stimulus_units,answer,total_score,"
            "detailed_analysis,difficulty,knowledge_points,common_mistakes。\n"
            "scoring_units 恰好3个，score_share 固定为0.34,0.33,0.33；"
            "每个 SEU 只保留一个 knowledge_link，share=1.0；所有字符串不超过8个汉字。\n"
            "diagnostic_units 恰好1个；stimulus_units 恰好1个；common_mistakes 恰好1个；"
            "knowledge_points 最多3个。\n"
            "必须用数字：bloom_level=4或5，trap_strength=2或3，complexity=2或3，difficulty_estimate=7或8。"
        )

    @staticmethod
    def _get_evidence_units_retry_prompt(
        question_type: str,
        section_header: str = None,
        scoring_units: list = None,
    ) -> str:
        section = section_header or "未提供"
        scoring_units_json = json.dumps(scoring_units or [], ensure_ascii=False)
        return (
            f"分节信息：{section}\n"
            f"题型：{question_type}\n"
            "你是高中生物试题诊断元数据抽取器。已有采分单元如下：\n"
            f"{scoring_units_json}\n"
            "现在只补充诊断单元和情境单元。只返回合法 JSON 对象，不要 markdown，不要解释。\n"
            "必须包含两个字段：diagnostic_units, stimulus_units。\n"
            "diagnostic_units 输出 2-3 个，聚焦学生最可能犯的误区或卡点；"
            "每个对象必须含 du_id, option_or_trap, distractor_type, misconception, "
            "trap_strength, knowledge_boundary, if_selected_means。\n"
            "stimulus_units 输出 1-2 个，概括题干中真正参与解题的文字、图、表或实验材料；"
            "每个对象必须含 su_id, stimulus_type, complexity, is_core, description。\n"
            "所有字符串保持简短，不要补写答案，不要重复 scoring_units。"
        )


    @staticmethod
    def _get_default_split_prompt() -> str:
        return """请分析这份生物试卷，将其拆分为单独的题目。

返回纯JSON数组格式（不要markdown代码块）：
[
    {
        "id": 1,
        "content": "题目完整文本（包括选项）",
        "image_indices": [0],
        "question_type": "单选题",
        "total_score": 2
    }
]

字段说明：
- id: 题号
- content: 题目完整文本（包括选项）
- image_indices: 该题目涉及的图片页码（从0开始）
- question_type: 题型（单选题/多选题/填空题/简答题/综合题）
- total_score: 本题满分分值（从题目前后的分值标注如"(6分)"、"每小题2分"提取；无标注时选择题默认2分，非选择题默认0表示未知）

注意：
1. 确保每道题完整独立
2. 图片页码准确对应
3. 严格返回JSON格式"""

    @staticmethod
    def _get_default_analysis_prompt() -> str:
        return """请深入分析这道生物题目，返回纯JSON格式（不要markdown代码块）：

{
    "knowledge_points": ["知识点1", "知识点2"],
    "detailed_analysis": "详细解题步骤...",
    "difficulty": "简单/中等/困难",
    "common_mistakes": ["易错点1", "易错点2"],
    "answer": "标准答案"
}"""


# Backward compatibility
Analyzer = QuestionAnalyzer
