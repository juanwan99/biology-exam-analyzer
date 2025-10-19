#!/bin/bash

echo "========================================="
echo "  生物试卷分析系统 - 诊断脚本"
echo "========================================="
echo ""

# 检查1: .env文件
echo "🔍 检查环境变量配置..."
if [ -f .env ]; then
    echo "✅ .env 文件存在"

    # 检查必要变量
    if grep -q "GEMINI_API_KEY=请填入" .env; then
        echo "⚠️  警告: GEMINI_API_KEY 未配置，请修改 .env 文件"
    else
        echo "✅ GEMINI_API_KEY 已配置"
    fi

    if grep -q "ADMIN_PASSWORD=" .env; then
        echo "✅ ADMIN_PASSWORD 已配置"
    else
        echo "❌ ADMIN_PASSWORD 未配置"
    fi
else
    echo "❌ .env 文件不存在，正在创建..."
    cp .env.example .env
    echo "⚠️  请编辑 .env 文件填入真实的 API Key"
fi

echo ""

# 检查2: Docker服务
echo "🔍 检查Docker服务..."
if command -v docker &> /dev/null; then
    echo "✅ Docker 已安装"

    if docker ps &> /dev/null; then
        echo "✅ Docker 服务运行正常"
    else
        echo "❌ Docker 服务未启动"
        exit 1
    fi
else
    echo "❌ Docker 未安装"
    exit 1
fi

echo ""

# 检查3: 项目文件结构
echo "🔍 检查项目文件结构..."
REQUIRED_FILES=(
    "docker-compose.yml"
    "backend/Dockerfile"
    "backend/main.py"
    "backend/requirements.txt"
    "frontend/Dockerfile"
    "frontend/package.json"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file"
    else
        echo "❌ 缺失: $file"
    fi
done

echo ""

# 检查4: 必要目录
echo "🔍 检查必要目录..."
REQUIRED_DIRS=("logs" "prompts" "uploads")
for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        echo "✅ $dir/"
    else
        echo "⚠️  创建目录: $dir/"
        mkdir -p "$dir"
    fi
done

echo ""

# 检查5: Prompt文件
echo "🔍 检查Prompt模板..."
if [ -f "prompts/split_prompt.txt" ]; then
    echo "✅ split_prompt.txt ($(wc -c < prompts/split_prompt.txt) 字节)"
else
    echo "❌ 缺失 split_prompt.txt"
fi

if [ -f "prompts/analysis_prompt.txt" ]; then
    echo "✅ analysis_prompt.txt ($(wc -c < prompts/analysis_prompt.txt) 字节)"
else
    echo "❌ 缺失 analysis_prompt.txt"
fi

echo ""

# 检查6: Docker Compose配置
echo "🔍 验证Docker Compose配置..."
if docker-compose config &> /dev/null; then
    echo "✅ docker-compose.yml 配置有效"
else
    echo "❌ docker-compose.yml 配置错误"
    docker-compose config
    exit 1
fi

echo ""

# 检查7: 端口占用
echo "🔍 检查端口占用..."
if command -v netstat &> /dev/null; then
    if netstat -tuln | grep -q ":80 "; then
        echo "⚠️  端口 80 已被占用"
    else
        echo "✅ 端口 80 可用"
    fi

    if netstat -tuln | grep -q ":8000 "; then
        echo "⚠️  端口 8000 已被占用"
    else
        echo "✅ 端口 8000 可用"
    fi
else
    echo "⚠️  无法检查端口占用（netstat 未安装）"
fi

echo ""

# 检查8: 现有容器
echo "🔍 检查现有容器..."
CONTAINERS=$(docker ps -a --filter "name=biology" --format "{{.Names}} - {{.Status}}")
if [ -z "$CONTAINERS" ]; then
    echo "📝 无现有容器"
else
    echo "$CONTAINERS"
fi

echo ""
echo "========================================="
echo "  诊断完成"
echo "========================================="
echo ""
echo "💡 下一步操作建议："
echo ""
echo "1. 如果 GEMINI_API_KEY 未配置："
echo "   nano .env"
echo "   # 填入真实的 API Key"
echo ""
echo "2. 启动服务："
echo "   docker-compose up -d"
echo ""
echo "3. 查看日志："
echo "   docker-compose logs -f"
echo ""
echo "4. 停止服务："
echo "   docker-compose down"
