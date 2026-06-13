-- 九学科适配：为存量表追加 subject 列（兼容式：加列 + 默认 biology，不破坏存量数据）
-- 幂等：IF NOT EXISTS，可重复执行。存量行自动归类 biology。
ALTER TABLE exercise_bank        ADD COLUMN IF NOT EXISTS subject VARCHAR(50) NOT NULL DEFAULT 'biology';
ALTER TABLE exam_history         ADD COLUMN IF NOT EXISTS subject VARCHAR(50) NOT NULL DEFAULT 'biology';
ALTER TABLE question_performance ADD COLUMN IF NOT EXISTS subject VARCHAR(50) NOT NULL DEFAULT 'biology';
ALTER TABLE score_prediction     ADD COLUMN IF NOT EXISTS subject VARCHAR(50) NOT NULL DEFAULT 'biology';

CREATE INDEX IF NOT EXISTS idx_exercise_bank_subject        ON exercise_bank(subject);
CREATE INDEX IF NOT EXISTS idx_exam_history_subject         ON exam_history(subject);
CREATE INDEX IF NOT EXISTS idx_question_performance_subject ON question_performance(subject);
CREATE INDEX IF NOT EXISTS idx_score_prediction_subject     ON score_prediction(subject);
