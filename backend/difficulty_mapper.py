"""
难度-得分率映射引擎

实现分层回退策略:
1. 知识点专属映射（精度最高）
2. 教材章节映射
3. 全局映射（兜底）

支持冷启动默认值和基于历史数据的动态更新
"""
from typing import List, Dict, Tuple, Optional
from decimal import Decimal
import numpy as np
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models import DifficultyMapping, QuestionPerformance
from logger import get_logger

logger = get_logger()


# 冷启动默认得分率（基于教育统计经验值）
COLD_START_RATES = {
    (0, 2): 0.95,    # 很简单 → 95% 得分率
    (2, 4): 0.85,    # 简单 → 85%
    (4, 6): 0.70,    # 中等 → 70%
    (6, 8): 0.55,    # 较难 → 55%
    (8, 10): 0.35,   # 很难 → 35%
}

# 冷启动默认标准差
COLD_START_STDDEV = {
    (0, 2): 0.05,
    (2, 4): 0.08,
    (4, 6): 0.10,
    (6, 8): 0.12,
    (8, 10): 0.15,
}

# 最小样本数要求
MIN_SAMPLES = {
    'global': 20,
    'chapter': 10,
    'knowledge_point': 5,
}

# 难度区间
DIFFICULTY_BINS = [(0, 2), (2, 4), (4, 6), (6, 8), (8, 10)]


class DifficultyMapper:
    """难度-得分率映射引擎"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def predict_rate(
        self,
        difficulty: float,
        grade: str,
        knowledge_points: Optional[List[str]] = None,
        textbook_chapter: Optional[str] = None
    ) -> Tuple[float, float, float]:
        """
        预测得分率（带置信区间）

        分层回退策略：
        1. 先查知识点专属映射
        2. 再查章节映射
        3. 最后用全局映射

        Args:
            difficulty: 绝对难度 (0-10)
            grade: 年级（高一/高二/高三）
            knowledge_points: 知识点列表
            textbook_chapter: 教材章节

        Returns:
            (predicted_rate, ci_lower, ci_upper) 预测得分率和95%置信区间
        """
        # 标准化年级
        grade = self._normalize_grade(grade)

        # 1. 尝试知识点映射
        if knowledge_points:
            for kp in knowledge_points:
                mapping = await self._get_mapping('knowledge_point', kp, grade, difficulty)
                if mapping and self._is_reliable(mapping):
                    logger.debug(f"使用知识点映射: {kp}, 难度={difficulty}")
                    return self._predict_from_mapping(mapping, difficulty)

        # 2. 尝试章节映射
        if textbook_chapter:
            mapping = await self._get_mapping('chapter', textbook_chapter, grade, difficulty)
            if mapping and self._is_reliable(mapping):
                logger.debug(f"使用章节映射: {textbook_chapter}, 难度={difficulty}")
                return self._predict_from_mapping(mapping, difficulty)

        # 3. 使用全局映射
        mapping = await self._get_mapping('global', None, grade, difficulty)
        if mapping:
            logger.debug(f"使用全局映射: 年级={grade}, 难度={difficulty}")
            return self._predict_from_mapping(mapping, difficulty)

        # 4. 冷启动默认值
        logger.debug(f"使用冷启动默认值: 难度={difficulty}")
        return self._cold_start_prediction(difficulty)

    async def _get_mapping(
        self,
        mapping_type: str,
        mapping_key: Optional[str],
        grade: str,
        difficulty: float
    ) -> Optional[DifficultyMapping]:
        """获取匹配的映射记录"""
        query = select(DifficultyMapping).where(
            and_(
                DifficultyMapping.mapping_type == mapping_type,
                DifficultyMapping.grade == grade,
                DifficultyMapping.difficulty_min <= difficulty,
                DifficultyMapping.difficulty_max > difficulty
            )
        )

        if mapping_key is not None:
            query = query.where(DifficultyMapping.mapping_key == mapping_key)
        else:
            query = query.where(DifficultyMapping.mapping_key.is_(None))

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    def _is_reliable(self, mapping: DifficultyMapping) -> bool:
        """判断映射是否可靠（基于置信度和样本量）"""
        min_samples = MIN_SAMPLES.get(mapping.mapping_type, 5)
        return (
            mapping.sample_count >= min_samples and
            float(mapping.confidence or 0) >= 0.6
        )

    def _predict_from_mapping(
        self,
        mapping: DifficultyMapping,
        difficulty: float
    ) -> Tuple[float, float, float]:
        """从映射计算预测值"""
        # 优先使用线性回归
        if mapping.slope is not None and mapping.intercept is not None:
            rate = float(mapping.slope) * difficulty + float(mapping.intercept)
        else:
            rate = float(mapping.avg_score_rate or 0.7)

        # 限制在合理范围
        rate = max(0.0, min(1.0, rate))

        # 计算置信区间
        stddev = float(mapping.score_rate_stddev or 0.1)
        confidence = float(mapping.confidence or 0.5)

        # 置信度越低，区间越宽
        width_factor = 2.0 - confidence  # confidence=1时factor=1, confidence=0.5时factor=1.5
        ci_lower = max(0.0, rate - 1.96 * stddev * width_factor)
        ci_upper = min(1.0, rate + 1.96 * stddev * width_factor)

        return rate, ci_lower, ci_upper

    def _cold_start_prediction(self, difficulty: float) -> Tuple[float, float, float]:
        """冷启动预测（无历史数据时使用）"""
        for (d_min, d_max), rate in COLD_START_RATES.items():
            if d_min <= difficulty < d_max:
                stddev = COLD_START_STDDEV[(d_min, d_max)]
                # 冷启动时置信区间更宽
                ci_lower = max(0.0, rate - 2.0 * stddev)
                ci_upper = min(1.0, rate + 2.0 * stddev)
                return rate, ci_lower, ci_upper

        # 超出范围，使用最难档位
        rate = COLD_START_RATES[(8, 10)]
        stddev = COLD_START_STDDEV[(8, 10)]
        return rate, max(0.0, rate - 2.0 * stddev), min(1.0, rate + 2.0 * stddev)

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

    async def build_mapping_from_history(self, grade: Optional[str] = None) -> Dict:
        """
        从历史数据构建映射模型

        Args:
            grade: 指定年级，None表示所有年级

        Returns:
            构建结果统计
        """
        stats = {
            'global': {'updated': 0, 'created': 0},
            'knowledge_point': {'updated': 0, 'created': 0},
            'chapter': {'updated': 0, 'created': 0},
        }

        grades = [grade] if grade else ['高一', '高二', '高三']

        for g in grades:
            # 获取该年级的所有题目表现数据
            query = select(QuestionPerformance).join(
                QuestionPerformance.exam
            ).where(
                QuestionPerformance.absolute_difficulty.isnot(None),
                QuestionPerformance.score_rate.isnot(None)
            )

            # 注意：需要通过关联的exam获取grade
            from models import ExamHistory
            query = select(QuestionPerformance).join(ExamHistory).where(
                QuestionPerformance.absolute_difficulty.isnot(None),
                QuestionPerformance.score_rate.isnot(None),
                ExamHistory.grade == g
            )

            result = await self.db.execute(query)
            performances = result.scalars().all()

            if not performances:
                logger.info(f"年级 {g} 无历史数据")
                continue

            # 构建全局映射
            global_stats = await self._build_global_mapping(g, performances)
            stats['global']['updated'] += global_stats['updated']
            stats['global']['created'] += global_stats['created']

            # 构建知识点映射
            kp_stats = await self._build_knowledge_point_mapping(g, performances)
            stats['knowledge_point']['updated'] += kp_stats['updated']
            stats['knowledge_point']['created'] += kp_stats['created']

            # 构建章节映射
            chapter_stats = await self._build_chapter_mapping(g, performances)
            stats['chapter']['updated'] += chapter_stats['updated']
            stats['chapter']['created'] += chapter_stats['created']

        await self.db.commit()
        logger.info(f"映射构建完成: {stats}")
        return stats

    async def _build_global_mapping(
        self,
        grade: str,
        performances: List[QuestionPerformance]
    ) -> Dict:
        """构建全局映射"""
        stats = {'updated': 0, 'created': 0}

        for d_min, d_max in DIFFICULTY_BINS:
            # 筛选该难度区间的题目
            questions = [
                p for p in performances
                if d_min <= float(p.absolute_difficulty) < d_max
            ]

            if len(questions) < MIN_SAMPLES['global']:
                continue

            # 计算统计量
            rates = [float(q.score_rate) for q in questions]
            difficulties = [float(q.absolute_difficulty) for q in questions]

            avg_rate = np.mean(rates)
            stddev = np.std(rates)
            sample_count = len(questions)

            # 线性回归
            slope, intercept = self._linear_regression(difficulties, rates)

            # 计算置信度（基于样本量和方差）
            confidence = self._calculate_confidence(sample_count, stddev)

            # 更新或创建映射
            result = await self._upsert_mapping(
                mapping_type='global',
                mapping_key=None,
                grade=grade,
                d_min=d_min,
                d_max=d_max,
                avg_rate=avg_rate,
                stddev=stddev,
                sample_count=sample_count,
                confidence=confidence,
                slope=slope,
                intercept=intercept
            )
            stats[result] += 1

        return stats

    async def _build_knowledge_point_mapping(
        self,
        grade: str,
        performances: List[QuestionPerformance]
    ) -> Dict:
        """构建知识点映射"""
        stats = {'updated': 0, 'created': 0}

        # 收集所有知识点
        kp_data = {}
        for p in performances:
            kps = p.knowledge_points or []
            for kp in kps:
                if kp not in kp_data:
                    kp_data[kp] = []
                kp_data[kp].append(p)

        # 为每个知识点构建映射
        for kp, questions in kp_data.items():
            for d_min, d_max in DIFFICULTY_BINS:
                bin_questions = [
                    q for q in questions
                    if d_min <= float(q.absolute_difficulty) < d_max
                ]

                if len(bin_questions) < MIN_SAMPLES['knowledge_point']:
                    continue

                rates = [float(q.score_rate) for q in bin_questions]
                difficulties = [float(q.absolute_difficulty) for q in bin_questions]

                avg_rate = np.mean(rates)
                stddev = np.std(rates)
                sample_count = len(bin_questions)
                slope, intercept = self._linear_regression(difficulties, rates)
                confidence = self._calculate_confidence(sample_count, stddev)

                result = await self._upsert_mapping(
                    mapping_type='knowledge_point',
                    mapping_key=kp,
                    grade=grade,
                    d_min=d_min,
                    d_max=d_max,
                    avg_rate=avg_rate,
                    stddev=stddev,
                    sample_count=sample_count,
                    confidence=confidence,
                    slope=slope,
                    intercept=intercept
                )
                stats[result] += 1

        return stats

    async def _build_chapter_mapping(
        self,
        grade: str,
        performances: List[QuestionPerformance]
    ) -> Dict:
        """构建章节映射"""
        stats = {'updated': 0, 'created': 0}

        # 按章节分组
        chapter_data = {}
        for p in performances:
            chapter = p.textbook_chapter
            if not chapter:
                continue
            if chapter not in chapter_data:
                chapter_data[chapter] = []
            chapter_data[chapter].append(p)

        # 为每个章节构建映射
        for chapter, questions in chapter_data.items():
            for d_min, d_max in DIFFICULTY_BINS:
                bin_questions = [
                    q for q in questions
                    if d_min <= float(q.absolute_difficulty) < d_max
                ]

                if len(bin_questions) < MIN_SAMPLES['chapter']:
                    continue

                rates = [float(q.score_rate) for q in bin_questions]
                difficulties = [float(q.absolute_difficulty) for q in bin_questions]

                avg_rate = np.mean(rates)
                stddev = np.std(rates)
                sample_count = len(bin_questions)
                slope, intercept = self._linear_regression(difficulties, rates)
                confidence = self._calculate_confidence(sample_count, stddev)

                result = await self._upsert_mapping(
                    mapping_type='chapter',
                    mapping_key=chapter,
                    grade=grade,
                    d_min=d_min,
                    d_max=d_max,
                    avg_rate=avg_rate,
                    stddev=stddev,
                    sample_count=sample_count,
                    confidence=confidence,
                    slope=slope,
                    intercept=intercept
                )
                stats[result] += 1

        return stats

    async def _upsert_mapping(
        self,
        mapping_type: str,
        mapping_key: Optional[str],
        grade: str,
        d_min: float,
        d_max: float,
        avg_rate: float,
        stddev: float,
        sample_count: int,
        confidence: float,
        slope: float,
        intercept: float
    ) -> str:
        """插入或更新映射记录"""
        # 查找现有记录
        query = select(DifficultyMapping).where(
            and_(
                DifficultyMapping.mapping_type == mapping_type,
                DifficultyMapping.grade == grade,
                DifficultyMapping.difficulty_min == d_min,
                DifficultyMapping.difficulty_max == d_max
            )
        )

        if mapping_key is not None:
            query = query.where(DifficultyMapping.mapping_key == mapping_key)
        else:
            query = query.where(DifficultyMapping.mapping_key.is_(None))

        result = await self.db.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            # 更新
            existing.avg_score_rate = Decimal(str(avg_rate))
            existing.score_rate_stddev = Decimal(str(stddev))
            existing.sample_count = sample_count
            existing.confidence = Decimal(str(confidence))
            existing.slope = Decimal(str(slope))
            existing.intercept = Decimal(str(intercept))
            return 'updated'
        else:
            # 创建
            new_mapping = DifficultyMapping(
                mapping_type=mapping_type,
                mapping_key=mapping_key,
                grade=grade,
                difficulty_min=Decimal(str(d_min)),
                difficulty_max=Decimal(str(d_max)),
                avg_score_rate=Decimal(str(avg_rate)),
                score_rate_stddev=Decimal(str(stddev)),
                sample_count=sample_count,
                confidence=Decimal(str(confidence)),
                slope=Decimal(str(slope)),
                intercept=Decimal(str(intercept))
            )
            self.db.add(new_mapping)
            return 'created'

    def _linear_regression(
        self,
        difficulties: List[float],
        rates: List[float]
    ) -> Tuple[float, float]:
        """简单线性回归"""
        if len(difficulties) < 2:
            return -0.075, 1.025  # 默认斜率和截距

        x = np.array(difficulties)
        y = np.array(rates)

        # 计算斜率和截距
        n = len(x)
        sum_x = np.sum(x)
        sum_y = np.sum(y)
        sum_xy = np.sum(x * y)
        sum_x2 = np.sum(x ** 2)

        denominator = n * sum_x2 - sum_x ** 2
        if abs(denominator) < 1e-10:
            return -0.075, 1.025

        slope = (n * sum_xy - sum_x * sum_y) / denominator
        intercept = (sum_y - slope * sum_x) / n

        return float(slope), float(intercept)

    def _calculate_confidence(self, sample_count: int, stddev: float) -> float:
        """
        计算置信度

        基于样本量和标准差
        样本越多、方差越小，置信度越高
        """
        # 样本量因子 (0-1)
        sample_factor = min(1.0, sample_count / 50.0)

        # 方差因子 (0-1)，方差越小越好
        variance_factor = max(0.0, 1.0 - stddev / 0.3)

        # 综合置信度
        confidence = 0.6 * sample_factor + 0.4 * variance_factor
        return max(0.0, min(1.0, confidence))

    async def get_coverage_stats(self) -> Dict:
        """获取数据覆盖统计"""
        stats = {
            'by_grade': {},
            'by_type': {
                'global': 0,
                'knowledge_point': 0,
                'chapter': 0,
            },
            'total_mappings': 0,
            'coverage_warnings': [],
        }

        # 查询所有映射
        query = select(DifficultyMapping)
        result = await self.db.execute(query)
        mappings = result.scalars().all()

        for m in mappings:
            stats['total_mappings'] += 1
            stats['by_type'][m.mapping_type] += 1

            grade = m.grade
            if grade not in stats['by_grade']:
                stats['by_grade'][grade] = {
                    'total': 0,
                    'with_data': 0,
                    'difficulty_bins': {str(b): 0 for b in DIFFICULTY_BINS}
                }

            stats['by_grade'][grade]['total'] += 1
            if m.sample_count > 0:
                stats['by_grade'][grade]['with_data'] += 1

            # 统计难度区间覆盖
            bin_key = f"({int(m.difficulty_min)}, {int(m.difficulty_max)})"
            if bin_key in stats['by_grade'][grade]['difficulty_bins']:
                stats['by_grade'][grade]['difficulty_bins'][bin_key] += m.sample_count

        # 生成警告
        for grade, data in stats['by_grade'].items():
            coverage = data['with_data'] / data['total'] if data['total'] > 0 else 0
            if coverage < 0.5:
                stats['coverage_warnings'].append(
                    f"年级 '{grade}' 数据覆盖率低 ({coverage:.1%})"
                )

            for bin_key, count in data['difficulty_bins'].items():
                if count < MIN_SAMPLES['global']:
                    stats['coverage_warnings'].append(
                        f"年级 '{grade}' 难度区间 {bin_key} 样本不足 ({count}个)"
                    )

        return stats
