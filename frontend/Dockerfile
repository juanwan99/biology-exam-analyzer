FROM node:18-alpine AS builder

WORKDIR /app

# 使用淘宝npm镜像
COPY package*.json ./
RUN npm config set registry https://registry.npmmirror.com && npm install

# 复制源码并构建
COPY . .
RUN npm run build

# 生产环境：nginx托管静态文件
FROM nginx:alpine

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制nginx配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
