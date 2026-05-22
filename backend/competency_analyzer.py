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
from llm_client import llm_call
from metadata_contracts import LLMCallRecord

logger = get_logger()


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
            analyzer: 保留兼容性，实际不使用（LLM 调用已迁移到 llm_client）
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

            # 通过统一 LLM 客户端调用（自动 fallback）
            logger.debug(f"[素养分析] 调用LLM分析题目 {question.get('id')}")
            response_text = await llm_call(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                temperature=0.1,
            )
            logger.debug(f"[素养分析] LLM响应: {response_text[:200]}...")

            # 解析JSON（四级降级：直接解析→代码块→首对象→截断修复）
            result = _extract_json(response_text)
            from llm_schemas import validate_llm_output, CompetencyResult
            result, ext_conf, val_errors = validate_llm_output(result, CompetencyResult, f"素养分析 题目{question.get('id', '?')}")
            if val_errors:
                logger.warning(f"[素养] Schema校验: {val_errors[:3]}")
            result["_extraction_confidence"] = ext_conf
            # 添加题目ID
            result["question_id"] = question.get("id")

            # 验证权重总和
            total_weight = sum([
                result.get("生命观念", {}).get("权重", 0),
                result.get("科学思维", {}).get("权重", 0),
                result.get("科学探究", {}).get("权重", 0),
                result.get("社会责任", {}).get("权重", 0)
            ])

            if abs(total_weight - 1.0) > 0.01:
                logger.warning(f"[素养分析] 题目 {question.get('id')} 权重总和异常: {total_weight}")

            call = LLMCallRecord(
                call_id=f"question-{question.get('id')}-competency",
                question_id=question.get("id"),
                purpose="competency_analysis",
                prompt_id="biology.competency_analysis",
                prompt_hash=sha256(prompt.encode("utf-8")).hexdigest(),
                provider="llm_client",
                model="configured_provider_chain",
                input_refs={
                    "question_id": question.get("id"),
                    "question_text_length": len(question.get("content", "") or ""),
                    "knowledge_point_count": len(question.get("knowledge_points", [])),
                },
                parsed_schema="CompetencyResult",
                confidence=ext_conf,
                validation_errors=val_errors,
                metadata={
                    "response_length": len(response_text),
                    "total_weight": round(total_weight, 4),
                    "primary_competency": result.get("primary_competency"),
                },
            )
            result["_llm_calls"] = [call.model_dump()]

            logger.info(f"[素养分析] 题目 {question.get('id')} 分析完成，主要素养: {result.get('primary_competency')}")
            return result

        except Exception as e:
            logger.error(f"[素养分析] 题目 {question.get('id')} 分析失败: {str(e)}", exc_info=True)
            failure_type = "json_parse_failed" if response_text else "llm_call_failed"
            call = LLMCallRecord(
                call_id=f"question-{question.get('id')}-competency",
                question_id=question.get("id"),
                purpose="competency_analysis",
                prompt_id="biology.competency_analysis",
                prompt_hash=sha256(prompt.encode("utf-8")).hexdigest(),
                provider="llm_client",
                model="configured_provider_chain",
                input_refs={
                    "question_id": question.get("id"),
                    "question_text_length": len(question.get("content", "") or ""),
                    "knowledge_point_count": len(question.get("knowledge_points", [])),
                },
                parsed_schema="CompetencyResult",
                confidence=0.0,
                validation_errors=[str(e)],
                metadata={
                    "response_length": len(response_text or ""),
                    "failure_type": failure_type,
                    "validation_errors": [str(e)],
                },
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
