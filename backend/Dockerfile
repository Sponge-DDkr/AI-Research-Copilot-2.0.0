# ============================================
# AI Research Copilot — Backend Dockerfile
# ============================================

FROM python:3.13-slim

WORKDIR /app

# 安装编译依赖（sentence-transformers 需要 gcc/g++ 编译 torch）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（先复制 requirements 以利用 Docker 层缓存）
COPY requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir \
    -r /app/backend/requirements.txt

# 复制后端源码
COPY . /app/backend/

# 创建持久化目录
RUN mkdir -p /app/data /app/memory /app/data/models

# HuggingFace 模型缓存路径（BGE embedding ~1.3GB + reranker ~1.8GB）
ENV HF_HOME=/app/data/models
ENV SENTENCE_TRANSFORMERS_HOME=/app/data/models

# 健康检查（start-period 覆盖首次模型下载 ~5-15min，避免误报 unhealthy）
HEALTHCHECK --interval=60s --timeout=10s --start-period=900s --retries=3 \
    CMD curl -f http://localhost:8000/api/chat/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
