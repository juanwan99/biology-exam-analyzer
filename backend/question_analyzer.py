import json
import re
import base64
import time
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

        if "answer" in data and not isinstance(data.get("answer"), str):
            data["answer"] = json.dumps(data["answer"], ensure_ascii=False)
            notes.append("answer_object_to_json_string")

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
            "hard": 8.0, "difficult": 8.0, "困难": 8.0, "高": 8.0,
        }
        confidence_map = {
            "high": 0.85, "medium": 0.65, "low": 0.45,
            "高": 0.85, "中": 0.65, "低": 0.45,
        }

        scoring_units = data.get("scoring_units") or []
        for seu in scoring_units:
            if not isinstance(seu, dict):
                continue
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
                original = link.get("share")
                coerced = cls._coerce_float(original)
                if coerced != original:
                    link["share"] = coerced
                    notes.append("knowledge_link_share_to_float")

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

        for index, unit in enumerate(data.get("diagnostic_units") or [], 1):
            if not isinstance(unit, dict):
                continue
            if not unit.get("option_or_trap"):
                for alt_key in ("option", "trap", "label", "name", "du_id"):
                    if unit.get(alt_key):
                        unit["option_or_trap"] = str(unit[alt_key])
                        notes.append(f"{alt_key}_to_option_or_trap")
                        break
                else:
                    unit["option_or_trap"] = f"trap_{index}"
                    notes.append("option_or_trap_defaulted")
            if not unit.get("misconception"):
                for alt_key in ("label", "description", "mistake", "error"):
                    if unit.get(alt_key):
                        unit["misconception"] = str(unit[alt_key])
                        notes.append(f"{alt_key}_to_misconception")
                        break
            if not unit.get("knowledge_boundary"):
                for alt_key in ("boundary", "analysis", "explanation"):
                    if unit.get(alt_key):
                        unit["knowledge_boundary"] = str(unit[alt_key])
                        notes.append(f"{alt_key}_to_knowledge_boundary")
                        break
            means = unit.get("if_selected_means")
            if isinstance(means, str):
                unit["if_selected_means"] = [means]
                notes.append("if_selected_means_to_list")

        for index, unit in enumerate(data.get("stimulus_units") or [], 1):
            if not isinstance(unit, dict):
                continue
            if not unit.get("description"):
                for alt_key in ("label", "name", "content", "summary", "su_id"):
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
                else:
                    unit["stimulus_type"] = "text"
                    notes.append("stimulus_type_defaulted")
            original = unit.get("complexity")
            coerced = cls._coerce_float(original, {"low": 1, "medium": 2, "high": 3, "低": 1, "中": 2, "高": 3})
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
        question_media_items = _question_images_to_media_items(question_images)
        question_media_refs = media_input_refs(question_media_items)
        visual_context_text = ""
        visual_call_record = None
        analysis_timeout = 240.0 if question_type in ("short_answer", "non_choice") or len(question_text) > 500 else 120.0

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
        if _evidence_ranking_enabled(evidence_ranking_enabled):
            provider = evidence_context_provider or QuestionEvidenceContextBuilder()
            try:
                evidence_context = await provider.build_question_context(
                    question_text=question_text,
                    question_id=question_id,
                    question_type=question_type,
                    section_header=section_header,
                    agent_search_enabled=agent_search_enabled,
                )
            except Exception as exc:
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

        try:
            logger.debug(f"[分析] 准备调用 llm_call 分析题目{question_id}")
            logger.debug(f"[分析] 请求包含 {len(question_media_items)} 张图片")
            if question_images:
                total_img_size = sum(len(img) for img in question_images if img)
                logger.debug(f"[分析] 图片总大小: {total_img_size / 1024:.2f} KB")

            response_text = await llm_call(
                messages=_question_messages(full_prompt, []),
                max_tokens=12000,
                temperature=0,
                timeout=analysis_timeout,
                purpose="question_analysis",
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
                    compact_response = await llm_call(
                        messages=_question_messages(
                            "\n\n".join(
                                part for part in [
                                    compact_prompt,
                                    visual_context_text,
                                    f"题目内容：\n{question_text}",
                                ]
                                if part
                            ),
                            [],
                        ),
                        max_tokens=12000,
                        temperature=0,
                        timeout=analysis_timeout,
                        purpose="question_analysis_retry",
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
        return not fine_grained.get("diagnostic_units") or not fine_grained.get("stimulus_units")

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

        retry_metadata = {
            "response_length": len(response_text or ""),
            "validation_errors": validation_errors,
            "repair_attempt": 1,
            "repair_for": "question_analysis.evidence_units",
            "diagnostic_units_count": len(fine_grained.get("diagnostic_units") or []),
            "stimulus_units_count": len(fine_grained.get("stimulus_units") or []),
        }
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
            "scoring_units 输出 3-6 个，按小问或采分点合并，score_share 总和必须等于 1.0。\n"
            "每个 scoring_unit 必须包含：seu_id, label, score_share, allocation_source, "
            "allocation_confidence, knowledge_links, bloom_level, competency_weights, "
            "difficulty_estimate, reasoning_brief。\n"
            "knowledge_links 每个单元 1-2 个，share 总和等于 1.0。\n"
            "competency_weights 必须含 生命观念、科学思维、科学探究、社会责任，四项总和等于 1.0。\n"
            "大题必须输出 2-3 个 diagnostic_units 和 1-2 个 stimulus_units；"
            "只有选择题且确无材料时才允许 stimulus_units=[]。文本字段保持简短。"
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
