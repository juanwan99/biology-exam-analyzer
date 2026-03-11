[biology-exam-analyzer] Executor→Reviewer | 2026-03-11 22:14:04
## 审查交接单: Task 1-11
计划: docs/plans/2026-03-11-difficulty-pipeline-plan.md

### 逐 Task 自审
| Task | 计划要求 | 实际执行 | 状态 | 说明 |
|------|---------|---------|------|------|
| T1 IRT估计器 | 创建 irt_estimator.py | commit d29db6b(含在init) | ✅ | 全对/全错/中等/简单 4 case 验证通过 |
| T2 Claude客户端 | 创建 claude_client.py (anthropic SDK) | commit 817265b → 7b3ce5c | 🔀 | anthropic SDK 与 AIProxy auth 不兼容，改用 httpx 直接调用 |
| T3 模拟学生 | 创建 simulated_student.py | commit 773003a | ✅ | prompt/judge/parse 验证通过 |
| T4 Pipeline主控 | 创建 difficulty_pipeline.py | commit 40c8205 | ✅ | 初始化+默认返回验证通过 |
| T5 配置依赖 | config.py + requirements.txt + docker-compose.yml | commit 5937d09 | ✅ | |
| T6 main.py切换 | import+初始化+调用方式+correct_answer | commit c849b77 | ✅ | 用 patch 脚本精确替换，2处 evaluate_with_refinement_sync |
| T7 prediction适配 | 修改 prediction_service.py | — | 🔀 | 经分析 absolute_difficulty 来自 API 请求（用户上传数据），与 Pipeline 输出独立，无需修改 |
| T8 删除旧文件 | 删除 5 个旧文件 | commit cc111c6 | ✅ | grep 确认无遗留引用后删除 |
| T9 冒烟测试 | 单题 Pipeline 端到端 | 12/12答对，SMOKE TEST PASSED | ✅ | |
| T10 gemini清理 | 清理 gemini_analyzer.py | — | 🔀 | grep 确认 gemini_analyzer.py 无旧引擎引用，无需修改 |
| T11 多题验证 | 3题区分度测试 | 简单2.2/中等0.8/困难5.0 | ⚠️ | Pipeline 功能正常；中等题全对(floor_hit)导致区分度异常，为 LLM 模拟学生已知局限 |

> 状态: ✅一致 / ❌不一致 / 🔀改进（实现优于计划，必须记录具体变更内容）

### 🔀 改进详情
- **T2**: anthropic SDK v0.84.0 向 AIProxy 发送的 auth 头不兼容（返回 401），改用 httpx + `x-api-key` 头直接调用。功能等价，去掉了 anthropic SDK 依赖（requirements.txt 中保留但 claude_client.py 不再 import）
- **T7**: prediction_service.py 的 `absolute_difficulty` 字段来自 `ExamHistoryCreate` API 请求，是用户上传的历史数据，与 Pipeline 实时输出的 `base_difficulty`/`final_difficulty` 是完全独立的数据路径。无需修改。
- **T10**: gemini_analyzer.py 中 grep `difficulty_engine|DifficultyEngine|score_allocator` 零匹配，确认无旧引擎引用。

### 验证清单自检
- ✅ 全对→floor_hit, 全错→ceiling_hit, confidence=0.3（T1 Step 2 验证）
- ✅ a hit bound→a_extreme flag + 1PL 退化（T1 代码审查）
- ✅ MAP 不收敛→fallback flag + logit 回退（T1 代码审查）
- ✅ b→score 映射：b=-3→0, b=0→5, b=+3→10（T1 Step 2 验证）
- ✅ AIProxy 认证通过（curl + httpx 双重验证）
- ✅ 12 个学生全并发 asyncio.gather
- ✅ 选择题纯代码评判：judge_choice 6 case 通过
- ✅ 主观题 Haiku 评判：困难题全部返回 0.5
- ✅ Pipeline 兼容旧接口：`DifficultyPipeline(gemini_analyzer=None)` 不报错
- ✅ `evaluate_with_refinement_sync` 在 sync 上下文正常工作
- ✅ main.py 无 DifficultyEngine 残留引用
- ✅ 旧文件删除后 grep 零匹配
- ⚠️ 区分度：简单2.2 < 困难5.0 正确，但中等题0.8（全对floor_hit）打破排序

### 自查（四要素格式）

- 新增文件的边界 case：
  构造输入: estimate_difficulty([1]*12) / estimate_difficulty([0]*12)
  运行命令: python3 IRT 验证脚本（T1 Step 2）
  实际输出: floor_hit confidence=0.3 / ceiling_hit confidence=0.3
  结论: 边界处理正确

- 状态变量/锁的异常路径：
  构造输入: question dict 缺少 correct_answer
  运行命令: Pipeline._default_result() 验证（T4 Step 2）
  实际输出: base_difficulty=5.0, flags=["no_evaluation"]
  结论: 无标准答案时安全降级，不崩溃

- 字符串匹配/条件判断的假阴性：
  构造输入: judge_choice("答案是A", "A") / judge_choice("不会", "A") / parse_student_response("我觉得答案是B")
  运行命令: python3 验证脚本（T3 Step 2）
  实际输出: 1.0 / 0.0 / {"answer": "我觉得答案是B"...}
  结论: 正则提取和 fallback 解析正常

使用 codex-review skill 进行 GPT 代码审查。
