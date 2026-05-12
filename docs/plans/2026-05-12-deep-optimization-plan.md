# 审题系统深度优化计划

> Topic: deep-optimization | Tier: T3 | Date: 2026-05-12

## 现有资产盘点（Q1）

| 层 | 已有 | 位置 | 证据 |
|----|------|------|------|
| LLM 客户端 | 统一 fallback 链（DeepSeek + Gemini） | `backend/llm_client.py` / `llm_config.py` | 上轮优化完成，128 tests passed |
| 兼容垫片 | `claude_client.py` 转发到 `llm_client` | `backend/claude_client.py:1-9` | 纯 re-export，2 处调用方未迁移 |
| 废弃配置 | `CLAUDE_API_BASE` 指向已死 `superaichao.xin` | `backend/config.py:23-27` | docker-compose 已删除此变量，config.py 残留 |
| 废弃 SDK | `google-generativeai` / `anthropic` / `openai` | `requirements.txt` | openai 被 `gaokao_extractor*.py` 直接 import（独立脚本） |
| numpy 依赖 | `difficulty_mapper.py` 生产使用 | `backend/difficulty_mapper.py:13` | `prediction_service.py:16` import 它 |
| auth 库 | 仅 `bcrypt` 实际使用 | `backend/auth_router.py:10,82,87` | `python-jose` / `passlib` / `PyJWT` 零引用 |
| 测试 | 156 collected, 139 passed, 14 failed, 3 errors | `pytest backend/ -q` | 详见 Batch 2 |
| 前端 | React 18 + Tailwind + Vite 5, 13 pages/components | `frontend/src/` | 5443 行 JSX，无测试 |
| 数据库 | PostgreSQL 16 + pgvector, 14 表 | `docker-compose.yml` | 总大小 ~16MB |
| 归档代码 | `archived/irt_estimator.py` + `simulated_student.py` | `backend/archived/` | 无人引用 |

## 增量 vs 新建论证（Q2）

全部变更都是增量清理，不新建任何系统。默认立场：删除死代码、修复已有测试、精简依赖。

## 交付路径（Q3）

- 后端变更：`docker-compose down && docker-compose up -d --build` 重建容器
- 前端不涉及代码变更（仅 `.gitignore` 调整）
- 生产 URL：无变化，清理不影响功能

---

## Batch 1: 死代码清理（8 文件）

### Task 1.1: 删除废弃 LLM 配置
- **文件**: `backend/config.py`
- **变更**: 删除 `CLAUDE_API_BASE` 和 `CLAUDE_API_KEY`（L23-27）
- **影响面**: grep `CLAUDE_API_BASE` → 仅 `config.py` 自身定义，无调用方
- **证据**: `docker-compose.yml` 已不传此变量；`llm_config.py` 独立管理 provider URL

### Task 1.2: 消除 claude_client.py 垫片
- **文件**: `backend/feature_extractor.py:8`, `backend/report_insights.py:9`
- **变更**: `from claude_client import send_message_gpt` → `from llm_client import send_message_gpt`
- **影响面**: 仅 2 处 import，函数签名完全一致（垫片是 re-export）
- **后续**: 删除 `backend/claude_client.py`

### Task 1.3: 清理 gemini_analyzer.py 构造函数
- **文件**: `backend/gemini_analyzer.py:17-19`
- **变更**: 删除 `api_key`/`api_base` 无用参数，更新类 docstring
- **影响面**: `deps.py:38` `GeminiAnalyzer()` 无参调用，不受影响

### Task 1.4: 清理 deps.py 废弃变量
- **文件**: `backend/deps.py:13`, `backend/main.py:16`
- **变更**: 删除 `deps.py` 中 `GEMINI_API_KEY` 变量；`main.py` 删除 `from deps import GEMINI_API_KEY`
- **影响面**: grep `GEMINI_API_KEY` in deps → 仅定义处，main.py 仅 import 处；实际使用已在 `llm_config.py` 中

### Task 1.5: 简化 competency_analyzer.py 的 extract_json 调用
- **文件**: `backend/competency_analyzer.py:21-33,100-102`
- **变更**: 删除 `gemini_analyzer` 参数，直接 `from gemini_analyzer import GeminiAnalyzer; GeminiAnalyzer.extract_json()` 静态调用
- **影响面**: `deps.py:54-55` 传入 `gemini_analyzer=g` → 删除该参数

### Task 1.6: 删除归档和垃圾文件
- **删除**: `backend/archived/` 目录, `backend/analysis_router.py.bak.20260331`
- **影响面**: grep `irt_estimator\|simulated_student` → 零引用

### Task 1.7: .gitignore 清理
- **变更**: 添加 `frontend/dist/` 到 `.gitignore`（构建产物不应入库）
- **影响面**: 仅 git 跟踪，不影响运行时（dist 已存在于 frontend 容器 image 中）

**测试契约 Batch 1:**
- 入口: `python -m pytest backend/ -q`
- 反例: 若 import 路径改错，pytest 收集阶段即 ImportError
- 边界: `competency_analyzer` 的 `extract_json` 不再依赖实例
- 回归: 139 passed 维持不变（死代码删除不应改变测试结果）
- 命令: `python -m pytest backend/ -q --tb=short`

---

## Batch 2: 测试修复（4 文件）

### Task 2.1: 修复 test_prompt_loader.py（6 failures）
- **根因**: 测试硬编码 `subject_prompts/` 路径，宿主机运行时此目录在 `prompts/`（docker 挂载为 `/app/subject_prompts`）
- **证据**: `FileNotFoundError: .../backend/subject_prompts/biology/split_prompt.txt` — 实际路径 `prompts/biology/split_prompt.txt`
- **修复**: 测试中用 `monkeypatch` 或修正 `PromptLoader` 初始化路径，使宿主机和容器均可运行

### Task 2.2: 修复 test_report_insights.py（3 failures）
- **根因**: `@pytest.mark.asyncio` 未注册 — 缺少 `pytest.ini` 或 `pyproject.toml` 的 asyncio_mode 配置
- **证据**: `PytestUnknownMarkWarning: Unknown pytest.mark.asyncio`
- **修复**: 添加 `pyproject.toml` 配置 `[tool.pytest.ini_options] asyncio_mode = "auto"`

### Task 2.3: 标记网络依赖测试
- **文件**: `backend/test_9subjects.py`, `backend/test_multisubject.py`, `backend/scripts/test_gemini_vision.py`
- **变更**: 添加 `@pytest.mark.skipif` 无 API key 时跳过，或 `@pytest.mark.integration`
- **影响面**: 3 个 ERROR → 3 个 SKIP

### Task 2.4: 删除 test_core_modules.py 中残留的 calibration 引用（如有）
- **验证**: 上轮已删除 TestCalibration，确认无残留

**测试契约 Batch 2:**
- 入口: `python -m pytest backend/ -q`
- 反例: 若 asyncio 配置错误，async test 仍报 `not natively supported`
- 边界: 无 API key 环境下 integration test 应 skip 而非 error
- 回归: 0 failed, 0 errors（全绿或全 skip）
- 命令: `python -m pytest backend/ -q --tb=short -v`

---

## Batch 3: 依赖瘦身（1 文件 + 容器重建）

### Task 3.1: 清理 requirements.txt
- **删除**: `google-generativeai`, `anthropic`, `python-jose`, `passlib`, `PyJWT`
- **保留**: `openai`（`gaokao_extractor.py` / `gaokao_extractor_v2.py` 直接 import）, `numpy`/`scipy`（`difficulty_mapper.py` 生产使用）, `bcrypt`（auth 唯一实际使用）
- **验证**: 容器重建后全量测试通过

### Evidence: 依赖删除决策

**decision**: 删除 5 个未使用的 pip 包
**evidence_refs**:
  - `grep -rn 'from openai\|import openai' backend/*.py` → 仅 `gaokao_extractor.py:13`, `gaokao_extractor_v2.py:12`（保留 openai）
  - `grep -rn 'jose\|passlib\|PyJWT' backend/*.py` → 零结果（删除三者）
  - `grep -rn 'anthropic' backend/*.py` → 零结果（删除）
  - `grep -rn 'google.generativeai\|google-generativeai' backend/*.py` → 零结果（删除）
  - `grep -rn 'numpy\|scipy' backend/*.py` → `difficulty_mapper.py:13` numpy 活跃（保留）
**Q1**: evidence_source: code-grep | evidence_state: verified
**impact_scope**: module (容器构建)
**unknowns**: none

**测试契约 Batch 3:**
- 入口: `docker-compose up -d --build && docker exec biology_backend python -m pytest -q`
- 反例: 若误删活跃依赖，容器启动即 ImportError
- 边界: `gaokao_extractor` 的 `openai` import 不受影响
- 回归: 容器内全量测试通过
- 命令: `docker-compose down && docker-compose up -d --build && docker exec biology_backend python -m pytest -q --tb=short`

---

## Batch 4: 安全与运维加固（2 文件）

### Task 4.1: 移除 docker-compose.yml 默认密码
- **变更**: `POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-biology123}` → `POSTGRES_PASSWORD=${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}`
- **前置**: 确认 `.env` 中已有 `POSTGRES_PASSWORD`

### Task 4.2: 添加 backend 健康检查
- **变更**: docker-compose.yml backend 服务增加 healthcheck（`curl -f http://localhost:8000/health`）
- **前置**: 确认 `/health` 端点存在

**测试契约 Batch 4:**
- 入口: `docker-compose up -d` 后 `docker ps` 检查健康状态
- 反例: 若 `.env` 缺 `POSTGRES_PASSWORD`，docker-compose 启动报错（预期行为）
- 边界: 健康检查间隔合理（不过载单 worker 服务）
- 回归: 所有容器正常运行
- 命令: `docker-compose down && docker-compose up -d && sleep 30 && docker ps`

---

## Contract Pack

### invariants
1. **LLM fallback 链不变**: DeepSeek → Gemini 顺序、per-provider proxy 机制不受任何 batch 影响 | verification: existing_test `test_llm_client.py`
2. **API 端点不变**: 所有 `/api/*` 路由签名和行为不变 | verification: existing_test `test_core_modules.py`
3. **认证机制不变**: bcrypt 密码校验逻辑不变 | verification: manual_grep `auth_router.py:82`

### counter_examples
1. **误删活跃 import**: 删 `claude_client.py` 但漏改 `feature_extractor.py` 的 import → `ImportError` at startup | tests_that_still_pass: 无（启动即崩） | mitigation: Batch 1 先改 import 再删文件，测试验证
2. **误删活跃依赖**: 删 `openai` 包导致 `gaokao_extractor.py` import 失败 → 高考题提取功能不可用 | tests_that_still_pass: 大部分测试不覆盖此模块 | mitigation: 已确认保留 openai

### risk_modules
- `backend/llm_client.py` — 不修改，但验证 Batch 1 的 import 变更不影响
- `backend/deps.py` — 修改惰性初始化逻辑，需确认单例行为不变
- `backend/competency_analyzer.py` — 修改构造函数签名

### test_debt
- 前端零测试 — 本次不处理，deadline: 下次前端功能迭代时补 | 理由: 本次仅后端优化
- `gaokao_extractor*.py` 无单元测试 — 独立脚本，使用频率低 | 理由: ROI 不足

### semantic_regression
- ORC-001: `llm_call()` 函数签名和 fallback 行为不变
- ORC-002: `GeminiAnalyzer.analyze_question()` 和 `split_questions()` 行为不变
- ORC-003: 所有 `@router` 端点路径和参数不变
