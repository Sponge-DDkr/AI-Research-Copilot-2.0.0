"""数据库层 — SQLAlchemy 2.0 ORM，管理报告持久化存储"""

from datetime import datetime, timezone, timedelta
from pathlib import Path

from sqlalchemy import Column, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# 北京时间
CST = timezone(timedelta(hours=8))

# 数据库文件路径
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "research.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# 引擎（WAL 模式 + 连接池复用）
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
    echo=False,
)

# Session 工厂
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# ── ORM 基类 ──
class Base(DeclarativeBase):
    pass


class Report(Base):
    """研究报告模型 — 对应 reports 表"""

    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task = Column(Text, nullable=False)
    report = Column(Text, nullable=False)
    depth = Column(String(16), default="auto")
    iterations = Column(Integer, default=0)
    plan_steps = Column(Integer, default=0)
    events_json = Column(Text, default="[]")
    created_at = Column(String(20), nullable=False)


class ToolLog(Base):
    """Agent 工具执行日志 — 对应 tool_logs 表（调试 + 复盘用）"""

    __tablename__ = "tool_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task = Column(Text, nullable=False, comment="所属研究任务")
    tool_name = Column(String(64), nullable=False, comment="工具名称")
    arguments_json = Column(Text, default="{}", comment="工具参数 JSON")
    result_preview = Column(Text, default="", comment="结果摘要（前 500 字符）")
    status = Column(String(16), default="success", comment="success / error / timeout")
    duration_ms = Column(Integer, default=0, comment="执行耗时（毫秒）")
    created_at = Column(String(20), nullable=False)


# ── 数据库初始化 ──
def init_db():
    """建表（幂等：Base.metadata.create_all 默认 checkfirst=True）"""
    # 启用 WAL 模式（在引擎创建后、建表前执行）
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)


# ── CRUD ──
def _row_to_dict(r: Report) -> dict:
    """将 ORM 对象转为 dict，向下游保持兼容"""
    return {
        "id": r.id,
        "task": r.task,
        "report": r.report,
        "depth": r.depth,
        "iterations": r.iterations,
        "plan_steps": r.plan_steps,
        "events_json": r.events_json,
        "created_at": r.created_at,
    }


def save_report(
    task: str,
    report: str,
    depth: str = "auto",
    iterations: int = 0,
    plan_steps: int = 0,
    events_json: str = "[]",
) -> int:
    """保存报告，返回新记录 ID"""
    created_at = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    with SessionLocal() as session:
        r = Report(
            task=task,
            report=report,
            depth=depth,
            iterations=iterations,
            plan_steps=plan_steps,
            events_json=events_json,
            created_at=created_at,
        )
        session.add(r)
        session.commit()
        return r.id


def get_reports(limit: int = 20, offset: int = 0) -> list[dict]:
    """获取历史报告列表（按时间倒序，不含完整报告内容，仅含 preview）"""
    from sqlalchemy import select

    with SessionLocal() as session:
        stmt = (
            select(Report)
            .order_by(Report.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = session.execute(stmt).scalars().all()
        return [
            {
                "id": r.id,
                "task": r.task,
                "depth": r.depth,
                "iterations": r.iterations,
                "plan_steps": r.plan_steps,
                "created_at": r.created_at,
                "preview": r.report[:200] if r.report else "",
            }
            for r in rows
        ]


def get_report_by_id(report_id: int) -> dict | None:
    """根据 ID 获取完整报告，不存在返回 None"""
    from sqlalchemy import select

    with SessionLocal() as session:
        r = session.execute(
            select(Report).where(Report.id == report_id)
        ).scalar_one_or_none()
        if not r:
            return None
        return _row_to_dict(r)


def delete_report(report_id: int) -> bool:
    """删除报告，返回是否删除成功"""
    from sqlalchemy import select

    with SessionLocal() as session:
        r = session.execute(
            select(Report).where(Report.id == report_id)
        ).scalar_one_or_none()
        if not r:
            return False
        session.delete(r)
        session.commit()
        return True


# ── ToolLog CRUD ──


def delete_all_reports() -> int:
    """删除所有历史报告 + 工具日志，返回删除的总记录数"""
    from sqlalchemy import delete as sql_delete

    with SessionLocal() as session:
        result_reports = session.execute(sql_delete(Report))
        result_logs = session.execute(sql_delete(ToolLog))
        session.commit()
        return result_reports.rowcount + result_logs.rowcount


def save_tool_log(
    task: str,
    tool_name: str,
    arguments_json: str = "{}",
    result_preview: str = "",
    status: str = "success",
    duration_ms: int = 0,
) -> int:
    """保存一条工具执行日志，返回记录 ID"""
    created_at = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    with SessionLocal() as session:
        log = ToolLog(
            task=task,
            tool_name=tool_name,
            arguments_json=arguments_json,
            result_preview=result_preview[:500],
            status=status,
            duration_ms=duration_ms,
            created_at=created_at,
        )
        session.add(log)
        session.commit()
        return log.id


def get_tool_logs(task: str = "", limit: int = 50, offset: int = 0) -> list[dict]:
    """获取工具执行日志（可按任务筛选）"""
    from sqlalchemy import select

    with SessionLocal() as session:
        stmt = select(ToolLog).order_by(ToolLog.created_at.desc())
        if task:
            stmt = stmt.where(ToolLog.task == task)
        stmt = stmt.limit(limit).offset(offset)
        rows = session.execute(stmt).scalars().all()
        return [
            {
                "id": r.id,
                "task": r.task,
                "tool_name": r.tool_name,
                "arguments_json": r.arguments_json,
                "result_preview": r.result_preview,
                "status": r.status,
                "duration_ms": r.duration_ms,
                "created_at": r.created_at,
            }
            for r in rows
        ]
