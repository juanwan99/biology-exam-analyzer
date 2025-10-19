#!/bin/bash

# 生物试卷分析系统 - 一键部署脚本

set -e  # 遇到错误立即退出

echo "========================================="
echo "  生物试卷分析系统 - 自动部署脚本"
echo "========================================="
echo ""

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo "❌ 未检测到Docker，正在安装..."
    curl -fsSL https://get.docker.com | sh
    sudo systemctl start docker
    sudo systemctl enable docker
    echo "✅ Docker安装完成"
else
    echo "✅ Docker已安装"
fi

# 检查Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "❌ 未检测到Docker Compose，正在安装..."
    sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    echo "✅ Docker Compose安装完成"
else
    echo "✅ Docker Compose已安装"
fi

echo ""
echo "========================================="
echo "  配置环境变量"
echo "========================================="
echo ""

# 检查.env文件
if [ ! -f .env ]; then
    echo "📝 未找到.env文件，正在创建..."
    cp .env.example .env

    echo "请输入Gemini API Key:"
    read -r GEMINI_KEY

    echo "请设置管理员密码:"
    read -r ADMIN_PASS

    # 写入.env
    cat > .env << EOF
GEMINI_API_KEY=${GEMINI_KEY}
ADMIN_PASSWORD=${ADMIN_PASS}
EOF
    echo "✅ 环境变量配置完成"
else
    echo "✅ .env文件已存在"
fi

echo ""
echo "========================================="
echo "  启动服务"
echo "========================================="
echo ""

# 构建并启动
echo "🔨 正在构建Docker镜像..."
docker-compose build

echo "🚀 正在启动容器..."
docker-compose up -d

echo ""
echo "⏳ 等待服务启动..."
sleep 5

# 检查容器状态
if docker-compose ps | grep -q "Up"; then
    echo "✅ 服务启动成功！"
    echo ""
    echo "========================================="
    echo "  访问信息"
    echo "========================================="
    echo ""

    # 获取公网IP（尝试多种方式）
    PUBLIC_IP=$(curl -s ifconfig.me || curl -s ipinfo.io/ip || hostname -I | awk '{print $1}')

    echo "🌐 前端界面: http://${PUBLIC_IP}"
    echo "🔧 管理后台: http://${PUBLIC_IP}/admin"
    echo "📚 API文档:  http://${PUBLIC_IP}/api/docs"
    echo ""
    echo "📋 查看日志: docker-compose logs -f"
    echo "🛑 停止服务: docker-compose down"
    echo ""
else
    echo "❌ 服务启动失败，请检查日志:"
    docker-compose logs
    exit 1
fi

# 设置日志清理定时任务
echo "⏰ 配置日志自动清理..."
CRON_JOB="0 0 * * * find $(pwd)/logs -name '*.log' -mtime +7 -delete"
(crontab -l 2>/dev/null | grep -v "biology-analyzer"; echo "$CRON_JOB") | crontab -
echo "✅ 已配置每日自动清理7天前日志"

echo ""
echo "========================================="
echo "  部署完成！"
echo "========================================="
