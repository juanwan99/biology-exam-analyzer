-- B0: prediction 相关表建表（对齐 models.py ORM 定义）
-- 幂等：IF NOT EXISTS

CREATE TABLE IF NOT EXISTS exam_history (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    exam_date TIMESTAMP,
    grade VARCHAR(50) NOT NULL,
    student_count INTEGER,
    total_score DECIMAL(5,2) NOT NULL,
    average_score DECIMAL(5,2),
    score_rate DECIMAL(4,3),
    difficulty_avg DECIMAL(4,2),
    source_file VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_exam_history_grade_date ON exam_history(grade, exam_date);

CREATE TABLE IF NOT EXISTS question_performance (
    id SERIAL PRIMARY KEY,
    exam_id INTEGER REFERENCES exam_history(id) ON DELETE CASCADE,
    question_number INTEGER NOT NULL,
    absolute_difficulty DECIMAL(4,2),
    knowledge_complexity DECIMAL(4,2),
    cognitive_level DECIMAL(4,2),
    question_score DECIMAL(5,2) NOT NULL,
    actual_average DECIMAL(5,2),
    score_rate DECIMAL(4,3),
    knowledge_points JSONB DEFAULT '[]',
    textbook_chapter VARCHAR(100),
    question_type VARCHAR(50),
    question_content TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_qp_exam_question ON question_performance(exam_id, question_number);
CREATE INDEX IF NOT EXISTS idx_qp_difficulty ON question_performance(absolute_difficulty);

CREATE TABLE IF NOT EXISTS difficulty_mapping (
    id SERIAL PRIMARY KEY,
    mapping_type VARCHAR(50) NOT NULL,
    mapping_key VARCHAR(200),
    grade VARCHAR(50) NOT NULL,
    difficulty_min DECIMAL(4,2) NOT NULL,
    difficulty_max DECIMAL(4,2) NOT NULL,
    avg_score_rate DECIMAL(4,3),
    score_rate_stddev DECIMAL(4,3),
    sample_count INTEGER DEFAULT 0,
    confidence DECIMAL(4,3),
    slope DECIMAL(10,8),
    intercept DECIMAL(10,8),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_dm_type_grade ON difficulty_mapping(mapping_type, grade);

CREATE TABLE IF NOT EXISTS score_prediction (
    id SERIAL PRIMARY KEY,
    exam_name VARCHAR(200),
    grade VARCHAR(50),
    total_score DECIMAL(5,2),
    question_count INTEGER,
    predicted_average DECIMAL(5,2),
    predicted_rate DECIMAL(4,3),
    confidence_lower DECIMAL(5,2),
    confidence_upper DECIMAL(5,2),
    reliability_score DECIMAL(4,3),
    per_question_data JSONB DEFAULT '[]',
    warnings JSONB DEFAULT '[]',
    actual_average DECIMAL(5,2),
    prediction_error DECIMAL(5,2),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_sp_grade ON score_prediction(grade);
