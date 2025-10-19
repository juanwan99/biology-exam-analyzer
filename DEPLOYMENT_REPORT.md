# 生物试卷分析系统 - 部署完成报告

**生成时间**: 2025-10-18 15:08
**项目路径**: C:\Users\liang\agent_shenti

---

## ✅ 部署状态：成功

所有服务已正常启动并运行。

---

## 🌐 访问信息

| 服务 | 地址 | 说明 |
|------|------|------|
| **前端主页** | http://localhost:3000 | 上传试卷并查看分析结果 |
| **管理后台** | http://localhost:3000/admin | Prompt编辑 + 日志查看 |
| **后端API** | http://localhost:8000 | RESTful API接口 |
| **API文档** | http://localhost:8000/docs | Swagger交互式文档 |

---

## 🔑 配置信息

```bash
# Gemini API配置
模型版本:     gemini-2.0-flash-exp
API Key:      AIzaSyC9zMNPpF1dKQE082_Crna389enWW4X4Us

# 管理员密码
密码:         admin123

# 端口映射
前端端口:     3000 (原计划80，但被占用)
后端端口:     8000
```

---

## 📊 容器状态

```
NAME                IMAGE                   STATUS
biology_backend     agent_shenti-backend    ✅ Running (Up)
biology_frontend    agent_shenti-frontend   ✅ Running (Up)
```

**资源限制**:
- 后端: 0.7核CPU + 1.4G内存
- 前端: 0.3核CPU + 600M内存

---

## 🔧 已修复的问题

### 1. Docker镜像拉取失败
- **原因**: 国内网络无法访问daocloud镜像源
- **解决**: 手动拉取官方镜像 + 配置淘宝npm镜像源

### 2. Gemini模型404错误
- **原因**: `gemini-1.5-flash` 在当前API版本不可用
- **解决**: 切换到 `gemini-2.0-flash-exp`

### 3. JSON解析失败
- **原因**: Gemini返回Markdown格式的JSON (带```代码块)
- **解决**: 添加 `extract_json()` 函数智能提取纯JSON

### 4. 端口占用
- **原因**: 80和8080端口被其他服务占用
- **解决**: 前端改用3000端口

### 5. PostCSS配置错误
- **原因**: CommonJS格式与ESM模块冲突
- **解决**: 改用 `export default` 语法

---

## 📝 核心功能

### 1. 试卷分析流程

```
用户上传PDF → 文档转图片 → Gemini拆分题目 → 逐题深度分析 → 可视化展示
```

**支持格式**: PDF, DOCX (目前PDF已完整测试)

### 2. 分析维度

- ✅ 知识点标注
- ✅ 详细解析
- ✅ 难度评级 (简单/中等/困难)
- ✅ 易错点分析
- ✅ 参考答案

### 3. 管理功能

- ✅ 在线编辑拆分Prompt
- ✅ 在线编辑分析Prompt
- ✅ 网页查看运行日志
- ✅ 下载历史日志文件

---

## 🚀 快速使用

### 上传试卷分析

1. 访问 http://localhost:3000
2. 点击"选择试卷文件" → 选择PDF
3. 点击"开始分析"
4. 等待处理（约1-3分钟，取决于题目数量）
5. 查看详细分析结果

### 管理后台

1. 访问 http://localhost:3000/admin
2. 输入密码: `admin123`
3. 切换标签页:
   - **Prompt管理**: 编辑并保存模板
   - **日志查看**: 实时查看/下载日志

---

## 🛠️ 常用命令

### 服务管理

```bash
# 进入项目目录
cd C:\Users\liang\agent_shenti

# 查看容器状态
docker-compose ps

# 查看实时日志
docker-compose logs -f

# 重启服务
docker-compose restart

# 停止服务
docker-compose down

# 启动服务
docker-compose up -d
```

### 查看日志

```bash
# 后端日志
docker-compose logs backend --tail=50

# 前端日志
docker-compose logs frontend --tail=50

# 本地日志文件
type logs\20251018.log
```

### 重新构建

```bash
# 重新构建后端
docker-compose build backend
docker-compose up -d backend

# 重新构建前端
docker-compose build frontend
docker-compose up -d frontend
```

---

## 📂 项目结构

```
C:\Users\liang\agent_shenti\
├── docker-compose.yml           # Docker编排配置
├── .env                         # 环境变量 (含API Key)
├── backend/                     # 后端服务
│   ├── Dockerfile
│   ├── main.py                  # FastAPI主程序
│   ├── gemini_analyzer.py       # Gemini调用 + JSON提取
│   ├── document_processor.py    # PDF转图片
│   ├── logger.py                # 日志系统
│   └── requirements.txt
├── frontend/                    # 前端服务
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── src/
│   │   ├── pages/
│   │   │   ├── AnalyzerPage.jsx    # 主页面
│   │   │   └── AdminPage.jsx       # 管理后台
│   │   └── components/
│   │       └── ResultDisplay.jsx   # 结果展示
│   └── package.json
├── prompts/                     # Prompt模板 (可热更新)
│   ├── split_prompt.txt
│   └── analysis_prompt.txt
├── logs/                        # 日志目录
└── uploads/                     # 临时上传目录
```

---

## ⚠️ 注意事项

1. **API调用限制**: Gemini API可能有调用频率限制，请避免短时间内大量上传
2. **内存占用**: 1核2G服务器运行正常，但处理大文件可能较慢
3. **网络要求**: Gemini API调用可能需要科学上网（取决于地区）
4. **日志管理**: 建议定期清理 `logs/` 目录，避免占满磁盘

---

## 🔍 故障排查

### 问题1: 无法访问前端

```bash
# 检查容器状态
docker-compose ps

# 如果未运行
docker-compose up -d
```

### 问题2: 分析失败

```bash
# 查看后端日志
docker-compose logs backend --tail=100

# 常见原因:
# - Gemini API Key无效
# - 网络无法访问Gemini API
# - PDF格式不支持
```

### 问题3: Gemini连接超时

```bash
# 测试网络连通性
curl -I https://generativelanguage.googleapis.com

# 如果超时，检查科学上网配置
```

---

## 🎯 后续优化建议

1. **向量数据库**: 集成ChromaDB实现相似题查找
2. **Word支持**: 完善DOCX处理 (目前仅PDF可用)
3. **批量分析**: 支持一次上传多份试卷
4. **数据可视化**: 添加知识点分布、难度统计图表
5. **导出功能**: 支持导出Word/PDF格式的分析报告

---

## 📞 技术支持

- **日志位置**: `C:\Users\liang\agent_shenti\logs\`
- **配置文件**: `C:\Users\liang\agent_shenti\.env`
- **Prompt模板**: `C:\Users\liang\agent_shenti\prompts\`

---

**部署完成！系统已就绪，可以开始使用。** 🎉
