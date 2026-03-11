-- 难度预估系统数据库表
-- 实现"绝对难度 + 相对难度"双维度评估系统

-- =====================================================
-- 1. 历史考试记录表
-- =====================================================

CREATE TABLE exam_history (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,                  -- 考试名称
    exam_date DATE,                              -- 考试日期
    grade VARCHAR(50) NOT NULL,                  -- 年级（高一/高二/高三）
    student_count INT,                           -- 参考人数
    total_score DECIMAL(5,2) NOT NULL,           -- 试卷总分
    average_score DECIMAL(5,2),                  -- 实际平均分
    score_rate DECIMAL(4,3),                     -- 得分率 (0-1)
    difficulty_avg DECIMAL(4,2),                 -- 平均绝对难度
    source_file VARCHAR(500),                    -- 原始文件路径
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE exam_history IS '历史考试记录表 - 存储已知平均分的历史试卷数据';
COMMENT ON COLUMN exam_history.grade IS '年级：高一/高二/高三';
COMMENT ON COLUMN exam_history.score_rate IS '得分率：average_score / total_score';
COMMENT ON COLUMN exam_history.difficulty_avg IS '所有题目的平均绝对难度 (0-10)';

-- =====================================================
-- 2. 题目实际表现表（细粒度数据）
-- =====================================================

CREATE TABLE question_performance (
    id SERIAL PRIMARY KEY,
    exam_id INT REFERENCES exam_history(id) ON DELETE CASCADE,
    question_number INT NOT NULL,                -- 题号

    -- 绝对难度（来自现有难度引擎）
    absolute_difficulty DECIMAL(4,2),            -- 绝对难度 (0-10)
    knowledge_complexity DECIMAL(4,2),           -- 知识复杂度
    cognitive_level DECIMAL(4,2),                -- 认知层级

    -- 实际表现
    question_score DECIMAL(5,2) NOT NULL,        -- 该题满分
    actual_average DECIMAL(5,2),                 -- 实际平均分
    score_rate DECIMAL(4,3),                     -- 得分率 (0-1)

    -- 知识点关联
    knowledge_points JSONB DEFAULT '[]',         -- 知识点列表
    textbook_chapter VARCHAR(100),               -- 教材章节

    -- 元数据
    question_type VARCHAR(50),                   -- 题型
    question_content TEXT,                       -- 题目内容摘要

    created_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE question_performance IS '题目实际表现表 - 存储每道题的难度和实际得分率';
COMMENT ON COLUMN question_performance.absolute_difficulty IS 'AI分析的绝对难度 (0-10)';
COMMENT ON COLUMN question_performance.score_rate IS '实际得分率：actual_average / question_score';

-- =====================================================
-- 3. 难度→得分率映射表
-- =====================================================

CREATE TABLE difficulty_mapping (
    id SERIAL PRIMARY KEY,
    mapping_type VARCHAR(50) NOT NULL,           -- 映射类型: global/knowledge_point/chapter
    mapping_key VARCHAR(200),                    -- 知识点名称或章节ID（global类型为NULL）
    grade VARCHAR(50) NOT NULL,                  -- 适用年级（高一/高二/高三）

    -- 难度区间
    difficulty_min DECIMAL(4,2) NOT NULL,        -- 区间下限
    difficulty_max DECIMAL(4,2) NOT NULL,        -- 区间上限

    -- 得分率统计
    avg_score_rate DECIMAL(4,3),                 -- 平均得分率
    score_rate_stddev DECIMAL(4,3),              -- 得分率标准差
    sample_count INT DEFAULT 0,                  -- 样本数量
    confidence DECIMAL(4,3),                     -- 置信度 (0-1)

    -- 线性回归参数（用于精确预估）
    slope DECIMAL(10,8),                         -- 斜率
    intercept DECIMAL(10,8),                     -- 截距

    updated_at TIMESTAMP DEFAULT NOW(),

    -- 复合唯一约束：同一类型+key+年级+难度区间只能有一条记录
    UNIQUE(mapping_type, mapping_key, grade, difficulty_min, difficulty_max)
);

COMMENT ON TABLE difficulty_mapping IS '难度-得分率映射表 - 存储不同维度的映射关系';
COMMENT ON COLUMN difficulty_mapping.mapping_type IS '映射类型: global(全局), knowledge_point(知识点), chapter(章节)';
COMMENT ON COLUMN difficulty_mapping.confidence IS '置信度: 基于样本量和标准差计算';

-- =====================================================
-- 4. 分数预估记录表
-- =====================================================

CREATE TABLE score_prediction (
    id SERIAL PRIMARY KEY,
    exam_name VARCHAR(200),                      -- 试卷名称
    grade VARCHAR(50),                           -- 年级
    total_score DECIMAL(5,2),                    -- 试卷总分
    question_count INT,                          -- 题目数量

    -- 预估结果
    predicted_average DECIMAL(5,2),              -- 预估平均分
    predicted_rate DECIMAL(4,3),                 -- 预估得分率
    confidence_lower DECIMAL(5,2),               -- 置信区间下限
    confidence_upper DECIMAL(5,2),               -- 置信区间上限
    reliability_score DECIMAL(4,3),              -- 可靠度评分

    -- 详细数据
    per_question_data JSONB DEFAULT '[]',        -- 每题预估详情
    warnings JSONB DEFAULT '[]',                 -- 警告信息

    -- 实际结果（考后填入）
    actual_average DECIMAL(5,2),                 -- 实际平均分
    prediction_error DECIMAL(5,2),               -- 预测误差

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE score_prediction IS '分数预估记录表 - 存储预估结果和考后反馈';
COMMENT ON COLUMN score_prediction.reliability_score IS '预估可靠度: 基于数据覆盖和样本量';
COMMENT ON COLUMN score_prediction.prediction_error IS '预测误差: actual_average - predicted_average';

-- =====================================================
-- 5. 创建索引
-- =====================================================

-- exam_history 索引
CREATE INDEX idx_exam_history_grade ON exam_history(grade);
CREATE INDEX idx_exam_history_exam_date ON exam_history(exam_date);
CREATE INDEX idx_exam_history_created_at ON exam_history(created_at);

-- question_performance 索引
CREATE INDEX idx_question_performance_exam_id ON question_performance(exam_id);
CREATE INDEX idx_question_performance_difficulty ON question_performance(absolute_difficulty);
CREATE INDEX idx_question_performance_knowledge_points ON question_performance USING gin(knowledge_points);

-- difficulty_mapping 索引
CREATE INDEX idx_difficulty_mapping_type ON difficulty_mapping(mapping_type);
CREATE INDEX idx_difficulty_mapping_grade ON difficulty_mapping(grade);
CREATE INDEX idx_difficulty_mapping_difficulty ON difficulty_mapping(difficulty_min, difficulty_max);

-- score_prediction 索引
CREATE INDEX idx_score_prediction_created_at ON score_prediction(created_at);
CREATE INDEX idx_score_prediction_grade ON score_prediction(grade);

-- =====================================================
-- 6. 插入冷启动默认映射数据
-- =====================================================

-- 为每个年级插入全局默认映射（冷启动用）
-- 难度区间: (0,2), (2,4), (4,6), (6,8), (8,10)
-- 默认得分率: 95%, 85%, 70%, 55%, 35%

INSERT INTO difficulty_mapping (mapping_type, mapping_key, grade, difficulty_min, difficulty_max, avg_score_rate, score_rate_stddev, sample_count, confidence, slope, intercept) VALUES
-- 高一
('global', NULL, '高一', 0, 2, 0.950, 0.050, 0, 0.5, -0.075, 1.025),
('global', NULL, '高一', 2, 4, 0.850, 0.080, 0, 0.5, -0.075, 1.025),
('global', NULL, '高一', 4, 6, 0.700, 0.100, 0, 0.5, -0.075, 1.025),
('global', NULL, '高一', 6, 8, 0.550, 0.120, 0, 0.5, -0.075, 1.025),
('global', NULL, '高一', 8, 10, 0.350, 0.150, 0, 0.5, -0.075, 1.025),
-- 高二
('global', NULL, '高二', 0, 2, 0.950, 0.050, 0, 0.5, -0.075, 1.025),
('global', NULL, '高二', 2, 4, 0.850, 0.080, 0, 0.5, -0.075, 1.025),
('global', NULL, '高二', 4, 6, 0.700, 0.100, 0, 0.5, -0.075, 1.025),
('global', NULL, '高二', 6, 8, 0.550, 0.120, 0, 0.5, -0.075, 1.025),
('global', NULL, '高二', 8, 10, 0.350, 0.150, 0, 0.5, -0.075, 1.025),
-- 高三
('global', NULL, '高三', 0, 2, 0.950, 0.050, 0, 0.5, -0.075, 1.025),
('global', NULL, '高三', 2, 4, 0.850, 0.080, 0, 0.5, -0.075, 1.025),
('global', NULL, '高三', 4, 6, 0.700, 0.100, 0, 0.5, -0.075, 1.025),
('global', NULL, '高三', 6, 8, 0.550, 0.120, 0, 0.5, -0.075, 1.025),
('global', NULL, '高三', 8, 10, 0.350, 0.150, 0, 0.5, -0.075, 1.025);

COMMENT ON TABLE difficulty_mapping IS '难度-得分率映射表 - 冷启动默认值基于教育统计经验';
