"""配置管理 — 环境变量 + .env 文件"""

import os
from pathlib import Path
from dataclasses import dataclass, field

from dotenv import load_dotenv

# 加载项目根目录的 .env 文件（backend/ 的父目录）
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


@dataclass
class Config:
    """全局配置，从环境变量加载"""

    # LLM
    deepseek_api_key: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", "")
    )
    deepseek_base_url: str = field(
        default_factory=lambda: os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        )
    )
    deepseek_model: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    )

    # Search
    tavily_api_key: str = field(
        default_factory=lambda: os.getenv("TAVILY_API_KEY", "")
    )

    # Server
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    cors_origins: list[str] = field(
        default_factory=lambda: os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
    )

    # Database
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", "sqlite:///./data/research.db"
        )
    )

    # ChromaDB
    chroma_persist_dir: str = field(
        default_factory=lambda: os.getenv(
            "CHROMA_PERSIST_DIR", "./data/chroma"
        )
    )

    # Agent
    max_iterations: int = field(
        default_factory=lambda: int(os.getenv("MAX_ITERATIONS", "20"))
    )
    tool_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("TOOL_TIMEOUT_SECONDS", "30"))
    )

    def validate(self) -> list[str]:
        """校验必要配置项，返回缺失项列表"""
        missing = []
        if not self.deepseek_api_key:
            missing.append("DEEPSEEK_API_KEY")
        if not self.tavily_api_key:
            missing.append("TAVILY_API_KEY (Phase 1 需要)")
        return missing


_config: Config | None = None


def get_config() -> Config:
    """获取全局配置单例"""
    global _config
    if _config is None:
        _config = Config()
    return _config
