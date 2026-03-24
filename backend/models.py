"""
数据库模型定义
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, DECIMAL, ARRAY, JSON, Index
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from database import Base


class TextbookVersion(Base):
    """教材版本"""
    __tablename__ = "textbook_versions"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.now)

    chapters = relationship("TextbookChapter", back_populates="version", cascade="all, delete-orphan")


# DEPRECATED: 现网数据库无此表。教材管理 API 的 chapter CRUD 功能依赖此 ORM，
# 但实际教材数据在 textbook_pages/textbook_chunks 表中（由上传流程直接写入）。
# 后续 Batch 考虑统一或删除。
class TextbookChapter(Base):
    """教材章节"""
    __tablename__ = "textbook_chapters"

    id = Column(Integer, primary_key=True)
    version_id = Column(Integer, ForeignKey("textbook_versions.id", ondelete="CASCADE"), index=True)
    grade = Column(String(20), nullable=False, index=True)
    semester = Column(String(10))
    module_name = Column(String(100), index=True)
    chapter_num = Column(Integer)
    chapter_name = Column(String(200))
    section_num = Column(Integer)
    section_name = Column(String(200))
    parent_id = Column(Integer, ForeignKey("textbook_chapters.id"), index=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    version = relationship("TextbookVersion", back_populates="chapters")
    contents = relationship("TextbookContent", back_populates="chapter", cascade="all, delete-orphan")
    knowledge_points = relationship("KnowledgePoint", back_populates="chapter")

    # 复合索引
    __table_args__ = (
        Index('idx_chapter_version_grade', 'version_id', 'grade'),
        Index('idx_chapter_module_sort', 'module_name', 'sort_order'),
    )


# DEPRECATED: 现网数据库无此表。教材管理 API 的 chapter CRUD 功能依赖此 ORM，
# 但实际教材数据在 textbook_pages/textbook_chunks 表中（由上传流程直接写入）。
# 后续 Batch 考虑统一或删除。
class TextbookContent(Base):
    """教材内容"""
    __tablename__ = "textbook_contents"

    id = Column(Integer, primary_key=True)
    chapter_id = Column(Integer, ForeignKey("textbook_chapters.id", ondelete="CASCADE"), index=True)
    content_type = Column(String(50), default="text", index=True)  # text/concept/example/experiment/summary
    title = Column(String(200))
    content = Column(Text, nullable=False)
    content_embedding = Column(Vector(1536))  # 向量嵌入
    page_num = Column(Integer)
    sort_order = Column(Integer, default=0)
    extra_data = Column(JSON, default={})  # 改名避免与SQLAlchemy保留字冲突
    created_at = Column(DateTime, default=datetime.now)

    chapter = relationship("TextbookChapter", back_populates="contents")

    __table_args__ = (
        Index('idx_content_chapter_sort', 'chapter_id', 'sort_order'),
    )


class KnowledgePoint(Base):
    """知识点"""
    __tablename__ = "knowledge_points"

    id = Column(Integer, primary_key=True)
    chapter_id = Column(Integer, ForeignKey("textbook_chapters.id", ondelete="SET NULL"), index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text)
    description_embedding = Column(Vector(1536))
    difficulty_level = Column(Integer, default=3, index=True)
    importance_level = Column(Integer, default=3, index=True)
    competency_tags = Column(JSON, default=[])
    prerequisite_ids = Column(ARRAY(Integer))
    keywords = Column(ARRAY(Text))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    chapter = relationship("TextbookChapter", back_populates="knowledge_points")

    __table_args__ = (
        Index('idx_kp_chapter_difficulty', 'chapter_id', 'difficulty_level'),
    )


class ExerciseSource(Base):
    """题目来源"""
    __tablename__ = "exercise_sources"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, index=True)
    source_type = Column(String(50), index=True)  # 高考/模拟/教辅/自编
    year = Column(Integer, index=True)
    region = Column(String(100), index=True)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.now)

    exercises = relationship("ExerciseBank", back_populates="source")

    __table_args__ = (
        Index('idx_source_type_year', 'source_type', 'year'),
    )


class ExerciseBank(Base):
    """题库"""
    __tablename__ = "exercise_bank"

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("exercise_sources.id", ondelete="SET NULL"), index=True)
    question_type = Column(String(50), nullable=False, index=True)
    content = Column(Text, nullable=False)
    content_embedding = Column(Vector(1536))
    options = Column(JSON)
    answer = Column(Text)
    explanation = Column(Text)
    knowledge_point_ids = Column(ARRAY(Integer))
    chapter_ids = Column(ARRAY(Integer))
    difficulty_level = Column(DECIMAL(3, 2), index=True)
    competency_scores = Column(JSON)
    tags = Column(ARRAY(Text))
    usage_count = Column(Integer, default=0, index=True)
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    source = relationship("ExerciseSource", back_populates="exercises")

    __table_args__ = (
        Index('idx_exercise_type_difficulty', 'question_type', 'difficulty_level'),
        Index('idx_exercise_source_type', 'source_id', 'question_type'),
    )


class AdminUser(Base):
    """管理员用户"""
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100))
    role = Column(String(20), default="editor")  # admin/editor/viewer
    is_active = Column(Integer, default=1)
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    operation_logs = relationship("OperationLog", back_populates="user")


class OperationLog(Base):
    """操作日志"""
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("admin_users.id", ondelete="SET NULL"), index=True)
    username = Column(String(50), index=True)  # 冗余存储，防止用户被删后丢失
    operation = Column(String(50), nullable=False, index=True)  # create/update/delete
    target_type = Column(String(50), nullable=False, index=True)  # exercise/source/chapter/knowledge_point
    target_id = Column(Integer, index=True)
    target_name = Column(String(200))  # 操作对象的名称/摘要
    old_value = Column(JSON)  # 修改前的值
    new_value = Column(JSON)  # 修改后的值
    ip_address = Column(String(50))
    created_at = Column(DateTime, default=datetime.now, index=True)

    user = relationship("AdminUser", back_populates="operation_logs")

    __table_args__ = (
        Index('idx_log_user_created', 'user_id', 'created_at'),
        Index('idx_log_target', 'target_type', 'target_id'),
        Index('idx_log_operation_created', 'operation', 'created_at'),
    )


class Resource(Base):
    """素材资源"""
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True)
    resource_type = Column(String(50), nullable=False)  # image/video/audio/document
    title = Column(String(200))
    description = Column(Text)
    file_path = Column(String(500))
    file_size = Column(Integer)
    mime_type = Column(String(100))
    chapter_ids = Column(ARRAY(Integer))
    knowledge_point_ids = Column(ARRAY(Integer))
    tags = Column(ARRAY(Text))
    extra_data = Column(JSON, default={})  # 改名避免与SQLAlchemy保留字冲突
    created_at = Column(DateTime, default=datetime.now)


class TextbookPage(Base):
    """教材页面（现网实际表 — B0 新增 ORM 映射）"""
    __tablename__ = "textbook_pages"

    id = Column(Integer, primary_key=True)
    book_id = Column(String(50), nullable=False, index=True)
    book_name = Column(String(200), nullable=False)
    page_num = Column(Integer, nullable=False)
    markdown_content = Column(Text)
    chapter_info = Column(JSON, default=dict)
    image_path = Column(String(500))
    created_at = Column(DateTime, default=datetime.now)

    chunks = relationship("TextbookChunk", back_populates="page", cascade="all, delete-orphan")


class TextbookChunk(Base):
    """教材切片（现网实际表 — B0 新增 ORM 映射）"""
    __tablename__ = "textbook_chunks"

    id = Column(Integer, primary_key=True)
    page_id = Column(Integer, ForeignKey("textbook_pages.id", ondelete="CASCADE"))
    book_id = Column(String(50), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    chunk_content = Column(Text, nullable=False)
    page_num = Column(Integer)
    chapter_info = Column(JSON, default=dict)
    embedding = Column(Vector(384))
    created_at = Column(DateTime, default=datetime.now)

    page = relationship("TextbookPage", back_populates="chunks")


# =====================================================
# 难度预估系统相关模型
# =====================================================

class ExamHistory(Base):
    """历史考试记录"""
    __tablename__ = "exam_history"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    exam_date = Column(DateTime)
    grade = Column(String(50), nullable=False, index=True)  # 高一/高二/高三
    student_count = Column(Integer)
    total_score = Column(DECIMAL(5, 2), nullable=False)
    average_score = Column(DECIMAL(5, 2))
    score_rate = Column(DECIMAL(4, 3))  # 得分率 0-1
    difficulty_avg = Column(DECIMAL(4, 2))  # 平均绝对难度
    source_file = Column(String(500))
    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联的题目表现
    question_performances = relationship(
        "QuestionPerformance",
        back_populates="exam",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index('idx_exam_history_grade_date', 'grade', 'exam_date'),
    )


class QuestionPerformance(Base):
    """题目实际表现"""
    __tablename__ = "question_performance"

    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey("exam_history.id", ondelete="CASCADE"), index=True)
    question_number = Column(Integer, nullable=False)

    # 绝对难度
    absolute_difficulty = Column(DECIMAL(4, 2))
    knowledge_complexity = Column(DECIMAL(4, 2))
    cognitive_level = Column(DECIMAL(4, 2))

    # 实际表现
    question_score = Column(DECIMAL(5, 2), nullable=False)
    actual_average = Column(DECIMAL(5, 2))
    score_rate = Column(DECIMAL(4, 3))

    # 知识点关联
    knowledge_points = Column(JSON, default=[])
    textbook_chapter = Column(String(100))

    # 元数据
    question_type = Column(String(50))
    question_content = Column(Text)

    created_at = Column(DateTime, default=datetime.now)

    exam = relationship("ExamHistory", back_populates="question_performances")

    __table_args__ = (
        Index('idx_qp_exam_question', 'exam_id', 'question_number'),
        Index('idx_qp_difficulty', 'absolute_difficulty'),
    )


class DifficultyMapping(Base):
    """难度-得分率映射"""
    __tablename__ = "difficulty_mapping"

    id = Column(Integer, primary_key=True)
    mapping_type = Column(String(50), nullable=False, index=True)  # global/knowledge_point/chapter
    mapping_key = Column(String(200))  # 知识点名或章节ID
    grade = Column(String(50), nullable=False, index=True)

    # 难度区间
    difficulty_min = Column(DECIMAL(4, 2), nullable=False)
    difficulty_max = Column(DECIMAL(4, 2), nullable=False)

    # 得分率统计
    avg_score_rate = Column(DECIMAL(4, 3))
    score_rate_stddev = Column(DECIMAL(4, 3))
    sample_count = Column(Integer, default=0)
    confidence = Column(DECIMAL(4, 3))

    # 线性回归参数
    slope = Column(DECIMAL(10, 8))
    intercept = Column(DECIMAL(10, 8))

    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        Index('idx_dm_type_grade', 'mapping_type', 'grade'),
        Index('idx_dm_difficulty_range', 'difficulty_min', 'difficulty_max'),
    )


class ScorePrediction(Base):
    """分数预估记录"""
    __tablename__ = "score_prediction"

    id = Column(Integer, primary_key=True)
    exam_name = Column(String(200))
    grade = Column(String(50), index=True)
    total_score = Column(DECIMAL(5, 2))
    question_count = Column(Integer)

    # 预估结果
    predicted_average = Column(DECIMAL(5, 2))
    predicted_rate = Column(DECIMAL(4, 3))
    confidence_lower = Column(DECIMAL(5, 2))
    confidence_upper = Column(DECIMAL(5, 2))
    reliability_score = Column(DECIMAL(4, 3))

    # 详细数据
    per_question_data = Column(JSON, default=[])
    warnings = Column(JSON, default=[])

    # 实际结果（考后填入）
    actual_average = Column(DECIMAL(5, 2))
    prediction_error = Column(DECIMAL(5, 2))

    created_at = Column(DateTime, default=datetime.now, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
