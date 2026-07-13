"""历史记录 API — 报告的 CRUD 操作"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from database import get_reports, get_report_by_id, delete_report, delete_all_reports, get_tool_logs

router = APIRouter(tags=["history"])


class ReportListItem(BaseModel):
    id: int
    task: str
    depth: str
    iterations: int
    plan_steps: int
    created_at: str
    preview: str


class ReportDetail(BaseModel):
    id: int
    task: str
    report: str
    depth: str
    iterations: int
    plan_steps: int
    events_json: str
    created_at: str


@router.get("/history", response_model=list[ReportListItem])
async def list_history(limit: int = 20, offset: int = 0):
    """获取历史报告列表（不含完整内容，按时间倒序）"""
    return get_reports(limit=limit, offset=offset)


@router.get("/history/{report_id}", response_model=ReportDetail)
async def get_history_detail(report_id: int):
    """获取单个报告的完整内容"""
    report = get_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"报告 #{report_id} 不存在")
    return report


@router.delete("/history/{report_id}")
async def delete_history(report_id: int):
    """删除一个历史报告"""
    ok = delete_report(report_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"报告 #{report_id} 不存在")
    return {"ok": True, "message": f"报告 #{report_id} 已删除"}


@router.delete("/history")
async def clear_all_history():
    """清空所有历史报告"""
    count = delete_all_reports()
    return {"ok": True, "message": f"已清空 {count} 条记录（含报告 + 工具日志）"}


@router.get("/history/{report_id}/logs")
async def get_report_logs(report_id: int):
    """获取指定报告关联的工具执行日志"""
    report = get_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"报告 #{report_id} 不存在")

    logs = get_tool_logs(task=report["task"])
    return {
        "report_id": report_id,
        "task": report["task"],
        "total": len(logs),
        "logs": logs,
    }
