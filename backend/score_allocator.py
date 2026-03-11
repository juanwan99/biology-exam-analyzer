"""
分值分配器：根据难度系数和答案长度分配题目分值到难度级别

核心功能：
1. 选择题：每个选项独立评估难度，分值按选项数平分
2. 填空题：根据难度系数和答案长度动态分配分值（1-4分）
3. 大题：根据子题难度分配分值
"""

from typing import Dict, List, Any
from logger import get_logger

logger = get_logger()


class ScoreAllocator:
    """分值分配器"""

    # 难度系数到难度标签的映射
    DIFFICULTY_THRESHOLDS = {
        "简单": (0, 4.5),
        "中等": (4.5, 7.5),
        "困难": (7.5, 10)
    }

    # 不定项选择题难度系数
    MULTIPLE_CHOICE_COEFFICIENT = 1.2

    def map_difficulty_score_to_label(self, difficulty_score: float) -> str:
        """
        将难度系数映射到难度标签

        Args:
            difficulty_score: 难度系数（0-10）

        Returns:
            难度标签（简单/中等/困难）
        """
        for label, (min_score, max_score) in self.DIFFICULTY_THRESHOLDS.items():
            if min_score <= difficulty_score < max_score:
                return label
        # 边界情况：10分算困难
        return "困难"

    def allocate_choice_question_scores(
        self,
        question: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        分配选择题（单选/多选）的分值到难度级别

        流程：
        1. 获取选项难度评估结果
        2. 计算每个选项的分值（总分÷选项数）
        3. 根据每个选项的难度系数映射到难度级别
        4. 累加各难度级别的分值

        Args:
            question: 题目信息（包含total_score, num_options, question_type）
            analysis: 分析结果（包含option_difficulty_breakdown）

        Returns:
            {"简单": x, "中等": y, "困难": z}
        """
        total_score = question.get("total_score", 0)
        num_options = question.get("num_options", 4)
        question_type = question.get("question_type", "single_choice")

        option_breakdown = analysis.get("option_difficulty_breakdown", [])

        if not option_breakdown:
            logger.warning(f"题目 {question.get('id')} 缺少option_difficulty_breakdown，使用默认分配")
            # 默认：整体难度为中等
            return {"简单": 0, "中等": total_score, "困难": 0}

        # 每个选项的分值
        score_per_option = total_score / num_options

        # 初始化分值分布
        score_distribution = {"简单": 0.0, "中等": 0.0, "困难": 0.0}

        # 为每个选项分配分值
        for option_data in option_breakdown:
            difficulty_score = option_data.get("difficulty_score", 5.0)

            # 不定项选择题：难度系数 × 1.2
            if question_type == "multiple_choice":
                difficulty_score = min(10.0, difficulty_score * self.MULTIPLE_CHOICE_COEFFICIENT)

            # 映射到难度标签
            difficulty_label = self.map_difficulty_score_to_label(difficulty_score)

            # 累加分值
            score_distribution[difficulty_label] += score_per_option

        # 四舍五入到1位小数
        for key in score_distribution:
            score_distribution[key] = round(score_distribution[key], 1)

        logger.info(f"选择题 {question.get('id')} 分值分配: {score_distribution}")
        return score_distribution

    def allocate_blank_question_scores(
        self,
        question: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        分配填空题的分值到难度级别

        流程：
        1. 获取每个填空的难度评估和答案长度
        2. 按难度系数和答案长度动态分配分值（1-4分）
        3. 调整使总和=题目总分
        4. 根据每个填空的难度系数映射到难度级别
        5. 累加各难度级别的分值

        Args:
            question: 题目信息（包含total_score）
            analysis: 分析结果（包含blank_difficulty_breakdown）

        Returns:
            {"简单": x, "中等": y, "困难": z}
        """
        total_score = question.get("total_score", 0)
        blank_breakdown = analysis.get("blank_difficulty_breakdown", [])

        if not blank_breakdown:
            logger.warning(f"填空题 {question.get('id')} 缺少blank_difficulty_breakdown，使用默认分配")
            return {"简单": 0, "中等": total_score, "困难": 0}

        num_blanks = len(blank_breakdown)

        # 步骤1: 按难度系数比例初步分配
        total_difficulty = sum([b.get("difficulty_score", 5.0) for b in blank_breakdown])
        if total_difficulty == 0:
            total_difficulty = num_blanks * 5.0  # 避免除零

        initial_scores = [
            total_score * (b.get("difficulty_score", 5.0) / total_difficulty)
            for b in blank_breakdown
        ]

        # 步骤2: 答案长度加成
        adjusted_scores = []
        for i, blank in enumerate(blank_breakdown):
            score = initial_scores[i]
            answer_length = blank.get("answer_length", 0)

            # 答案长度加成
            if answer_length > 30:
                score += 0.8
            elif answer_length > 15:
                score += 0.4

            adjusted_scores.append(score)

        # 步骤3: 限制范围 [1, 4]
        clamped_scores = [max(1.0, min(4.0, s)) for s in adjusted_scores]

        # 步骤4: 按比例缩放使总和=total_score
        current_total = sum(clamped_scores)
        if current_total > 0:
            final_scores = [s * (total_score / current_total) for s in clamped_scores]
        else:
            # 均分
            final_scores = [total_score / num_blanks] * num_blanks

        # 步骤5: 四舍五入到0.5分
        final_scores = [round(s * 2) / 2 for s in final_scores]

        # 步骤6: 最后微调确保总和=total_score
        diff = sum(final_scores) - total_score
        if abs(diff) > 0.01:
            # 从最大分值中调整
            max_idx = final_scores.index(max(final_scores))
            final_scores[max_idx] -= diff
            final_scores[max_idx] = round(final_scores[max_idx] * 2) / 2

        # 步骤7: 根据难度映射到难度级别
        score_distribution = {"简单": 0.0, "中等": 0.0, "困难": 0.0}

        for i, blank in enumerate(blank_breakdown):
            difficulty_score = blank.get("difficulty_score", 5.0)
            difficulty_label = self.map_difficulty_score_to_label(difficulty_score)
            score_distribution[difficulty_label] += final_scores[i]

        # 四舍五入
        for key in score_distribution:
            score_distribution[key] = round(score_distribution[key], 1)

        logger.info(f"填空题 {question.get('id')} 分值分配: {score_distribution}")
        # 详细分配（避免f-string中的复杂表达式）
        detail_items = [f"{blank_breakdown[i].get('answer', '')[:10]}:{final_scores[i]}分" for i in range(num_blanks)]
        logger.debug(f"  详细分配: {detail_items}")

        return score_distribution

    def allocate_subjective_question_scores(
        self,
        question: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        分配主观题（简答题/实验题/大题）的分值到难度级别

        流程：
        1. 如果有子题，按子题难度分配（类似选择题逻辑）
        2. 如果没有子题，使用LLM返回的整体难度

        Args:
            question: 题目信息（包含total_score）
            analysis: 分析结果（包含sub_questions, difficulty）

        Returns:
            {"简单": x, "中等": y, "困难": z}
        """
        total_score = question.get("total_score", 0)
        sub_questions = analysis.get("sub_questions", [])

        if not sub_questions:
            # 没有子题，使用LLM返回的整体难度标签
            llm_difficulty = analysis.get("difficulty", "中等")

            # 确保是有效的难度标签
            if llm_difficulty not in ["简单", "中等", "困难"]:
                llm_difficulty = "中等"

            score_distribution = {"简单": 0.0, "中等": 0.0, "困难": 0.0}
            score_distribution[llm_difficulty] = total_score

            logger.info(f"主观题 {question.get('id')} 无子题，使用整体难度: {llm_difficulty} {total_score}分")
            return score_distribution

        # 有子题：类似选择题的逻辑
        num_subs = len(sub_questions)
        logger.info(f"主观题 {question.get('id')} 有 {num_subs} 个子题，总分 {total_score}分")

        # 步骤1：根据每个子题的难度系数分配初始分值
        sub_scores = []
        for sub in sub_questions:
            difficulty_score = sub.get("difficulty_score", 5.0)

            # 根据难度映射到基础分值（可根据实际情况调整）
            if difficulty_score < 4.0:
                base_score = 1.0  # 简单题基础分
            elif difficulty_score < 7.0:
                base_score = 2.0  # 中等题基础分
            else:
                base_score = 3.5  # 困难题基础分

            sub_scores.append(base_score)

        # 步骤2：按比例缩放使总和=total_score
        current_total = sum(sub_scores)
        if current_total > 0:
            sub_scores = [s * (total_score / current_total) for s in sub_scores]
        else:
            # 如果全是0，均分
            sub_scores = [total_score / num_subs] * num_subs

        # 步骤3：四舍五入到0.5分
        sub_scores = [round(s * 2) / 2 for s in sub_scores]

        # 步骤4：微调确保总和=total_score
        diff = sum(sub_scores) - total_score
        if abs(diff) > 0.01:
            # 从最大分值中调整
            max_idx = sub_scores.index(max(sub_scores))
            sub_scores[max_idx] -= diff
            sub_scores[max_idx] = max(0, round(sub_scores[max_idx] * 2) / 2)

        # 步骤5：按难度级别汇总（类似选择题）
        score_distribution = {"简单": 0.0, "中等": 0.0, "困难": 0.0}

        for i, sub in enumerate(sub_questions):
            difficulty_score = sub.get("difficulty_score", 5.0)
            difficulty_label = self.map_difficulty_score_to_label(difficulty_score)
            score_distribution[difficulty_label] += sub_scores[i]

        # 四舍五入
        for key in score_distribution:
            score_distribution[key] = round(score_distribution[key], 1)

        logger.info(f"主观题 {question.get('id')} 子题分值分配: {score_distribution}")

        # 详细日志
        detail_items = [
            f"子题{sub_questions[i].get('sub_id', i+1)}(难度{sub_questions[i].get('difficulty_score', 0)}):{sub_scores[i]}分"
            for i in range(num_subs)
        ]
        logger.debug(f"  详细分配: {detail_items}")

        return score_distribution

    def allocate_question_scores(
        self,
        question: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        根据题型分配题目分值到难度级别（总入口）

        Args:
            question: 题目信息
            analysis: 分析结果

        Returns:
            {"简单": x, "中等": y, "困难": z}
        """
        question_type = question.get("question_type", "unknown")

        if question_type in ["single_choice", "multiple_choice"]:
            return self.allocate_choice_question_scores(question, analysis)
        elif question_type == "fill_blank":
            return self.allocate_blank_question_scores(question, analysis)
        elif question_type in ["short_answer", "experiment"]:
            return self.allocate_subjective_question_scores(question, analysis)
        else:
            # 未知题型，默认中等
            logger.warning(f"未知题型 {question_type}，使用默认分配")
            return {"简单": 0, "中等": question.get("total_score", 0), "困难": 0}
