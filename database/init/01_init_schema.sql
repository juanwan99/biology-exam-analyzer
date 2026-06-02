-- 生物教育资源数据库初始化脚本
-- 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================
-- 1. 教材资料库
-- =====================================================

-- 教材版本表
CREATE TABLE textbook_versions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,           -- 如：人教版、北师大版
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 教材章节表
CREATE TABLE textbook_chapters (
    id SERIAL PRIMARY KEY,
    version_id INT REFERENCES textbook_versions(id) ON DELETE CASCADE,
    grade VARCHAR(20) NOT NULL,            -- 高一/高二/高三
    semester VARCHAR(10),                  -- 上/下
    module_name VARCHAR(100),              -- 必修1/选择性必修2/选择性必修3
    chapter_num INT,                       -- 第几章
    chapter_name VARCHAR(200),             -- 章节名称
    section_num INT,                       -- 第几节（可为空表示章级别）
    section_name VARCHAR(200),             -- 节名称
    parent_id INT REFERENCES textbook_chapters(id), -- 父级章节
    sort_order INT DEFAULT 0,              -- 排序
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 教材内容表（存储具体内容段落）
CREATE TABLE textbook_contents (
    id SERIAL PRIMARY KEY,
    chapter_id INT REFERENCES textbook_chapters(id) ON DELETE CASCADE,
    content_type VARCHAR(50) DEFAULT 'text', -- text/concept/example/experiment/summary
    title VARCHAR(200),                     -- 段落标题（可选）
    content TEXT NOT NULL,                  -- 内容文本
    content_embedding VECTOR(1536),         -- 语义向量（用于相似搜索）
    page_num INT,                           -- 页码（可选）
    sort_order INT DEFAULT 0,
    metadata JSONB DEFAULT '{}',            -- 扩展信息
    created_at TIMESTAMP DEFAULT NOW()
);

-- 知识点表
CREATE TABLE knowledge_points (
    id SERIAL PRIMARY KEY,
    chapter_id INT REFERENCES textbook_chapters(id) ON DELETE SET NULL,
    name VARCHAR(200) NOT NULL,             -- 知识点名称
    description TEXT,                       -- 详细说明
    description_embedding VECTOR(1536),     -- 语义向量
    difficulty_level INT DEFAULT 3,         -- 1-5难度等级
    importance_level INT DEFAULT 3,         -- 1-5重要程度
    competency_tags JSONB DEFAULT '[]',     -- 关联的核心素养标签
    prerequisite_ids INT[],                 -- 前置知识点IDs
    keywords TEXT[],                        -- 关键词数组
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =====================================================
-- 2. 教辅题库
-- =====================================================

-- 题目来源表
CREATE TABLE exercise_sources (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,             -- 来源名称（五年高考、名校真题等）
    source_type VARCHAR(50),                -- 类型：高考/模拟/教辅/自编
    year INT,                               -- 年份
    region VARCHAR(100),                    -- 地区
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 题库表
CREATE TABLE exercise_bank (
    id SERIAL PRIMARY KEY,
    source_id INT REFERENCES exercise_sources(id) ON DELETE SET NULL,
    question_type VARCHAR(50) NOT NULL,     -- 选择题/填空题/实验题/综合题
    content TEXT NOT NULL,                  -- 题目内容
    content_embedding VECTOR(1536),         -- 语义向量
    options JSONB,                          -- 选项（选择题）{"A": "...", "B": "..."}
    answer TEXT,                            -- 答案
    explanation TEXT,                       -- 解析
    knowledge_point_ids INT[],              -- 关联知识点IDs
    chapter_ids INT[],                      -- 关联章节IDs
    difficulty_level DECIMAL(3,2),          -- 难度系数 0.00-1.00
    competency_scores JSONB,                -- 素养维度得分
    tags TEXT[],                            -- 标签
    usage_count INT DEFAULT 0,              -- 使用次数
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =====================================================
-- 3. 素材资源表（图片、实验视频等）
-- =====================================================

CREATE TABLE resources (
    id SERIAL PRIMARY KEY,
    resource_type VARCHAR(50) NOT NULL,     -- image/video/audio/document
    title VARCHAR(200),
    description TEXT,
    file_path VARCHAR(500),                 -- 文件存储路径
    file_size INT,                          -- 文件大小(bytes)
    mime_type VARCHAR(100),
    chapter_ids INT[],                      -- 关联章节
    knowledge_point_ids INT[],              -- 关联知识点
    tags TEXT[],
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

-- =====================================================
-- 4. 创建索引
-- =====================================================

-- 教材内容向量索引（使用IVFFlat加速相似搜索）
CREATE INDEX idx_textbook_contents_embedding ON textbook_contents
    USING ivfflat (content_embedding vector_cosine_ops) WITH (lists = 100);

-- 知识点向量索引
CREATE INDEX idx_knowledge_points_embedding ON knowledge_points
    USING ivfflat (description_embedding vector_cosine_ops) WITH (lists = 100);

-- 题库向量索引
CREATE INDEX idx_exercise_bank_embedding ON exercise_bank
    USING ivfflat (content_embedding vector_cosine_ops) WITH (lists = 100);

-- 其他常用索引
CREATE INDEX idx_textbook_chapters_version ON textbook_chapters(version_id);
CREATE INDEX idx_textbook_chapters_parent ON textbook_chapters(parent_id);
CREATE INDEX idx_textbook_contents_chapter ON textbook_contents(chapter_id);
CREATE INDEX idx_knowledge_points_chapter ON knowledge_points(chapter_id);
CREATE INDEX idx_exercise_bank_type ON exercise_bank(question_type);
CREATE INDEX idx_exercise_bank_difficulty ON exercise_bank(difficulty_level);

-- 全文搜索索引（中文需要额外配置，这里用基础的）
CREATE INDEX idx_textbook_contents_content ON textbook_contents USING gin(to_tsvector('simple', content));
CREATE INDEX idx_knowledge_points_name ON knowledge_points USING gin(to_tsvector('simple', name));

-- =====================================================
-- 5. 插入默认数据
-- =====================================================

-- 插入人教版教材版本
INSERT INTO textbook_versions (name, description) VALUES
('人教版', '人民教育出版社高中生物教材（2019年版）'),
('北师大版', '北京师范大学出版社高中生物教材');

-- 插入人教版必修一的章节结构示例
INSERT INTO textbook_chapters (version_id, grade, semester, module_name, chapter_num, chapter_name, sort_order) VALUES
(1, '高一', '上', '必修1：分子与细胞', 1, '走近细胞', 1),
(1, '高一', '上', '必修1：分子与细胞', 2, '组成细胞的分子', 2),
(1, '高一', '上', '必修1：分子与细胞', 3, '细胞的基本结构', 3),
(1, '高一', '上', '必修1：分子与细胞', 4, '细胞的物质输入和输出', 4),
(1, '高一', '上', '必修1：分子与细胞', 5, '细胞的能量供应和利用', 5),
(1, '高一', '上', '必修1：分子与细胞', 6, '细胞的生命历程', 6);

-- 插入必修二的章节
INSERT INTO textbook_chapters (version_id, grade, semester, module_name, chapter_num, chapter_name, sort_order) VALUES
(1, '高一', '下', '必修2：遗传与进化', 1, '遗传因子的发现', 10),
(1, '高一', '下', '必修2：遗传与进化', 2, '基因和染色体的关系', 11),
(1, '高一', '下', '必修2：遗传与进化', 3, '基因的本质', 12),
(1, '高一', '下', '必修2：遗传与进化', 4, '基因的表达', 13),
(1, '高一', '下', '必修2：遗传与进化', 5, '基因突变及其他变异', 14),
(1, '高一', '下', '必修2：遗传与进化', 6, '生物的进化', 15);

-- 插入选择性必修一的章节
INSERT INTO textbook_chapters (version_id, grade, semester, module_name, chapter_num, chapter_name, sort_order) VALUES
(1, '高二', '上', '选择性必修1：稳态与调节', 1, '人体的内环境与稳态', 20),
(1, '高二', '上', '选择性必修1：稳态与调节', 2, '神经调节', 21),
(1, '高二', '上', '选择性必修1：稳态与调节', 3, '体液调节', 22),
(1, '高二', '上', '选择性必修1：稳态与调节', 4, '免疫调节', 23),
(1, '高二', '上', '选择性必修1：稳态与调节', 5, '植物生命活动的调节', 24);

-- 插入选择性必修二的章节
INSERT INTO textbook_chapters (version_id, grade, semester, module_name, chapter_num, chapter_name, sort_order) VALUES
(1, '高二', '下', '选择性必修2：生物与环境', 1, '种群及其动态', 30),
(1, '高二', '下', '选择性必修2：生物与环境', 2, '群落及其演替', 31),
(1, '高二', '下', '选择性必修2：生物与环境', 3, '生态系统及其稳定性', 32),
(1, '高二', '下', '选择性必修2：生物与环境', 4, '人与环境', 33);

-- 插入选择性必修三的章节
INSERT INTO textbook_chapters (version_id, grade, semester, module_name, chapter_num, chapter_name, sort_order) VALUES
(1, '高三', '上', '选择性必修3：生物技术与工程', 1, '发酵工程', 40),
(1, '高三', '上', '选择性必修3：生物技术与工程', 2, '细胞工程', 41),
(1, '高三', '上', '选择性必修3：生物技术与工程', 3, '基因工程', 42),
(1, '高三', '上', '选择性必修3：生物技术与工程', 4, '生物技术的安全性与伦理问题', 43);

COMMENT ON TABLE textbook_versions IS '教材版本表';
COMMENT ON TABLE textbook_chapters IS '教材章节结构表';
COMMENT ON TABLE textbook_contents IS '教材内容表（支持向量搜索）';
COMMENT ON TABLE knowledge_points IS '知识点表（支持向量搜索）';
COMMENT ON TABLE exercise_bank IS '教辅题库表（支持向量搜索）';
COMMENT ON TABLE resources IS '素材资源表';
