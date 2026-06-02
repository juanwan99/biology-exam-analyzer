# 生物试卷智能分析系统 - 服务器部署指南

## 服务器信息
- **IP地址**: 117.72.183.223
- **系统**: Ubuntu 22.04.5 LTS
- **配置**: 2核CPU + 3.8GB内存 + 59GB磁盘

---

## 部署步骤

### 第一步：上传安装脚本到服务器

在本地Windows终端执行：
```bash
scp C:\Users\liang\agent_shenti\deploy\server_setup.sh ubuntu@117.72.183.223:~/
```

### 第二步：SSH登录服务器并运行安装脚本

```bash
ssh ubuntu@117.72.183.223
chmod +x ~/server_setup.sh
./server_setup.sh
```

安装脚本会自动完成：
1. 更新系统包
2. 安装Docker
3. 安装Docker Compose
4. 检查端口占用
5. 配置防火墙
6. 创建2GB Swap空间
7. 安装Git

### 第三步：重新登录SSH（使docker组权限生效）

```bash
exit
ssh ubuntu@117.72.183.223
```

验证Docker安装：
```bash
docker --version
docker-compose --version
```

### 第四步：克隆项目代码

```bash
cd ~
git clone https://github.com/juanwan99/biology-exam-analyzer.git
cd biology-exam-analyzer
git checkout feature/rule-based-splitting
```

### 第五步：配置环境变量

创建 `.env` 文件：
```bash
nano .env
```

填入以下内容（请替换为您的实际API密钥）：
```env
# DeepSeek API配置
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_API_BASE=https://api.deepseek.com/v1

# 管理员密码
ADMIN_PASSWORD=your_admin_password_here
```

保存并退出（Ctrl+X，然后Y，然后回车）

### 第六步：检查并释放端口占用

**重要：端口8000已被占用，需要处理**

查看占用进程：
```bash
sudo lsof -i :8000
```

如果需要停止：
```bash
sudo lsof -ti:8000 | xargs sudo kill -9
```

### 第七步：启动服务

```bash
docker-compose up -d
```

查看日志：
```bash
docker-compose logs -f
```

查看运行状态：
```bash
docker-compose ps
```

### 第八步：配置Nginx反向代理（可选，推荐）

如果要使用80端口访问，需要配置Nginx：

1. 安装Nginx：
```bash
sudo apt install -y nginx
```

2. 创建配置文件：
```bash
sudo nano /etc/nginx/sites-available/biology-analyzer
```

3. 填入配置：
```nginx
server {
    listen 80;
    server_name 117.72.183.223;

    client_max_body_size 50M;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 300s;
    }
}
```

4. 启用配置并重启Nginx：
```bash
sudo ln -s /etc/nginx/sites-available/biology-analyzer /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## 访问地址

### 直接访问（不使用Nginx）：
- 前端：http://117.72.183.223:3000
- 后端API：http://117.72.183.223:8000

### 通过Nginx访问（推荐）：
- 应用入口：http://117.72.183.223

---

## 常用运维命令

### 查看服务状态
```bash
docker-compose ps
```

### 查看日志
```bash
# 查看所有日志
docker-compose logs -f

# 只看后端日志
docker-compose logs -f backend

# 只看前端日志
docker-compose logs -f frontend
```

### 重启服务
```bash
# 重启全部
docker-compose restart

# 重启单个服务
docker-compose restart backend
docker-compose restart frontend
```

### 停止服务
```bash
docker-compose down
```

### 更新代码
```bash
cd ~/biology-exam-analyzer
git pull origin feature/rule-based-splitting
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### 清理磁盘空间
```bash
# 清理未使用的Docker镜像
docker system prune -a

# 查看磁盘使用
df -h
du -sh ~/biology-exam-analyzer/*
```

---

## 资源优化建议

由于服务器内存为3.8GB，建议：

1. **降低并发数**：编辑 `backend/main.py`，将 `max_workers=21` 改为 `max_workers=5`

2. **限制Docker内存**：编辑 `docker-compose.yml`：
```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 1.5G
  frontend:
    deploy:
      resources:
        limits:
          memory: 512M
```

3. **监控资源使用**：
```bash
# 实时监控
htop

# 查看Docker资源占用
docker stats
```

---

## 故障排查

### 服务无法启动
```bash
# 查看详细日志
docker-compose logs backend
docker-compose logs frontend

# 检查端口占用
sudo netstat -tuln | grep -E ":80|:3000|:8000"
```

### 内存不足
```bash
# 查看内存使用
free -h

# 查看Swap使用
swapon --show

# 清理内存缓存
sudo sync && sudo sysctl -w vm.drop_caches=3
```

### 磁盘空间不足
```bash
# 清理Docker
docker system prune -a --volumes

# 清理日志
sudo journalctl --vacuum-time=7d
```

---

## 安全建议

1. **配置防火墙**：
```bash
sudo ufw enable
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

2. **定期更新系统**：
```bash
sudo apt update && sudo apt upgrade -y
```

3. **备份数据**：
```bash
# 备份上传的文件和报告
tar -czf backup_$(date +%Y%m%d).tar.gz ~/biology-exam-analyzer/uploads ~/biology-exam-analyzer/reports
```

4. **修改默认密码**：
修改 `.env` 文件中的 `ADMIN_PASSWORD`
