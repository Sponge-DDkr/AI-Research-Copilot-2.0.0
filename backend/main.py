"""AI Research Copilot — FastAPI 入口"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_config

# Windows 终端 GBK 编码兼容 — 强制 stdout 用 UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时校验配置，关闭时清理资源"""
    config = get_config()
    missing = config.validate()

    # 启动提示
    print("[START] AI Research Copilot 启动中...")
    print(f"   LLM: {config.deepseek_model} @ {config.deepseek_base_url}")

    if missing:
        print(f"[WARN] 缺少以下配置项: {', '.join(missing)}")
        print(f"      请在 .env 文件中配置后再试")
    else:
        print("[OK] 所有配置项就绪")

    # 确保数据目录存在
    Path("./data").mkdir(exist_ok=True)

    yield  # 应用在此运行

    print("[STOP] AI Research Copilot 已关闭")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例"""
    config = get_config()

    app = FastAPI(
        title="AI Research Copilot",
        description="单 Agent 多工具自主研究与报告生成系统",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS 中间件 — 允许前端开发服务器跨域
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 初始化数据库
    from database import init_db
    init_db()

    # 初始化 ChromaDB 向量库
    from vector import ensure_collections
    ensure_collections()

    # 注册路由
    from api.chat import router as chat_router
    from api.research import router as research_router
    from api.history import router as history_router
    from api.knowledge import router as knowledge_router

    app.include_router(chat_router, prefix="/api")
    app.include_router(research_router, prefix="/api")
    app.include_router(history_router, prefix="/api")
    app.include_router(knowledge_router, prefix="/api")

    return app


app = create_app()


# ============ 开发模式直接运行 ============
if __name__ == "__main__":
    import uvicorn

    config = get_config()
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=False,  # Windows 上 reload 会导致孤儿进程占用端口
    )
