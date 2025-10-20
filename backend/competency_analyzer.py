"""
核心素养分析器
基于《普通高中生物学课程标准（2017年版2020修订）》
分析题目考查的四大核心素养
"""
import json
from typing import Dict, List, Any
from logger import get_logger

logger = get_logger()


class CompetencyAnalyzer:
    """核心素养分析器"""

    def __init__(
        self,
        library_path: str = "/app/rules/competency_library.json",
        gemini_analyzer=None
    ):
        """
        初始化核心素养分析器

        Args:
            library_path: 素养库JSON文件路径
            gemini_analyzer: Gemini分析器实例（必需，用于LLM分析）
        """
        self.library_path = library_path
        self.library = self._load_library()
        self.gemini_analyzer = gemini_analyzer

        if not self.gemini_analyzer:
            logger.warning("核心素养分析器未配置Gemini，功能受限")
        else:
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

    def analyze_competency(self, question: Dict[str, Any]) -> Dict[str, Any]:
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
                "生命观念": {
                    "涉及": true,
                    "具体维度": ["进化与适应观"],
                    "权重": 0.2,
                    "分析说明": "..."
                },
                "科学思维": {...},
                "科学探究": {...},
                "社会责任": {...},
                "primary_competency": "科学思维",
                "competency_level": "高"
            }
        """
        if not self.gemini_analyzer:
            logger.error("[素养分析] 未配置Gemini分析器，无法进行分析")
            return self._get_default_result(question.get("id"))

        logger.info(f"[素养分析] 开始分析题目 {question.get('id')}")

        try:
            # 加载Prompt
            prompt_path = "/app/prompts/competency_analysis_prompt.txt"
            try:
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    prompt_template = f.read()
            except FileNotFoundError:
                logger.error(f"[素养分析] Prompt文件未找到: {prompt_path}")
                return self._get_default_result(question.get("id"))

            # 填充Prompt
            prompt = prompt_template.format(
                question_text=question.get("content", ""),
                knowledge_points=", ".join(question.get("knowledge_points", []))
            )

            # 调用Gemini API
            logger.debug(f"[素养分析] 调用API分析题目 {question.get('id')}")
            response = self.gemini_analyzer.client.chat.completions.create(
                model=self.gemini_analyzer.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=2048,
                temperature=0.1
            )

            response_text = response.choices[0].message.content
            logger.debug(f"[素养分析] API响应: {response_text[:200]}...")

            # 解析JSON
            json_text = self.gemini_analyzer.extract_json(response_text)
            result = json.loads(json_text)

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

            logger.info(f"[素养分析] 题目 {question.get('id')} 分析完成，主要素养: {result.get('primary_competency')}")
            return result

        except Exception as e:
            logger.error(f"[素养分析] 题目 {question.get('id')} 分析失败: {str(e)}", exc_info=True)
            return self._get_default_result(question.get("id"))

    def _get_default_result(self, question_id) -> Dict:
        """返回默认结果（分析失败时）"""
        return {
            "question_id": question_id,
            "生命观念": {"涉及": False, "具体维度": [], "权重": 0, "分析说明": ""},
            "科学思维": {"涉及": True, "具体维度": ["演绎与推理"], "权重": 1.0, "分析说明": "默认结果"},
            "科学探究": {"涉及": False, "具体维度": [], "权重": 0, "分析说明": ""},
            "社会责任": {"涉及": False, "具体维度": [], "权重": 0, "分析说明": ""},
            "primary_competency": "科学思维",
            "competency_level": "中"
        }

    def aggregate_exam_competencies(self, questions_competencies: List[Dict]) -> Dict:
        """
        聚合整份试卷的素养覆盖情况

        Args:
            questions_competencies: 所有题目的素养分析结果列表

        Returns:
            {
                "生命观念": {
                    "题目数": 12,
                    "总权重": 4.8,
                    "占比": 0.32,
                    "细分": {
                        "结构与功能观": 5,
                        "稳态与平衡观": 4,
                        ...
                    }
                },
                "科学思维": {...},
                "科学探究": {...},
                "社会责任": {...},
                "primary_distribution": {
                    "生命观念": 8,
                    "科学思维": 12,
                    "科学探究": 3,
                    "社会责任": 2
                }
            }
        """
        logger.info(f"[素养聚合] 开始聚合 {len(questions_competencies)} 道题目的素养数据")

        competencies = ["生命观念", "科学思维", "科学探究", "社会责任"]
        aggregated = {}

        for comp in competencies:
            # 统计涉及该素养的题目
            involved_questions = [
                q for q in questions_competencies
                if q.get(comp, {}).get("涉及", False)
            ]

            # 计算总权重
            total_weight = sum(q.get(comp, {}).get("权重", 0) for q in questions_competencies)

            # 统计细分维度
            sub_dimensions = {}
            for q in involved_questions:
                dims = q.get(comp, {}).get("具体维度", [])
                for dim in dims:
                    sub_dimensions[dim] = sub_dimensions.get(dim, 0) + 1

            aggregated[comp] = {
                "题目数": len(involved_questions),
                "总权重": round(total_weight, 2),
                "占比": round(total_weight / len(questions_competencies), 3) if questions_competencies else 0,
                "细分": sub_dimensions
            }

        # 统计主要素养分布
        primary_distribution = {}
        for comp in competencies:
            count = sum(1 for q in questions_competencies if q.get("primary_competency") == comp)
            primary_distribution[comp] = count

        aggregated["primary_distribution"] = primary_distribution

        logger.info(f"[素养聚合] 聚合完成")
        return aggregated


# 测试代码
if __name__ == "__main__":
    # 需要Gemini分析器才能测试
    print("核心素养分析器模块加载成功")
    print("使用时需配合Gemini分析器")
