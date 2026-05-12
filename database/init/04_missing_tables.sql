-- 补充 ORM 中定义但 init SQL 中缺失的 4 张表
-- 2026-05-12 审计补丁

-- 管理员用户表
CREATE TABLE IF NOT EXISTS admin_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(100),
    role VARCHAR(20) DEFAULT 'editor',
    is_active INTEGER DEFAULT 1,
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 操作日志表
CREATE TABLE IF NOT EXISTS operation_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES admin_users(id) ON DELETE SET NULL,
    username VARCHAR(50),
    operation VARCHAR(50) NOT NULL,
    target_type VARCHAR(50) NOT NULL,
    target_id INTEGER,
    target_name VARCHAR(200),
    old_value JSONB,
    new_value JSONB,
    ip_address VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_oplog_user ON operation_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_oplog_op ON operation_logs(operation);
CREATE INDEX IF NOT EXISTS idx_oplog_target ON operation_logs(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_oplog_created ON operation_logs(created_at);

-- 教材页面表
CREATE TABLE IF NOT EXISTS textbook_pages (
    id SERIAL PRIMARY KEY,
    book_id VARCHAR(50) NOT NULL,
    book_name VARCHAR(200) NOT NULL,
    page_num INTEGER NOT NULL,
    markdown_content TEXT,
    chapter_info JSONB DEFAULT '{}',
    image_path VARCHAR(500),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tp_book ON textbook_pages(book_id);

-- 教材切片表
CREATE TABLE IF NOT EXISTS textbook_chunks (
    id SERIAL PRIMARY KEY,
    page_id INTEGER REFERENCES textbook_pages(id) ON DELETE CASCADE,
    book_id VARCHAR(50) NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_content TEXT NOT NULL,
    page_num INTEGER,
    chapter_info JSONB DEFAULT '{}',
    embedding VECTOR(384),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tc_book ON textbook_chunks(book_id);
CREATE INDEX IF NOT EXISTS idx_tc_page ON textbook_chunks(page_id);
