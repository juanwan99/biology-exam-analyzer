"""
核心素养分析器
基于《普通高中生物学课程标准（2017年版2020修订）》
分析题目考查的四大核心素养
"""
import json
from hashlib import sha256
from typing import Dict, List, Any
from logger import get_logger
from config import RULES_DIR, PROMPT_DIR
from llm_client import llm_call, get_last_llm_call_metadata as get_last_call_metadata
from llm_media import media_input_refs, messages_with_media
from metadata_contracts import LLMCallRecord
from vision_context import extract_visual_context

logger = get_logger()

COMPETENCY_DIMS = ["生命观念", "科学思维", "科学探究", "社会责任"]
NORMALIZABLE_WEIGHT_MIN = 0.75
NORMALIZABLE_WEIGHT_MAX = 1.25


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


def _extract_json(text: str) -> dict:
    """从 LLM 响应中提取 JSON，只做语法清理，不补造字段内容。"""
    import re
    text = text.strip()

    candidates = [text]
    candidates.extend(match.group(1).strip() for match in re.finditer(
        r'```(?:json)?\s*\n?(.*?)\n?```',
        text,
        re.DOTALL,
    ))
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start:end + 1])

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        variants = [
            candidate,
            re.sub(r",\s*([}\]])", r"\1", candidate),
        ]
        for variant in variants:
            try:
                return json.loads(variant)
            except json.JSONDecodeError:
                continue
    raise ValueError(f"无法从LLM响应中提取JSON: {text[:100]}...")


def _is_length_provider_failure(exc: Exception) -> bool:
    text = str(exc)
    return "finish_reason=length" in text or "provider_incomplete_response" in text


def _build_compact_competency_prompt(question: Dict[str, Any],
                                     visual_context_text: str = "") -> str:
    knowledge_points = ", ".join(question.get("knowledge_points", []))
    parts = [
        "你是高中生物核心素养分析器。上一次输出过长或不可解析，现在只做紧凑恢复。",
        "只返回一个合法 JSON 对象，不要 markdown，不要解释，不要省略号。",
        "必须包含：生命观念、科学思维、科学探究、社会责任、primary_competency、competency_level。",
        "四个素养对象必须包含：涉及、具体维度、权重、分析说明。",
        "权重总和必须等于 1.0；未涉及的素养用 涉及=false、具体维度=[]、权重=0、分析说明=\"\"。",
        "每个具体维度最多 2 个；分析说明不超过 35 个汉字。",
        "primary_competency 必须是权重最高的素养；competency_level 只能是 低/中/高。",
        f"题目内容：\n{str(question.get('content', ''))[:2600]}",
        f"已识别知识点：{knowledge_points[:500]}",
    ]
    if visual_context_text:
        parts.append(f"视觉信息：\n{visual_context_text[:1000]}")
    return "\n\n".join(parts)


def _parse_competency_response(response_text: str, question_id) -> tuple[dict, float, list]:
    result = _extract_json(response_text)
    from llm_schemas import validate_llm_output, CompetencyResult
    result, ext_conf, val_errors = validate_llm_output(
        result,
        CompetencyResult,
        f"素养分析 题目{question_id}",
    )
    if val_errors:
        logger.warning(f"[素养] Schema校验: {val_errors[:3]}")
    result["_extraction_confidence"] = ext_conf
    result["question_id"] = question_id
    return result, ext_conf, val_errors


def _competency_weight_sum(result: dict) -> float:
    total = 0.0
    for dim in COMPETENCY_DIMS:
        value = (result.get(dim) or {}).get("权重", 0)
        try:
            total += float(value)
        except (TypeError, ValueError):
            continue
    return total


def _normalise_competency_weights(result: dict) -> dict:
    total = _competency_weight_sum(result)
    metadata = {"total_weight_raw": round(total, 4)}
    if abs(total - 1.0) <= 0.01:
        return metadata
    if not (NORMALIZABLE_WEIGHT_MIN <= total <= NORMALIZABLE_WEIGHT_MAX):
        metadata["weight_sum_error"] = f"competency_weight_sum_mismatch:{total:.4f}"
        return metadata

    for dim in COMPETENCY_DIMS:
        payload = result.get(dim)
        if not isinstance(payload, dict):
            continue
        try:
            payload["权重"] = round(float(payload.get("权重", 0)) / total, 4)
        except (TypeError, ValueError):
            payload["权重"] = 0.0

    primary = result.get("primary_competency")
    valid_weights = {
        dim: (result.get(dim) or {}).get("权重", 0)
        for dim in COMPETENCY_DIMS
        if isinstance(result.get(dim), dict)
    }
    if primary not in COMPETENCY_DIMS and valid_weights:
        result["primary_competency"] = max(valid_weights, key=valid_weights.get)

    metadata["weight_sum_normalized_from"] = round(total, 4)
    metadata["weight_sum_normalized_to"] = round(_competency_weight_sum(result), 4)
    return metadata


class CompetencyAnalyzer:
    """核心素养分析器"""

    def __init__(
        self,
        library_path: str = None,

    ):
        """
        初始化核心素养分析器

        Args:
            library_path: 素养库JSON文件路径（默认使用config中的路径）
        """
        self.library_path = library_path or str(RULES_DIR / "competency_library.json")
        self.library = self._load_library()

        logger.info("核心素养分析器初始化完成")

    def _load_library(self) -> Dict:
        """加载素养库"""
        try:
            with open(self.library_path, 'r', encoding='utf-8') as f:
                library = json.load(f)
            logger.info(f"素养库加载成功: {self.library_path}")
            return library
        except FileNotFoundError:
            logger.error(f"素养库文件未找到: {self.library_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"素养库JSON解析失败: {e}")
            raise

    async def analyze_competency(self, question: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析题目的核心素养

        Args:
            question: {
                "id": 7,
                "content": "题目文本",
                "knowledge_points": ["遗传学", "概率计算"]
            }

        Returns:
            {
                "question_id": 7,
                "生命观念": {...},
                "科学思维": {...},
                "科学探究": {...},
                "社会责任": {...},
                "primary_competency": "科学思维",
                "competency_level": "高"
            }
        """
        logger.info(f"[素养分析] 开始分析题目 {question.get('id')}")
        prompt = ""
        response_text = ""

        try:
            # 加载Prompt
            prompt_path = str(PROMPT_DIR / "competency_analysis_prompt.txt")
            try:
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    prompt_template = f.read()
            except FileNotFoundError:
                logger.error(f"[素养分析] Prompt文件未找到: {prompt_path}")
                raise RuntimeError(f"competency prompt missing: {prompt_path}")

            # 填充Prompt
            prompt = prompt_template.format(
                question_text=question.get("content", ""),
                knowledge_points=", ".join(question.get("knowledge_points", []))
            )
            media_items = question.get("media_items") or question.get("_media_for_ai") or []
            input_refs = {
                "question_id": question.get("id"),
                "question_text_length": len(question.get("content", "") or ""),
                "knowledge_point_count": len(question.get("knowledge_points", [])),
                **media_input_refs(media_items),
            }
            visual_call_record = None
            if media_input_refs(media_items):
                visual_context_text, visual_call_record = await extract_visual_context(
                    media_items,
                    question_text=question.get("content", ""),
                    question_id=question.get("id"),
                    question_type=str(question.get("type") or question.get("question_type") or ""),
                    section_header=str(question.get("_section_header") or ""),
                    call_id=f"question-{question.get('id')}-competency-visual-context",
                )
                prompt = "\n\n".join([prompt, visual_context_text])

            # 通过统一 LLM 客户端调用；文本主审固定由 DeepSeek 路由承担。
            logger.debug(f"[素养分析] 调用LLM分析题目 {question.get('id')}")
            selected_prompt = prompt
            retry_count = 0
            recovery_metadata = {}
            try:
                response_text = await llm_call(
                    messages=messages_with_media(prompt, []),
                    max_tokens=8192,
                    temperature=0.1,
                    purpose="competency_analysis",
                )
                logger.debug(f"[素养分析] LLM响应: {response_text[:200]}...")
                result, ext_conf, val_errors = _parse_competency_response(
                    response_text,
                    question.get("id"),
                )
            except Exception as first_exc:
                if not (_is_length_provider_failure(first_exc) or response_text):
                    raise
                logger.warning(
                    f"[素养分析] 题目 {question.get('id')} 触发紧凑恢复: {first_exc}"
                )
                retry_count = 1
                recovery_metadata = {
                    "initial_error": str(first_exc)[:300],
                    "initial_response_length": len(response_text or ""),
                    "recovery_mode": "compact_json",
                    "recovery_status": "ok",
                }
                selected_prompt = _build_compact_competency_prompt(
                    question,
                    visual_context_text if visual_call_record else "",
                )
                response_text = await llm_call(
                    messages=messages_with_media(selected_prompt, []),
                    max_tokens=4096,
                    temperature=0,
                    purpose="competency_analysis",
                )
                logger.debug(f"[素养分析] 紧凑恢复响应: {response_text[:200]}...")
                result, ext_conf, val_errors = _parse_competency_response(
                    response_text,
                    question.get("id"),
                )

            weight_metadata = _normalise_competency_weights(result)
            total_weight = _competency_weight_sum(result)

            if weight_metadata.get("weight_sum_normalized_from") is not None:
                logger.warning(
                    "[素养分析] 题目 %s 权重总和 %.4f 已归一化为 %.4f",
                    question.get("id"),
                    weight_metadata["weight_sum_normalized_from"],
                    weight_metadata["weight_sum_normalized_to"],
                )
            elif abs(total_weight - 1.0) > 0.01:
                logger.warning(f"[素养分析] 题目 {question.get('id')} 权重总和异常: {total_weight}")
                val_errors = (val_errors or []) + [
                    weight_metadata.get("weight_sum_error")
                    or f"competency_weight_sum_mismatch:{total_weight:.4f}"
                ]

            call_metadata = {
                "response_length": len(response_text),
                "total_weight": round(total_weight, 4),
                "primary_competency": result.get("primary_competency"),
                **({"visual_context_source": "qwen_vision"} if visual_call_record else {}),
                **weight_metadata,
                **recovery_metadata,
            }
            provider, model, fallback_count, call_metadata = _llm_call_trace(call_metadata)
            call = LLMCallRecord(
                call_id=f"question-{question.get('id')}-competency",
                question_id=question.get("id"),
                purpose="competency_analysis",
                prompt_id="biology.competency_analysis",
                prompt_hash=sha256(selected_prompt.encode("utf-8")).hexdigest(),
                provider=provider,
                model=model,
                input_refs=input_refs,
                parsed_schema="CompetencyResult",
                confidence=ext_conf,
                validation_errors=val_errors,
                fallback_count=fallback_count,
                retry_count=retry_count,
                metadata=call_metadata,
            )
            result["_llm_calls"] = list([visual_call_record] if visual_call_record else []) + [call.model_dump()]

            logger.info(f"[素养分析] 题目 {question.get('id')} 分析完成，主要素养: {result.get('primary_competency')}")
            return result

        except Exception as e:
            logger.error(f"[素养分析] 题目 {question.get('id')} 分析失败: {str(e)}", exc_info=True)
            failure_type = "json_parse_failed" if response_text else "llm_call_failed"
            media_items = question.get("media_items") or question.get("_media_for_ai") or []
            input_refs = {
                "question_id": question.get("id"),
                "question_text_length": len(question.get("content", "") or ""),
                "knowledge_point_count": len(question.get("knowledge_points", [])),
                **media_input_refs(media_items),
            }
            call_metadata = {
                "response_length": len(response_text or ""),
                "failure_type": failure_type,
                "validation_errors": [str(e)],
            }
            provider, model, fallback_count, call_metadata = _llm_call_trace(call_metadata)
            call = LLMCallRecord(
                call_id=f"question-{question.get('id')}-competency",
                question_id=question.get("id"),
                purpose="competency_analysis",
                prompt_id="biology.competency_analysis",
                prompt_hash=sha256(prompt.encode("utf-8")).hexdigest(),
                provider=provider,
                model=model,
                input_refs=input_refs,
                parsed_schema="CompetencyResult",
                confidence=0.0,
                validation_errors=[str(e)],
                fallback_count=fallback_count,
                metadata=call_metadata,
            )
            return {
                "error": f"素养分析失败: {str(e)}",
                "question_id": question.get("id"),
                "_llm_calls": [call.model_dump()],
            }

    def aggregate_exam_competencies(self, questions_competencies: List[Dict]) -> Dict:
        """
        聚合整份试卷的素养覆盖情况
        """
        logger.info(f"[素养聚合] 开始聚合 {len(questions_competencies)} 道题目的素养数据")

        competencies = ["生命观念", "科学思维", "科学探究", "社会责任"]
        aggregated = {}

        # V1: 分值加权，从显式 _total_score 字段读取；缺分值记 0，不等权补 1。
        exam_total = sum(q.get("_total_score", 0) for q in questions_competencies)

        for comp in competencies:
            # 统计涉及该素养的题目
            involved_questions = [
                q for q in questions_competencies
                if q.get(comp, {}).get("涉及", False)
            ]

            # 分值加权总权重: Σ(权重 × 分值)
            weighted_sum = sum(
                q.get(comp, {}).get("权重", 0) * q.get("_total_score", 0)
                for q in questions_competencies
            )

            # 统计细分维度（保留题目数统计，V2 再改加权）
            sub_dimensions = {}
            for q in involved_questions:
                dims = q.get(comp, {}).get("具体维度", [])
                for dim in dims:
                    sub_dimensions[dim] = sub_dimensions.get(dim, 0) + 1

            aggregated[comp] = {
                "题目数": len(involved_questions),
                "总权重": round(weighted_sum, 2),
                "占比": round(weighted_sum / exam_total, 3) if exam_total > 0 else 0,
                "细分": sub_dimensions,
            }

        # 统计主要素养分布
        primary_distribution = {}
        for comp in competencies:
            count = sum(1 for q in questions_competencies if q.get("primary_competency") == comp)
            primary_distribution[comp] = count

        aggregated["primary_distribution"] = primary_distribution

        involved_distribution = {comp: 0 for comp in competencies}
        for q in questions_competencies:
            fg = q.get("_fine_grained")
            if not fg:
                pc = q.get("primary_competency")
                if pc and pc in competencies:
                    involved_distribution[pc] += 1
                continue
            q_involved = set()
            for seu in fg.get("scoring_units", []):
                cw = seu.get("competency_weights")
                if cw and isinstance(cw, dict):
                    for dim, w in cw.items():
                        if dim in competencies and isinstance(w, (int, float)) and w >= 0.2:
                            q_involved.add(dim)
            for dim in q_involved:
                involved_distribution[dim] += 1
        aggregated["involved_distribution"] = involved_distribution
        logger.info(f"[素养聚合] 涉及分布: {involved_distribution}")

        # SEU 级素养分布：每个 SEU 取 competency_weights 最高维度
        # Debug: 检查 _fine_grained 传入状态
        fg_count = sum(1 for q in questions_competencies if q.get("_fine_grained"))
        logger.info(f"[素养聚合] _fine_grained 传入: {fg_count}/{len(questions_competencies)} 题")
        seu_primary_distribution = {comp: 0 for comp in competencies}
        has_seu_data = False
        for q in questions_competencies:
            fg = q.get("_fine_grained")
            if not fg:
                continue
            has_seu_data = True
            for seu in fg.get("scoring_units", []):
                cw = seu.get("competency_weights")
                if cw and isinstance(cw, dict):
                    valid = {k: v for k, v in cw.items() if k in competencies and isinstance(v, (int, float))}
                    if valid:
                        primary = max(valid, key=valid.get)
                        seu_primary_distribution[primary] = seu_primary_distribution.get(primary, 0) + 1
        if has_seu_data:
            aggregated["seu_primary_distribution"] = seu_primary_distribution
            logger.info(f"[素养聚合] SEU级分布: {seu_primary_distribution}")

        logger.info(f"[素养聚合] 聚合完成")
        return aggregated


# 测试代码
if __name__ == "__main__":
    print("核心素养分析器模块加载成功")
