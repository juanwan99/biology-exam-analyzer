#!/bin/bash
# 服务器环境安装脚本 - Ubuntu 22.04

set -e  # 遇到错误立即退出

echo "========================================="
echo "生物试卷智能分析系统 - 服务器环境配置"
echo "========================================="

# 1. 更新系统包
echo ""
echo "[1/6] 更新系统包..."
sudo apt update

# 2. 安装Docker
echo ""
echo "[2/6] 安装Docker..."
if ! command -v docker &> /dev/null; then
    sudo apt install -y docker.io
    sudo systemctl start docker
    sudo systemctl enable docker
    # 将当前用户添加到docker组（避免每次都要sudo）
    sudo usermod -aG docker $USER
    echo "✓ Docker安装完成"
else
    echo "✓ Docker已安装"
fi

# 3. 安装Docker Compose
echo ""
echo "[3/6] 安装Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    sudo apt install -y docker-compose
    echo "✓ Docker Compose安装完成"
else
    echo "✓ Docker Compose已安装"
fi

# 4. 检查端口占用
echo ""
echo "[4/6] 检查端口占用..."
if netstat -tuln | grep -q ":80 "; then
    echo "⚠️  警告: 端口80已被占用"
    netstat -tuln | grep ":80 "
fi

if netstat -tuln | grep -q ":8000 "; then
    echo "⚠️  警告: 端口8000已被占用"
    netstat -tuln | grep ":8000 "
    echo "提示: 如需停止占用进程，请运行: sudo lsof -ti:8000 | xargs sudo kill -9"
fi

# 5. 配置防火墙（UFW）
echo ""
echo "[5/6] 配置防火墙..."
if command -v ufw &> /dev/null; then
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
    sudo ufw allow 22/tcp  # 确保SSH不被阻止
    echo "✓ 防火墙规则已添加（80, 443, 22）"
else
    echo "✓ 未检测到UFW防火墙"
fi

# 6. 创建Swap空间（建议2GB）
echo ""
echo "[6/6] 创建Swap空间..."
if [ $(swapon --show | wc -l) -eq 0 ]; then
    echo "当前无Swap，创建2GB Swap空间..."
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    # 永久生效
    if ! grep -q '/swapfile' /etc/fstab; then
        echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    fi
    echo "✓ Swap空间创建完成"
else
    echo "✓ Swap已存在"
fi

# 7. 安装Git（如果未安装）
echo ""
echo "[7/7] 检查Git..."
if ! command -v git &> /dev/null; then
    sudo apt install -y git
    echo "✓ Git安装完成"
else
    echo "✓ Git已安装"
fi

echo ""
echo "========================================="
echo "✅ 环境配置完成！"
echo "========================================="
echo ""
echo "下一步："
echo "1. 重新登录SSH以使docker组权限生效: exit 然后重新 ssh ubuntu@117.72.183.223"
echo "2. 克隆项目代码"
echo "3. 配置环境变量"
echo "4. 启动服务"
echo ""
