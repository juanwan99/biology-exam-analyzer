# 生物试卷智能分析系统 - 项目交接文档

**交接日期**: 2025-10-19
**项目状态**: 开发中（进度约50%）
**GitHub仓库**: https://github.com/juanwan99/biology-exam-analyzer
**Git标签**: v0.1-baseline（稳定基线版本）

---

## 🚀 快速启动

```bash
# 1. 进入项目目录
cd C:\Users\liang\agent_shenti

# 2. 配置环境变量（首次运行）
# 复制 .env.example 为 .env，填写 GEMINI_API_KEY

# 3. 启动所有服务
docker-compose up -d

# 4. 访问应用
# 前端: http://localhost
# 后端API: http://localhost:8000/docs
```

---

## ⚡ 修改Prompt的正确方法（重要！）

### ✅ 推荐方法：只需重启（5秒完成）

```bash
# 1. 编辑本地文件
notepad backend\prompts\analysis_prompt.txt
# 或
notepad backend\prompts\split_prompt.txt

# 2. 重启后端容器（新prompt立即生效）
docker-compose restart backend

# 完成！无需重新构建
```

**原理**：项目已配置卷挂载 `./backend/prompts:/app/prompts`，本地文件直接映射到容器内，修改后重启即可。

### ❌ 错误方法：重新构建（耗时3-5分钟）

```bash
# 不要这样做！太慢了
docker-compose build --no-cache backend
docker-compose up -d backend
```

### 📋 什么时候需要重建容器？

**不需要重建**（只需重启）：
- ✅ 修改 `backend/prompts/*.txt`
- ✅ 修改 `.env` 环境变量
- ✅ 修改 `uploads/` 文件
- ✅ 修改 `logs/` 日志配置

**需要重建**：
- ❌ 修改 `backend/*.py` Python代码
- ❌ 修改 `requirements.txt` 依赖
- ❌ 修改 `Dockerfile`
- ❌ 修改 `frontend/` 代码

---

## 📊 核心功能状态

### ✅ 已完成（50%）
- PDF/Word文档解析（文字、表格、图片提取）
- Gemini API题目拆分和分析
- 智能元素匹配（图表分配到题目）
- API频率限制（3秒间隔）
- Docker容器化部署
- Git版本管理 + GitHub远程仓库

### ⚠️ 已知问题
1. **详细分析过简**（正在修复中）
   - 原因：容器内使用了旧的超严格prompt
   - 解决：`docker-compose build --no-cache backend`

2. **图表渲染混乱**（已临时禁用）
   - 后端继续提取传给AI
   - 前端暂不显示，待优化

### ❌ 未开始（50%）
- 课标映射
- 逻辑检测
- 能力评估
- 用户体验优化（加载提示、错误处理、样式美化）

---

## 🗂️ 项目结构

```
agent_shenti/
├── backend/                     # 后端服务（FastAPI）
│   ├── main.py                 # 主入口
│   ├── document_processor.py   # 文档解析
│   ├── gemini_analyzer.py      # AI分析
│   └── prompts/                # AI提示词
│       ├── split_prompt.txt    # 题目拆分
│       └── analysis_prompt.txt # 题目分析（200-300字）
│
├── frontend/                    # 前端界面（React）
│   └── src/components/
│       └── ResultDisplay.jsx   # 结果展示
│
├── docker-compose.yml          # Docker编排
├── .env                        # 环境变量（需手动创建）
├── VERSION_CONTROL.md          # 版本管理指南
└── HANDOVER.md                 # 本文档
```

---

## 🔧 常用命令

### Docker操作
```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 查看日志
docker-compose logs backend --tail 100

# 重新构建（修改代码后）
docker-compose build --no-cache backend
docker-compose up -d
```

### Git操作
```bash
# 查看状态
git status

# 提交代码
git add .
git commit -m "feat: 功能描述"
git push

# 回退到基线版本
git checkout v0.1-baseline

# 恢复最新版本
git checkout main
```

---

## 📝 重要文件

### 后端核心
- `backend/main.py` 第77-167行：主分析流程
- `backend/gemini_analyzer.py` 第276-280行：删除了严格重试逻辑
- `backend/prompts/analysis_prompt.txt`：**关键**，控制分析详细程度

### 前端核心
- `frontend/src/components/ResultDisplay.jsx` 第98-107行：题目展示
- 第101-106行：图表渲染已注释（待优化）

---

## 🐛 故障排除

### 问题1：详细分析只有一句话
**解决**：
```bash
# 强制重新构建后端
docker-compose build --no-cache backend
docker-compose up -d backend

# 验证prompt
docker exec biology_backend sh -c "cat /app/prompts/analysis_prompt.txt | head -20"
```

### 问题2：服务无法启动
**解决**：
```bash
# 查看详细错误
docker-compose logs backend

# 完全重建
docker-compose down
docker-compose up -d --build
```

### 问题3：修改代码不生效
**解决**：使用 `--no-cache` 强制重新构建

---

## 🎯 下一步工作

### 立即任务（A核心功能）
1. ✅ 验证详细分析是否恢复正常（200-300字）
2. ✅ 确保题干和选项完整显示
3. ✅ 确认知识点、易错点字段完整

### 近期任务（B用户体验）
1. ⬜ 添加加载进度提示
2. ⬜ 优化错误提示
3. ⬜ 页面样式美化

### 中期任务（图表优化）
1. ⬜ 前端正确渲染表格（HTML）
2. ⬜ 前端正确显示图片（Base64）
3. ⬜ 优化图表排版

---

## 📞 重要资源

- **GitHub**: https://github.com/juanwan99/biology-exam-analyzer
- **API文档**: http://localhost:8000/docs
- **版本管理**: 参考 `VERSION_CONTROL.md`
- **详细诊断**: 参考 `图片表格问题诊断报告.md`

---

## ⚠️ 注意事项

1. **修改Prompt后必须重新构建容器**
2. **环境变量（.env）不要提交到Git**
3. **API Key使用OpenAI兼容接口（chataiapi.com）**
4. **已配置3秒频率限制，避免限流**
5. **图表功能：后端正常，前端已临时禁用**

---

**交接完成**
**下一步**: 验证详细分析修复效果，继续优化用户体验
