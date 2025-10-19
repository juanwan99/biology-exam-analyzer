# 生物试卷分析系统 - 部署文档

## 🚀 快速开始

### 1. 环境要求
- 1核2G服务器（阿里云/腾讯云等）
- 已安装 Docker 和 Docker Compose
- 公网IP（用于直接访问）

### 2. 安装Docker（如未安装）

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
sudo systemctl start docker
sudo systemctl enable docker

# 安装Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 3. 部署步骤

```bash
# 克隆项目（或上传到服务器）
cd /opt
git clone <your-repo-url> biology-analyzer
cd biology-analyzer

# 配置环境变量
cp .env.example .env
nano .env  # 填入真实的API Key和密码
```

`.env` 文件内容示例：
```env
GEMINI_API_KEY=AIzaSy...your_actual_key
ADMIN_PASSWORD=your_secure_password_123
```

```bash
# 一键启动
docker-compose up -d

# 查看启动状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 4. 访问服务

- **前端界面**: `http://你的公网IP`
- **管理后台**: `http://你的公网IP/admin`
- **API文档**: `http://你的公网IP/api/docs`

---

## 📁 项目结构

```
agent_shenti/
├── docker-compose.yml      # Docker编排文件
├── .env                    # 环境变量（不要提交到Git）
├── backend/                # 后端服务
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py            # FastAPI主程序
│   ├── logger.py          # 日志系统
│   ├── document_processor.py  # 文档处理
│   └── gemini_analyzer.py     # Gemini调用
├── frontend/               # 前端服务
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   └── src/
│       ├── pages/
│       │   ├── AnalyzerPage.jsx  # 主页面
│       │   └── AdminPage.jsx     # 管理后台
│       └── components/
│           └── ResultDisplay.jsx # 结果展示
├── prompts/                # Prompt模板目录（挂载卷）
│   ├── split_prompt.txt    # 拆分Prompt
│   └── analysis_prompt.txt # 分析Prompt
├── logs/                   # 日志目录（挂载卷）
└── uploads/                # 临时上传目录
```

---

## 🔧 常用命令

### Docker管理
```bash
# 启动服务
docker-compose up -d

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 查看日志
docker-compose logs -f backend
docker-compose logs -f frontend

# 重新构建镜像
docker-compose build --no-cache
docker-compose up -d
```

### 资源监控
```bash
# 查看容器资源占用
docker stats

# 查看磁盘空间
df -h

# 清理Docker缓存（慎用）
docker system prune -a
```

### 日志管理
```bash
# 实时查看今日日志
tail -f logs/$(date +%Y%m%d).log

# 查找错误日志
grep "ERROR" logs/*.log

# 清理7天前日志
find logs/ -name "*.log" -mtime +7 -delete
```

---

## 🛠️ 配置说明

### 资源限制（docker-compose.yml）
```yaml
backend:
  deploy:
    resources:
      limits:
        cpus: '0.7'      # 后端占70% CPU
        memory: 1400M    # 1.4G内存

frontend:
  deploy:
    resources:
      limits:
        cpus: '0.3'      # 前端占30% CPU
        memory: 600M     # 600M内存
```

### Nginx配置（frontend/nginx.conf）
```nginx
# 大文件上传限制
client_max_body_size 50M;

# API代理
location /api {
    proxy_pass http://backend:8000;
}
```

---

## 📝 Prompt管理

### 方式1: 网页管理（推荐）
1. 访问 `http://你的IP/admin`
2. 输入管理员密码
3. 在"Prompt管理"标签页编辑
4. 点击"保存并生效"

### 方式2: 直接编辑文件
```bash
# 编辑拆分Prompt
nano prompts/split_prompt.txt

# 编辑分析Prompt
nano prompts/analysis_prompt.txt

# 无需重启，下次调用自动生效
```

---

## 🔍 故障排查

### 问题1: 容器启动失败
```bash
# 查看详细日志
docker-compose logs

# 检查端口占用
netstat -tuln | grep -E '80|8000'

# 重新构建
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### 问题2: Gemini API调用失败
```bash
# 检查环境变量
docker-compose exec backend env | grep GEMINI

# 手动测试API
docker-compose exec backend python -c "
import google.generativeai as genai
import os
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-1.5-flash')
print(model.generate_content('Hello'))
"
```

### 问题3: 内存不足
```bash
# 查看内存占用
free -h

# 减少Uvicorn worker数量（已设置为1）
# 在backend/Dockerfile中确认:
CMD ["uvicorn", "main:app", "--workers", "1"]
```

### 问题4: 前端无法访问后端
```bash
# 检查网络连接
docker-compose exec frontend ping backend

# 检查nginx配置
docker-compose exec frontend cat /etc/nginx/conf.d/default.conf
```

---

## 🔐 安全建议

1. **修改默认密码**
   ```bash
   nano .env
   # 设置强密码: ADMIN_PASSWORD=YourStr0ngP@ssw0rd!
   docker-compose restart
   ```

2. **配置防火墙**
   ```bash
   # 仅开放80端口
   sudo ufw allow 80/tcp
   sudo ufw enable
   ```

3. **启用HTTPS（可选）**
   - 使用 Let's Encrypt 免费证书
   - 修改 nginx.conf 添加SSL配置

4. **API Key保护**
   ```bash
   # 确保.env不被Git追踪
   echo ".env" >> .gitignore
   ```

---

## 📊 性能优化

### 1. 日志轮转（防止磁盘占满）
```bash
# 添加定时任务
crontab -e

# 每天0点删除7天前日志
0 0 * * * find /opt/biology-analyzer/logs -name "*.log" -mtime +7 -delete
```

### 2. 限制上传文件大小
修改 `frontend/nginx.conf`:
```nginx
client_max_body_size 50M;  # 根据需要调整
```

### 3. Gemini调用优化
- 使用 `gemini-1.5-flash`（速度快）
- 避免并发调用（已串行处理）
- 图片压缩到85%质量

---

## 🎯 后期扩展

### 添加向量数据库（ChromaDB）

1. 修改 `backend/requirements.txt`:
   ```txt
   chromadb==0.4.22
   ```

2. 新建 `backend/vector_store.py`:
   ```python
   import chromadb

   class VectorStore:
       def __init__(self):
           self.client = chromadb.Client()
           self.collection = self.client.create_collection("biology_questions")

       def add_question(self, text, metadata):
           self.collection.add(
               documents=[text],
               metadatas=[metadata],
               ids=[f"q_{metadata['id']}"]
           )

       def search_similar(self, query, n=3):
           return self.collection.query(
               query_texts=[query],
               n_results=n
           )
   ```

3. 在 `main.py` 中集成到分析流程

### 添加数据可视化

前端使用 Chart.js 或 Recharts:
```bash
cd frontend
npm install recharts
```

---

## 📞 支持

遇到问题？
1. 查看日志: `docker-compose logs -f`
2. 检查磁盘空间: `df -h`
3. 查看资源占用: `docker stats`

---

**祝部署顺利！** 🎉
