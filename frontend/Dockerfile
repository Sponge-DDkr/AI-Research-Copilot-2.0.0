# ============================================
# AI Research Copilot — Frontend Dockerfile
# ============================================

FROM node:22-alpine

WORKDIR /app

# 安装依赖（先复制 package 文件以利用 Docker 层缓存）
COPY package.json ./
RUN npm install

# 复制前端源码
COPY . .

# 后端服务地址（Docker Compose 服务名）
ENV BACKEND_URL=http://backend:8000

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
