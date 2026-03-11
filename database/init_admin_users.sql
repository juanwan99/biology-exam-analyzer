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

-- 索引
CREATE INDEX IF NOT EXISTS idx_operation_logs_user ON operation_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_operation_logs_target ON operation_logs(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_operation_logs_created ON operation_logs(created_at DESC);

-- 插入20个管理员账户（密码使用bcrypt hash）
-- 默认密码都是 bio2024!
-- 使用 python3 -c "import bcrypt; print(bcrypt.hashpw('bio2024!'.encode(), bcrypt.gensalt()).decode())"
INSERT INTO admin_users (username, password_hash, display_name, role) VALUES
('admin', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '系统管理员', 'admin'),
('teacher01', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师01', 'editor'),
('teacher02', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师02', 'editor'),
('teacher03', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师03', 'editor'),
('teacher04', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师04', 'editor'),
('teacher05', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师05', 'editor'),
('teacher06', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师06', 'editor'),
('teacher07', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师07', 'editor'),
('teacher08', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师08', 'editor'),
('teacher09', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师09', 'editor'),
('teacher10', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师10', 'editor'),
('teacher11', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师11', 'editor'),
('teacher12', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师12', 'editor'),
('teacher13', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师13', 'editor'),
('teacher14', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师14', 'editor'),
('teacher15', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师15', 'editor'),
('teacher16', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师16', 'editor'),
('teacher17', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师17', 'editor'),
('teacher18', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师18', 'editor'),
('teacher19', '$2b$12$DW5kZNrssL2YW0FCU0uIeOCEgRW129pm3Pr9tnvUJoNcnxVba6tgq', '教师19', 'editor')
ON CONFLICT (username) DO NOTHING;
