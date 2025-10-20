"""
难度评估引擎
基于规则的初步评分 + LLM精调
"""
import json
import re
from typing import Dict, List, Any, Optional
from pathlib import Path
from logger import get_logger

logger = get_logger()


class DifficultyEngine:
    """难度评估引擎"""

    def __init__(
        self,
        rules_path: str = "/app/rules/difficulty_rules.json",
        gemini_analyzer=None
    ):
        """
        初始化难度评估引擎

        Args:
            rules_path: 规则库JSON文件路径
            gemini_analyzer: Gemini分析器实例（用于LLM精调）
        """
        self.rules_path = rules_path
        self.rules = self._load_rules()
        self.gemini_analyzer = gemini_analyzer
        logger.info("难度评估引擎初始化完成")

    def _load_rules(self) -> Dict:
        """加载规则库"""
        try:
            with open(self.rules_path, 'r', encoding='utf-8') as f:
                rules = json.load(f)
            logger.info(f"规则库加载成功: {self.rules_path}")
            return rules
        except FileNotFoundError:
            logger.error(f"规则库文件未找到: {self.rules_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"规则库JSON解析失败: {e}")
            raise

    def evaluate_difficulty(self, question: Dict[str, Any]) -> Dict[str, Any]:
        """
        评估题目难度（规则引擎）

        Args:
            question: {
                "id": 7,
                "content": "题目文本",
                "knowledge_points": ["遗传学", "概率计算"],
                "images": [...]  # 可选
            }

        Returns:
            {
                "question_id": 7,
                "knowledge_complexity": 6.0,
                "cognitive_level": 8.0,
                "info_extraction": 8.5,
                "reasoning_steps": 7.0,
                "base_difficulty": 7.2,
                "details": {...}
            }
        """
        logger.info(f"[规则引擎] 开始评估题目 {question.get('id', 'unknown')}")

        content = question.get("content", "")
        knowledge_points = question.get("knowledge_points", [])
        images = question.get("images", [])

        # 1. 知识点复杂度评估
        knowledge_score = self._evaluate_knowledge_complexity(knowledge_points, content)

        # 2. 认知层级评估
        cognitive_score = self._evaluate_cognitive_level(content)

        # 3. 信息提取难度评估
        info_score = self._evaluate_info_extraction(content, images)

        # 4. 步骤复杂度评估
        reasoning_score = self._evaluate_reasoning_complexity(content)

        # 5. 计算加权平均
        base_difficulty = (
            knowledge_score * 0.4 +
            cognitive_score * 0.3 +
            info_score * 0.2 +
            reasoning_score * 0.1
        )

        result = {
            "question_id": question.get("id"),
            "knowledge_complexity": round(knowledge_score, 2),
            "cognitive_level": round(cognitive_score, 2),
            "info_extraction": round(info_score, 2),
            "reasoning_steps": round(reasoning_score, 2),
            "base_difficulty": round(base_difficulty, 2),
            "details": {
                "knowledge_analysis": self._get_knowledge_details(knowledge_points, content),
                "cognitive_analysis": self._get_cognitive_details(content),
                "info_analysis": self._get_info_details(content, images),
                "reasoning_analysis": self._get_reasoning_details(content)
            }
        }

        logger.info(f"[规则引擎] 题目 {question.get('id')} 基础难度: {base_difficulty:.2f}")
        return result

    def _evaluate_knowledge_complexity(self, knowledge_points: List[str], content: str) -> float:
        """
        评估知识点复杂度

        评分规则:
        - 单知识点: 0-3分
        - 2个知识点(同章): 4-5分
        - 2-3个知识点(跨章): 5-7分
        - 3+知识点(跨模块): 7-10分
        """
        num_kp = len(knowledge_points)

        if num_kp == 0:
            return 3.0  # 默认中等
        elif num_kp == 1:
            return 3.0
        elif num_kp == 2:
            # 检查是否跨模块
            if self._is_cross_module(knowledge_points):
                return 7.0
            else:
                return 5.0
        elif num_kp >= 3:
            if self._is_cross_module(knowledge_points):
                return 9.0
            else:
                return 7.0

        return 5.0

    def _is_cross_module(self, knowledge_points: List[str]) -> bool:
        """
        检测知识点是否跨模块

        通过关键词匹配判断知识点所属模块
        """
        modules = self.rules["knowledge_modules"]
        kp_modules = set()

        for kp in knowledge_points:
            for module_name, module_data in modules.items():
                module_keywords = module_data.get("keywords", [])
                if any(keyword in kp for keyword in module_keywords):
                    kp_modules.add(module_name)
                    break

        # 如果涉及2个以上模块，则为跨模块
        return len(kp_modules) >= 2

    def _evaluate_cognitive_level(self, content: str) -> float:
        """
        评估认知层级（基于布鲁姆分类法）

        从高到低检查关键词匹配:
        L6_评价(10分) > L5_综合(9分) > L4_分析(8分) >
        L3_应用(6分) > L2_理解(4分) > L1_记忆(2分)
        """
        cognitive_levels = self.rules["cognitive_levels"]
        content_lower = content.lower()

        # 从高到低检查
        for level_name in ["L6_评价", "L5_综合", "L4_分析", "L3_应用", "L2_理解", "L1_记忆"]:
            level_data = cognitive_levels[level_name]
            keywords = level_data["keywords"]

            # 检查是否匹配关键词
            if any(kw in content_lower for kw in keywords):
                return float(level_data["score"])

        # 默认理解层级
        return 4.0

    def _evaluate_info_extraction(self, content: str, images: List) -> float:
        """
        评估信息提取难度

        评分规则:
        - 纯文字: 0-3分
        - 简单图表: 4-6分
        - 复杂图表(系谱图、多图): 7-9分
        - 综合信息(材料一/二、多图多表): 9-10分
        """
        info_patterns = self.rules["info_extraction_patterns"]

        # 从高到低检查
        for pattern_name in ["综合信息", "复杂图表", "简单图表", "纯文字"]:
            pattern_data = info_patterns[pattern_name]
            patterns = pattern_data["patterns"]

            if patterns and any(pattern in content for pattern in patterns):
                return float(pattern_data["score"])

        # 如果有图片但无关键词，默认简单图表
        if images and len(images) > 0:
            return 5.0

        # 纯文字
        return 2.0

    def _evaluate_reasoning_complexity(self, content: str) -> float:
        """
        评估步骤复杂度

        评分规则:
        - 单步直达: 0-3分
        - 两步推理: 4-5分
        - 多步推理: 6-7分
        - 复杂推理(逐代分析、多条件): 8-10分
        """
        reasoning_patterns = self.rules["reasoning_complexity"]

        # 从高到低检查
        for pattern_name in ["复杂推理", "多步推理", "两步推理", "单步直达"]:
            pattern_data = reasoning_patterns[pattern_name]
            indicators = pattern_data["indicators"]

            if indicators:
                # 检查是否匹配指示词
                if isinstance(indicators, list):
                    if any(indicator in content for indicator in indicators):
                        return float(pattern_data["score"])
                elif isinstance(indicators, str):
                    # 正则匹配（如"首先.*然后.*最后"）
                    if re.search(indicators, content):
                        return float(pattern_data["score"])

        # 默认两步推理
        return 4.0

    def _get_knowledge_details(self, knowledge_points: List[str], content: str) -> str:
        """获取知识点分析详情"""
        num_kp = len(knowledge_points)
        is_cross = self._is_cross_module(knowledge_points)

        if num_kp == 0:
            return "未检测到明确知识点"
        elif num_kp == 1:
            return f"单一知识点: {knowledge_points[0]}"
        elif is_cross:
            return f"跨模块综合题（涉及{num_kp}个知识点）: {', '.join(knowledge_points)}"
        else:
            return f"跨章节题目（涉及{num_kp}个知识点）: {', '.join(knowledge_points)}"

    def _get_cognitive_details(self, content: str) -> str:
        """获取认知层级分析详情"""
        cognitive_levels = self.rules["cognitive_levels"]

        for level_name in ["L6_评价", "L5_综合", "L4_分析", "L3_应用", "L2_理解", "L1_记忆"]:
            level_data = cognitive_levels[level_name]
            keywords = level_data["keywords"]
            matched_keywords = [kw for kw in keywords if kw in content.lower()]

            if matched_keywords:
                return f"{level_data['description']}（关键词: {', '.join(matched_keywords[:3])}）"

        return "理解层级"

    def _get_info_details(self, content: str, images: List) -> str:
        """获取信息提取分析详情"""
        info_patterns = self.rules["info_extraction_patterns"]

        for pattern_name in ["综合信息", "复杂图表", "简单图表"]:
            pattern_data = info_patterns[pattern_name]
            patterns = pattern_data["patterns"]
            matched_patterns = [p for p in patterns if p in content]

            if matched_patterns:
                img_count = len(images) if images else 0
                return f"{pattern_name}（检测到: {', '.join(matched_patterns[:3])}；图片数: {img_count}）"

        return "纯文字题目"

    def _get_reasoning_details(self, content: str) -> str:
        """获取推理复杂度分析详情"""
        reasoning_patterns = self.rules["reasoning_complexity"]

        for pattern_name in ["复杂推理", "多步推理", "两步推理"]:
            pattern_data = reasoning_patterns[pattern_name]
            indicators = pattern_data["indicators"]

            if indicators:
                if isinstance(indicators, list):
                    matched = [ind for ind in indicators if ind in content]
                    if matched:
                        return f"{pattern_name}（检测到: {', '.join(matched[:3])}）"
                elif isinstance(indicators, str):
                    if re.search(indicators, content):
                        return f"{pattern_name}（符合模式: {indicators}）"

        return "单步直达或简单推理"

    def refine_with_llm(
        self,
        question: Dict[str, Any],
        base_result: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        使用LLM精调难度评分

        Args:
            question: 题目信息
            base_result: 规则引擎的基础评估结果

        Returns:
            LLM精调后的结果，如果失败则返回None
        """
        if not self.gemini_analyzer:
            logger.warning("[LLM精调] 未配置Gemini分析器，跳过精调")
            return None

        logger.info(f"[LLM精调] 开始精调题目 {question.get('id')}")

        try:
            # 加载精调Prompt
            prompt_path = "/app/prompts/difficulty_refine_prompt.txt"
            try:
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    prompt_template = f.read()
            except FileNotFoundError:
                logger.error(f"[LLM精调] Prompt文件未找到: {prompt_path}")
                return None

            # 填充Prompt
            prompt = prompt_template.format(
                knowledge_complexity=base_result["knowledge_complexity"],
                cognitive_level=base_result["cognitive_level"],
                info_extraction=base_result["info_extraction"],
                reasoning_steps=base_result["reasoning_steps"],
                base_difficulty=base_result["base_difficulty"],
                question_text=question.get("content", ""),
                knowledge_points=", ".join(question.get("knowledge_points", []))
            )

            # 调用Gemini API
            response = self.gemini_analyzer.client.chat.completions.create(
                model=self.gemini_analyzer.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=2048,
                temperature=0.1  # 低随机性，确保评分稳定
            )

            response_text = response.choices[0].message.content
            logger.debug(f"[LLM精调] API响应: {response_text}")

            # 解析JSON
            json_text = self.gemini_analyzer.extract_json(response_text)
            refined_result = json.loads(json_text)

            logger.info(f"[LLM精调] 题目 {question.get('id')} 精调完成，最终难度: {refined_result.get('final_difficulty')}")
            return refined_result

        except Exception as e:
            logger.error(f"[LLM精调] 失败: {str(e)}", exc_info=True)
            return None

    def evaluate_with_refinement(
        self,
        question: Dict[str, Any],
        mode: str = "fast"
    ) -> Dict[str, Any]:
        """
        完整的难度评估流程：规则引擎 + LLM精调

        Args:
            question: 题目信息
            mode: 评估模式
                - "fast" (快速模式): 仅规则引擎，耗时短，适合预览
                - "deep" (深度模式): 规则引擎 + LLM精调，耗时长，准确度高

        Returns:
            完整评估结果
        """
        # 第1步：规则引擎基础评估
        base_result = self.evaluate_difficulty(question)

        # 第2步：LLM精调（根据模式决定）
        if mode == "deep" and self.gemini_analyzer:
            logger.info(f"[评估] 题目 {question.get('id')} 使用深度模式（规则+LLM精调）")
            refined_result = self.refine_with_llm(question, base_result)

            if refined_result:
                # 合并结果
                return {
                    **base_result,
                    "mode": "deep",
                    "refined": True,
                    "knowledge_complexity": refined_result["knowledge_complexity_adjusted"],
                    "cognitive_level": refined_result["cognitive_level_adjusted"],
                    "info_extraction": refined_result["info_extraction_adjusted"],
                    "reasoning_steps": refined_result["reasoning_steps_adjusted"],
                    "final_difficulty": refined_result["final_difficulty"],
                    "difficulty_label": refined_result["difficulty_label"],
                    "estimated_solve_time": refined_result.get("estimated_solve_time", "未知"),
                    "difficulty_factors": refined_result.get("difficulty_factors", []),
                    "adjustment_reasons": refined_result.get("adjustment_reasons", "")
                }
            else:
                logger.warning(f"[评估] 题目 {question.get('id')} LLM精调失败，回退到快速模式")
        elif mode == "fast":
            logger.info(f"[评估] 题目 {question.get('id')} 使用快速模式（仅规则引擎）")
        else:
            logger.warning(f"[评估] 未知模式 '{mode}'，使用快速模式")

        # 快速模式或精调失败：返回基础评估
        base_result["mode"] = "fast"
        base_result["refined"] = False
        base_result["final_difficulty"] = base_result["base_difficulty"]
        base_result["difficulty_label"] = self._get_difficulty_label(base_result["base_difficulty"])
        base_result["estimated_solve_time"] = self._estimate_time(base_result["base_difficulty"])
        return base_result

    def _estimate_time(self, difficulty: float) -> str:
        """根据难度估算答题时间（快速模式使用）"""
        if difficulty < 4:
            return "1-2分钟"
        elif difficulty < 7:
            return "2-4分钟"
        else:
            return "5-8分钟"

    def _get_difficulty_label(self, score: float) -> str:
        """根据分数返回难度标签"""
        if score < 4:
            return "简单"
        elif score < 7:
            return "中等"
        else:
            return "困难"


# 测试代码
if __name__ == "__main__":
    # 测试用例：2025山东卷第7题
    test_question = {
        "id": 7,
        "content": """某动物家系的系谱图如图所示。a1、a2、a3、a4是位于X染色体上的等位基因，
Ⅰ-1基因型为XalXa2，Ⅰ-2基因型为Xa3Y，Ⅱ-1和Ⅱ-4基因型均为Xa4Y，
Ⅳ-1为纯合子的概率为（    ）
A. 3/64  B. 3/32  C. 1/8  D. 3/16""",
        "knowledge_points": ["伴性遗传", "概率计算", "基因型推导"],
        "images": []  # 假设系谱图已在文字中描述
    }

    # 初始化引擎
    engine = DifficultyEngine(rules_path="rules/difficulty_rules.json")

    # 评估难度
    result = engine.evaluate_difficulty(test_question)

    # 打印结果
    print("=" * 70)
    print(f"题目 {result['question_id']} 难度评估结果:")
    print("=" * 70)
    print(f"知识点复杂度: {result['knowledge_complexity']}/10")
    print(f"  → {result['details']['knowledge_analysis']}")
    print(f"\n认知层级: {result['cognitive_level']}/10")
    print(f"  → {result['details']['cognitive_analysis']}")
    print(f"\n信息提取: {result['info_extraction']}/10")
    print(f"  → {result['details']['info_analysis']}")
    print(f"\n推理复杂度: {result['reasoning_steps']}/10")
    print(f"  → {result['details']['reasoning_analysis']}")
    print("=" * 70)
    print(f"📊 基础难度系数: {result['base_difficulty']}/10")
    print("=" * 70)
