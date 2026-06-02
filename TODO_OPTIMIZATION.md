# 优化待办清单

> 调研日期: 2026-02-05
> 策略: 边开发边优化，涉及相关区域时顺手改进

---

## P0 — 安全问题（涉及时必须修复）

### 路径穿越漏洞
- **位置**: `backend/main.py` ~行1270
- **问题**: `".." in path` 防护可被 URL 编码绕过
- **修复**: 使用 `Path.resolve()` + 基目录白名单校验
- **触发时机**: 修改文件上传/下载相关功能时

### 认证机制薄弱
- **位置**: `backend/main.py` ~行360
- **问题**: 明文比对、无速率限制、无密码哈希
- **修复**: bcrypt 哈希 + 登录限流(5次/分钟) + IP 记录
- **触发时机**: 改动认证/权限相关功能时

### 输入验证缺失
- **位置**: `backend/main.py` ~行861 (corrected_questions)
- **问题**: 直接 `json.loads()` 无 Schema 验证
- **修复**: Pydantic 模型校验 + 请求体大小限制
- **触发时机**: 新增或修改 API 接口时，新接口必须有校验

---

## P1 — 性能瓶颈（涉及时优先优化）

### 并发模型不匹配
- **位置**: `backend/main.py` ~行649, 934
- **问题**: ThreadPoolExecutor 阻塞 FastAPI 事件循环
- **优化**: asyncio.gather + Semaphore 替代
- **触发时机**: 重构分析流程或新增并发任务时

### API 频率控制过度保守
- **位置**: `backend/question_analyzer.py` ~行36-87
- **问题**: 所有请求共享 0.2s 固定延迟，100题光延迟就20秒
- **优化**: Semaphore 控制并发数（5路并行），取消固定延迟
- **触发时机**: 优化分析速度或更换 AI API 时

### Session 内存泄漏
- **位置**: `backend/main.py` ~行156-208
- **问题**: OrderedDict 存 session，无大小上限
- **优化**: 迁移 Redis 或加最大数量限制 + 主动清理
- **触发时机**: 新增需要 session 的功能时

### 数据库连接池太小
- **位置**: `backend/database.py` ~行28-30
- **问题**: pool_size=5，但有21个并发线程
- **优化**: pool_size=20, max_overflow=5
- **触发时机**: 遇到数据库连接超时或新增并发数据库操作时

---

## P2 — 代码质量（日常开发中逐步改进）

### main.py 过于臃肿
- **问题**: 路由、业务逻辑、Session管理、工具函数全在一个文件
- **优化**: 新功能用独立 router 文件，逐步从 main.py 中拆出
- **触发时机**: 每次新增功能时

### 代码重复
- **位置**: `infer_question_type()` 在多处重复定义
- **优化**: 提取到 utils 模块统一调用
- **触发时机**: 修改题型识别逻辑时

### 错误处理不完整
- **问题**: 多处 `except Exception` 吞异常，不区分可重试/不可重试
- **优化**: 分类异常，API 429 自动重试，保留堆栈信息
- **触发时机**: 修改 AI 调用或数据处理逻辑时

### 日志混乱
- **位置**: `backend/logger.py` + main.py 各处
- **问题**: 无轮转、DEBUG内容用INFO打印
- **优化**: RotatingFileHandler + 正确日志级别
- **触发时机**: 排查问题发现日志不好用时

---

## P3 — 增强功能（后续规划）

### 数据库向量索引
- **位置**: `backend/models.py`
- **问题**: embedding 列缺少 HNSW 索引，语义搜索慢
- **触发时机**: 题库规模增大或搜索变慢时

### 前端体验
- [ ] 分析进度实时反馈（WebSocket）
- [ ] 大量题目虚拟列表渲染
- [ ] 结果导出 CSV/Excel
- [ ] 超时/重试机制

### 监控告警
- [ ] API 响应时间统计
- [ ] 错误率监控
- [ ] 磁盘/内存使用告警

---

## 已完成

> 优化完成后移到这里，记录日期和改动内容

### 2026-03-12: P0 安全修复（全部完成）
- **路径穿越**: Path.resolve() + 基目录白名单校验（uploads + reports）
- **认证机制**: Header(verify_admin) → Depends(verify_admin)，hmac.compare_digest timing-safe 比较
- **登录限流**: 5次/分钟 IP 限流（auth_router.py）
- **输入验证**: corrected_questions 添加 Pydantic QuestionCorrection schema
