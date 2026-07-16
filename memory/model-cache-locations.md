---
name: model-cache-locations
description: 本地依赖缓存路径和磁盘占用——HuggingFace 模型（启动需跳过联网检查）、Python 包、Node 包
metadata:
  type: project
---

# 依赖缓存路径与磁盘占用

## HuggingFace 模型缓存

- **路径**：`~/.cache/huggingface/hub/`（`C:\Users\邓凤坤\.cache\huggingface\hub\`）
- **大小**：~4.6 GB
- **包含模型**：
  - `BAAI/bge-large-zh-v1.5`（embedding, 1024维）~1.3 GB
  - `BAAI/bge-reranker-v2-m3`（Cross-Encoder Reranker）~1.8 GB
  - 其他依赖模型 ~1.5 GB
- **启动注意事项**：sentencetransformers 每次 import 会联网检查模型配置文件更新（HEAD 请求 `huggingface.co`），国内网络不通导致超时重试（每个文件重试 5 次，约 23 秒），多个配置文件累计阻塞 > 1 分钟
- **解决方案**：启动前设置 `HF_HUB_OFFLINE=1` 跳过联网检查，或 `HF_ENDPOINT=https://hf-mirror.com` 走镜像

## Python 包

- **用户级 site-packages**：`C:\Users\邓凤坤\AppData\Roaming\Python\Python312\site-packages`
- **大小**：~1.2 GB（45,119 个文件）
- **关键包**：fastapi, chromadb, sentence-transformers, torch, httpx, sqlalchemy, pydantic 等
- **Conda 基础环境**：`D:\ProgramData\miniconda3\Lib\site-packages\`

## Node.js 包

- **路径**：`frontend/node_modules/`
- **大小**：~208 MB
- **关键包**：react 19, antd 6, tailwindcss 4, vite, typescript 等

## 项目运行时数据

- **路径**：`data/`
- **大小**：~3.3 MB
- **内容**：SQLite 数据库 + ChromaDB 向量索引

## 总计

约 **6 GB**（模型 4.6G + Python 包 1.2G + Node 包 0.2G + 项目数据 < 0.01G）

**Why:** 知道每个缓存放哪里，遇到启动问题能快速定位。HuggingFace 离线启动是关键——连不上 hf.co 不是项目 bug，是网络墙的正常现象。

**How to apply:** 每次启动后端前检查是否需要 `HF_HUB_OFFLINE=1`；换机器部署时优先用镜像 `HF_ENDPOINT=https://hf-mirror.com`；清理缓存时知道 4.6G 的模型缓存不要删（除非要重下）。
