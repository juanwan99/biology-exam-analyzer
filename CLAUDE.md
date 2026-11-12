# 审题（biology-exam-analyzer）开工简报

上传 Word / PDF 试卷 → 拆题 → 每题 AI 分析（知识点 / 认知层级 / 难度 / 素养 / 分值）→ 整卷统计 + 分数预估（报告可选）。九学科，提示词在 `prompts/<学科>/`。流程规矩看正本 TASK-POLICY，这里只写代码。

## 主链路（改功能先找它在哪）

- 入口 `analysis_router.py`：`POST /api/analyze_auto` 起后台任务，前端轮询 `GET /api/analysis/status/{task_id}`
- 拆题：docx → `visual_word_splitter.split_word_with_visual`；pdf → `pdf_splitter.py`（`get_pdf_splitter().split`）
- 每题：`services/analysis_service.py` 的 `AnalysisService.analyze_question` → `question_analyzer.py`（知识点 / 认知层级）→ `difficulty_pipeline.py`（`feature_extractor.py` + `rule_scorer.py`）→ `competency_analyzer.py`
- 分值：`score_rules.py`，卷面写了分值以卷面为准，不交给 LLM 猜
- 整卷：`analysis_statistics.py`（统计）、`prediction_service.py`（分数预估，写 `score_prediction` 表）、`exam_diagnostics.py`
- 报告：`report_product_*.py`、`report_insights.py`

## 现成函数（先用，别另写）

- LLM 一律走 `llm_client.llm_call(messages, max_tokens, temperature, purpose=...)`：按 `llm_config.py` 的 PROVIDERS 走 fallback（文字 deepseek → qwen_text，带图自动走 qwen_vision）；400 / 401 / 403 和其他失败都会依次落到下一个 provider，带图只在视觉链里落。拼图文消息用 `llm_media.messages_with_media`
- LLM 出的 JSON：`llm_schemas.validate_llm_output`（失败不阻断，只打标）
- 学科：`subject_config.normalize_subject / get_competency_dims / is_valid_subject`（`normalize_subject` 静默降级 biology，不打日志；入口要自己先 `is_valid_subject` 判再告警，照 `analysis_router.analyze_auto` 写）；提示词：`prompt_loader.PromptLoader`
- 单例：`deps.get_*()`；任务 / 会话 / token：`task_manager`、`runtime_store`（SQLite）
- 请求级开关：`analysis_options`；整卷并发：`analysis_scheduling.gather_longest_first`（长题先跑）
- 特征缓存：`feature_cache`，改了特征提示词或口径要改 `_FEATURE_CACHE_VERSION`
- 测试假 LLM：`backend/tests/fakes/fake_llm_client.py`；`backend/tests/conftest.py` 自动隔离缓存和 runtime_store

## 写法

- 新接口另开 `xxx_router.py`，在 `main.py` 里 `include_router`；业务逻辑放 service，不写在路由里
- 超 2000 行的文件不加功能，新功能另起文件（`question_analyzer.py`、`report_product_html.py`、`report_product_model.py`、`backend/tests/test_feature_difficulty.py`）
- 优化只改通用环节（提示词、流程、模型、判法、映射表），禁止对着某道题、某份卷改结果凑数
- 仓公开：密钥、账号、真卷、成绩不进仓
- 报错用 `logger.exception` 保留堆栈；上传只收 .docx / .pdf
- 测试：本机只跑受影响的，`cd backend && /home/liang/.cache/bea-venv/bin/python -m pytest -q -p no:cacheprovider tests/test_xxx.py`；全量上 ECS（`ops/daily.sh` 里有）

## 现网与常见坑

- 河源 ECS `/home/ops/projects/biology-exam-analyzer`，是 git 工作树；发版和对账看 `ops/DEPLOY.md`，验收用 `ops/check-live.sh` / `ops/diff-live.sh` / `ops/daily.sh`，双入口看 `ops/DUAL-ENTRY.md`
- compose 命令都带 `-p biology`；后端 `./backend:/app` 挂载，改 .py 重启就行，前端要重建，compose 的 env 改了要 `up -d`
- `up -d backend` 后必须 `restart frontend`，不然 nginx 还连着旧 IP，会 502；重启后等健康过了 starting 再验收
- 本机 curl 要带 `--noproxy '*'`；现网镜像只有 LibreOffice Writer
- deepseek key 坏没坏，看日志看不出来，要在容器里请求 `/models` 看是不是 200（`ops/daily.sh` 会打印）
- `ops/check-live.sh` 会往 `score_prediction` 写一条记录，跑完自己删；ECS 上 `git pull` 卡住就改用 bundle（见 `ops/DEPLOY.md`）
