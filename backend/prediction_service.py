"""
分数预估服务

提供历史数据管理和分数预估的业务逻辑
"""
from typing import List, Dict, Optional, Any
from decimal import Decimal
from datetime import datetime
import math

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import ExamHistory, QuestionPerformance, ScorePrediction, DifficultyMapping
from difficulty_mapper import DifficultyMapper, DIFFICULTY_BINS, MIN_SAMPLES
from logger import get_logger

logger = get_logger()


class PredictionService:
    """分数预估服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.mapper = DifficultyMapper(db)

    # ========================================
    # 历史数据管理
    # ========================================

    async def create_exam_history(
        self,
        name: str,
        grade: str,
        total_score: float,
        questions: List[Dict],
        exam_date: Optional[str] = None,
        student_count: Optional[int] = None,
        source_file: Optional[str] = None
    ) -> ExamHistory:
        """
        创建历史考试记录

        Args:
            name: 考试名称
            grade: 年级（高一/高二/高三）
            total_score: 试卷总分
            questions: 题目列表，每个题目包含:
                - question_number: 题号
                - question_score: 该题满分
                - actual_average: 实际平均分
                - absolute_difficulty: 绝对难度（可选，会自动分析）
                - knowledge_points: 知识点列表
                - textbook_chapter: 教材章节
                - question_type: 题型
                - question_content: 题目内容
            exam_date: 考试日期
            student_count: 参考人数
            source_file: 原始文件路径

        Returns:
            创建的历史记录
        """
        # 标准化年级
        grade = self._normalize_grade(grade)

        # 计算整卷统计
        total_actual = sum(q.get('actual_average', 0) for q in questions)
        avg_score = total_actual
        score_rate = avg_score / total_score if total_score > 0 else 0

        # 计算平均难度（如果有难度数据）
        difficulties = [q.get('absolute_difficulty') for q in questions if q.get('absolute_difficulty') is not None]
        difficulty_avg = sum(difficulties) / len(difficulties) if difficulties else None

        # 创建考试记录
        exam = ExamHistory(
            name=name,
            exam_date=datetime.strptime(exam_date, '%Y-%m-%d') if exam_date else None,
            grade=grade,
            student_count=student_count,
            total_score=Decimal(str(total_score)),
            average_score=Decimal(str(avg_score)),
            score_rate=Decimal(str(score_rate)),
            difficulty_avg=Decimal(str(difficulty_avg)) if difficulty_avg else None,
            source_file=source_file
        )
        self.db.add(exam)
        await self.db.flush()  # 获取exam.id

        # 创建题目表现记录
        for q in questions:
            q_score = float(q.get('question_score', 0))
            actual_avg = float(q.get('actual_average', 0))
            q_score_rate = actual_avg / q_score if q_score > 0 else 0

            performance = QuestionPerformance(
                exam_id=exam.id,
                question_number=q.get('question_number', 0),
                absolute_difficulty=Decimal(str(q['absolute_difficulty'])) if q.get('absolute_difficulty') else None,
                knowledge_complexity=Decimal(str(q['knowledge_complexity'])) if q.get('knowledge_complexity') else None,
                cognitive_level=Decimal(str(q['cognitive_level'])) if q.get('cognitive_level') else None,
                question_score=Decimal(str(q_score)),
                actual_average=Decimal(str(actual_avg)),
                score_rate=Decimal(str(q_score_rate)),
                knowledge_points=q.get('knowledge_points', []),
                textbook_chapter=q.get('textbook_chapter'),
                question_type=q.get('question_type'),
                question_content=q.get('question_content', '')[:500]  # 限制长度
            )
            self.db.add(performance)

        await self.db.commit()
        await self.db.refresh(exam)

        # 触发映射更新
        await self.mapper.build_mapping_from_history(grade)

        logger.info(f"创建历史记录: {name}, 年级={grade}, 题目数={len(questions)}")
        return exam

    async def get_exam_history(self, exam_id: int) -> Optional[ExamHistory]:
        """获取单个历史记录详情"""
        query = select(ExamHistory).options(
            selectinload(ExamHistory.question_performances)
        ).where(ExamHistory.id == exam_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_exam_history(
        self,
        grade: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict:
        """列出历史记录"""
        query = select(ExamHistory).order_by(desc(ExamHistory.created_at))

        if grade:
            grade = self._normalize_grade(grade)
            query = query.where(ExamHistory.grade == grade)

        # 获取总数
        count_query = select(func.count(ExamHistory.id))
        if grade:
            count_query = count_query.where(ExamHistory.grade == grade)
        count_result = await self.db.execute(count_query)
        total = count_result.scalar()

        # 分页查询
        query = query.offset(offset).limit(limit)
        result = await self.db.execute(query)
        exams = result.scalars().all()

        return {
            'total': total,
            'items': [self._exam_to_dict(e) for e in exams]
        }

    async def delete_exam_history(self, exam_id: int) -> bool:
        """删除历史记录"""
        exam = await self.get_exam_history(exam_id)
        if not exam:
            return False

        grade = exam.grade
        await self.db.delete(exam)
        await self.db.commit()

        # 重建映射
        await self.mapper.build_mapping_from_history(grade)

        logger.info(f"删除历史记录: id={exam_id}")
        return True

    # ========================================
    # 分数预估
    # ========================================

    async def predict_exam_score(
        self,
        questions: List[Dict],
        total_score: float,
        grade: str,
        exam_name: Optional[str] = None,
        save_prediction: bool = True
    ) -> Dict:
        """
        预估试卷分数

        Args:
            questions: 题目列表，每个题目需包含:
                - total_score: 题目满分
                - difficulty: { final_difficulty: float }
                - analysis: { knowledge_points: [] }（可选）
            total_score: 试卷总分
            grade: 年级
            exam_name: 考试名称
            save_prediction: 是否保存预估记录

        Returns:
            预估结果
        """
        grade = self._normalize_grade(grade)
        predictions = []
        total_variance = 0.0
        warnings = []
        knowledge_points_coverage = {}

        # 如果题目没有分值，按总分均分
        has_scores = any(
            float(q.get('total_score', q.get('analysis', {}).get('total_score', 0))) > 0
            for q in questions
        )
        default_score = total_score / len(questions) if (not has_scores and len(questions) > 0) else 0

        for i, q in enumerate(questions):
            # 提取难度和知识点
            difficulty_data = q.get('difficulty', {})
            diff = float(difficulty_data.get('final_difficulty', 5.0))
            analysis = q.get('analysis', {})
            kps = analysis.get('knowledge_points', [])
            chapter = analysis.get('textbook_chapter')
            q_score = float(q.get('total_score', analysis.get('total_score', 0)))
            if q_score <= 0:
                q_score = default_score

            # 预测得分率
            rate, ci_low, ci_high = await self.mapper.predict_rate(
                difficulty=diff,
                grade=grade,
                knowledge_points=kps,
                textbook_chapter=chapter
            )

            # 计算预测分数
            pred_score = rate * q_score
            variance = ((ci_high - ci_low) / 4) ** 2 * q_score ** 2

            predictions.append({
                'question_id': q.get('id', i + 1),
                'question_number': i + 1,
                'question_score': q_score,
                'difficulty': diff,
                'predicted_rate': round(rate, 3),
                'predicted_score': round(pred_score, 2),
                'confidence_interval': [
                    round(ci_low * q_score, 2),
                    round(ci_high * q_score, 2)
                ],
                'knowledge_points': kps
            })

            total_variance += variance

            # 跟踪知识点覆盖
            for kp in kps:
                if kp not in knowledge_points_coverage:
                    knowledge_points_coverage[kp] = {'count': 0, 'has_data': False}
                knowledge_points_coverage[kp]['count'] += 1

        # 检查知识点数据覆盖
        for kp, info in knowledge_points_coverage.items():
            # 检查该知识点是否有映射数据
            has_mapping = await self._check_knowledge_point_coverage(kp, grade)
            info['has_data'] = has_mapping
            if not has_mapping:
                warnings.append(f"知识点'{kp}'历史数据不足")

        # 计算总体预测
        total_predicted = sum(p['predicted_score'] for p in predictions)
        se = math.sqrt(total_variance)

        # 95%置信区间
        ci_lower = max(0, total_predicted - 1.96 * se)
        ci_upper = min(total_score, total_predicted + 1.96 * se)

        # 计算可靠度
        reliability = await self._calculate_reliability(questions, grade, knowledge_points_coverage)

        result = {
            'predicted_average': round(total_predicted, 2),
            'predicted_rate': round(total_predicted / total_score, 3) if total_score > 0 else 0,
            'confidence_interval': [round(ci_lower, 2), round(ci_upper, 2)],
            'reliability_score': round(reliability, 3),
            'per_question_predictions': predictions,
            'warnings': list(set(warnings)),  # 去重
            'grade': grade,
            'total_score': total_score,
            'question_count': len(questions)
        }

        # 保存预估记录
        if save_prediction:
            prediction_record = ScorePrediction(
                exam_name=exam_name,
                grade=grade,
                total_score=Decimal(str(total_score)),
                question_count=len(questions),
                predicted_average=Decimal(str(result['predicted_average'])),
                predicted_rate=Decimal(str(result['predicted_rate'])),
                confidence_lower=Decimal(str(ci_lower)),
                confidence_upper=Decimal(str(ci_upper)),
                reliability_score=Decimal(str(reliability)),
                per_question_data=predictions,
                warnings=warnings
            )
            self.db.add(prediction_record)
            await self.db.commit()
            result['prediction_id'] = prediction_record.id

        logger.info(f"预估完成: 预测均分={result['predicted_average']}, 可靠度={reliability}")
        return result

    async def submit_feedback(
        self,
        prediction_id: int,
        actual_average: float
    ) -> Dict:
        """
        提交考后实际分数反馈

        Args:
            prediction_id: 预估记录ID
            actual_average: 实际平均分

        Returns:
            更新后的预估记录
        """
        query = select(ScorePrediction).where(ScorePrediction.id == prediction_id)
        result = await self.db.execute(query)
        prediction = result.scalar_one_or_none()

        if not prediction:
            return None

        # 更新实际分数和误差
        prediction.actual_average = Decimal(str(actual_average))
        prediction.prediction_error = Decimal(str(actual_average - float(prediction.predicted_average)))

        await self.db.commit()
        await self.db.refresh(prediction)

        logger.info(
            f"反馈提交: 预测={prediction.predicted_average}, "
            f"实际={actual_average}, 误差={prediction.prediction_error}"
        )

        return {
            'id': prediction.id,
            'predicted_average': float(prediction.predicted_average),
            'actual_average': actual_average,
            'prediction_error': float(prediction.prediction_error),
            'error_percentage': abs(float(prediction.prediction_error)) / float(prediction.predicted_average) * 100 if float(prediction.predicted_average) > 0 else 0
        }

    # ========================================
    # 统计与分析
    # ========================================

    async def get_coverage_stats(self) -> Dict:
        """获取数据覆盖统计"""
        # 获取映射覆盖统计
        mapping_stats = await self.mapper.get_coverage_stats()

        # 获取历史数据统计
        exam_stats = await self._get_exam_stats()

        # 获取预估准确度统计
        accuracy_stats = await self._get_accuracy_stats()

        return {
            'mapping_coverage': mapping_stats,
            'exam_history': exam_stats,
            'prediction_accuracy': accuracy_stats
        }

    async def _get_exam_stats(self) -> Dict:
        """获取历史考试统计"""
        stats = {
            'total_exams': 0,
            'total_questions': 0,
            'by_grade': {}
        }

        # 按年级统计
        query = select(
            ExamHistory.grade,
            func.count(ExamHistory.id).label('exam_count')
        ).group_by(ExamHistory.grade)

        result = await self.db.execute(query)
        for row in result:
            stats['by_grade'][row.grade] = {
                'exam_count': row.exam_count
            }
            stats['total_exams'] += row.exam_count

        # 统计题目数
        query = select(func.count(QuestionPerformance.id))
        result = await self.db.execute(query)
        stats['total_questions'] = result.scalar()

        return stats

    async def _get_accuracy_stats(self) -> Dict:
        """获取预估准确度统计"""
        # 查询有实际分数的预估记录
        query = select(ScorePrediction).where(
            ScorePrediction.actual_average.isnot(None)
        )
        result = await self.db.execute(query)
        predictions = result.scalars().all()

        if not predictions:
            return {
                'sample_count': 0,
                'avg_error': None,
                'avg_error_percentage': None,
                'within_confidence': None
            }

        predictions = [p for p in predictions if p.prediction_error is not None]
        if not predictions:
            return {
                'sample_count': 0,
                'avg_error': None,
                'avg_error_percentage': None,
                'within_confidence': None
            }
        errors = [float(p.prediction_error) for p in predictions]
        error_percentages = [
            abs(e) / float(p.predicted_average) * 100
            for p, e in zip(predictions, errors)
            if float(p.predicted_average) > 0
        ]

        # 计算在置信区间内的比例
        within_ci = sum(
            1 for p in predictions
            if float(p.confidence_lower) <= float(p.actual_average) <= float(p.confidence_upper)
        )

        return {
            'sample_count': len(predictions),
            'avg_error': round(sum(errors) / len(errors), 2),
            'avg_error_percentage': round(sum(error_percentages) / len(error_percentages), 2) if error_percentages else None,
            'within_confidence': round(within_ci / len(predictions), 3)
        }

    async def _check_knowledge_point_coverage(self, kp: str, grade: str) -> bool:
        """检查知识点是否有足够的映射数据"""
        query = select(DifficultyMapping).where(
            DifficultyMapping.mapping_type == 'knowledge_point',
            DifficultyMapping.mapping_key == kp,
            DifficultyMapping.grade == grade,
            DifficultyMapping.sample_count >= MIN_SAMPLES['knowledge_point']
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None

    async def _calculate_reliability(
        self,
        questions: List[Dict],
        grade: str,
        kp_coverage: Dict
    ) -> float:
        """
        计算预估可靠度

        基于:
        1. 数据覆盖率（知识点/章节是否有映射数据）
        2. 样本充足程度
        3. 难度分布合理性
        """
        # 1. 知识点覆盖因子
        covered = sum(1 for info in kp_coverage.values() if info['has_data'])
        total_kp = len(kp_coverage) if kp_coverage else 1
        coverage_factor = covered / total_kp if total_kp > 0 else 0.5

        # 2. 全局映射样本量因子
        global_samples = await self._get_global_sample_count(grade)
        sample_factor = min(1.0, global_samples / 100)

        # 3. 题目数量因子（题目越多，预测越稳定）
        question_factor = min(1.0, len(questions) / 20)

        # 综合可靠度
        reliability = 0.5 * coverage_factor + 0.3 * sample_factor + 0.2 * question_factor

        return max(0.0, min(1.0, reliability))

    async def _get_global_sample_count(self, grade: str) -> int:
        """获取全局映射的总样本数"""
        query = select(func.sum(DifficultyMapping.sample_count)).where(
            DifficultyMapping.mapping_type == 'global',
            DifficultyMapping.grade == grade
        )
        result = await self.db.execute(query)
        return result.scalar() or 0

    def _normalize_grade(self, grade: str) -> str:
        """标准化年级名称"""
        grade = grade.strip()
        if '高一' in grade or '1' in grade:
            return '高一'
        elif '高二' in grade or '2' in grade:
            return '高二'
        elif '高三' in grade or '3' in grade:
            return '高三'
        return grade

    def _exam_to_dict(self, exam: ExamHistory) -> Dict:
        """将ExamHistory转换为字典"""
        return {
            'id': exam.id,
            'name': exam.name,
            'exam_date': exam.exam_date.strftime('%Y-%m-%d') if exam.exam_date else None,
            'grade': exam.grade,
            'student_count': exam.student_count,
            'total_score': float(exam.total_score),
            'average_score': float(exam.average_score) if exam.average_score else None,
            'score_rate': float(exam.score_rate) if exam.score_rate else None,
            'difficulty_avg': float(exam.difficulty_avg) if exam.difficulty_avg else None,
            'source_file': exam.source_file,
            'created_at': exam.created_at.isoformat() if exam.created_at else None
        }
