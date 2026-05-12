FROM python:3.11-slim-bookworm

# 安装系统依赖（pdf2image需要poppler，Word转换需要LibreOffice，weasyprint需要pango/cairo）
RUN apt-get update && apt-get install -y \
    poppler-utils \
    libreoffice-writer \
    libreoffice-core \
    fonts-wqy-zenhei \
    fonts-wqy-microhei \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev \
    shared-mime-info \
    locales \
    --no-install-recommends \
    && sed -i -e 's/# zh_CN.UTF-8 UTF-8/zh_CN.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

# 设置中文locale环境变量
ENV LANG=zh_CN.UTF-8 \
    LANGUAGE=zh_CN:zh \
    LC_ALL=zh_CN.UTF-8

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制应用代码
COPY . .

# 创建必要目录
RUN mkdir -p /app/logs /app/uploads /app/prompts

# 暴露端口
EXPOSE 8000

# 启动命令（单worker模式，适配1核2G）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
