"""Knowledge API — 知识库文件上传与查询"""

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from vector import get_knowledge_collection

router = APIRouter(tags=["knowledge"])

# 支持的文件类型
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

# 切片大小（字符数）
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


# ── Response Models ──

class KnowledgeUploadResponse(BaseModel):
    filename: str = Field(..., description="原始文件名")
    chunks: int = Field(..., description="切片数量")
    message: str = Field(..., description="处理结果")


class KnowledgeStatsResponse(BaseModel):
    total_documents: int = Field(..., description="已索引的文档数")
    total_chunks: int = Field(..., description="总切片数")


# ── 文本提取 ──


def _extract_text_from_pdf(file_bytes: bytes) -> str:
    """从 PDF 字节流提取文本"""
    try:
        from PyPDF2 import PdfReader
        from io import BytesIO

        reader = PdfReader(BytesIO(file_bytes))
        texts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                texts.append(text)
        return "\n\n".join(texts)
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="PDF 解析需要 PyPDF2 库。请运行：pip install PyPDF2",
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF 解析失败：{str(e)}")


def _extract_text(filename: str, file_bytes: bytes) -> str:
    """根据文件类型提取文本"""
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        return _extract_text_from_pdf(file_bytes)
    elif ext in {".txt", ".md", ".markdown"}:
        return file_bytes.decode("utf-8", errors="replace")
    else:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 {ext}。支持：{', '.join(ALLOWED_EXTENSIONS)}",
        )


# ── 文本切片 ──


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """简单固定大小切片 + overlap

    按段落优先分割，超过 chunk_size 才强制截断。
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    paragraphs = text.split("\n\n")

    current = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current) + len(para) + 2 <= chunk_size:
            current = (current + "\n\n" + para).strip() if current else para
        else:
            if current:
                chunks.append(current)
            # 如果单个段落就超过 chunk_size，强制截断
            if len(para) > chunk_size:
                # 按句子分
                sentences = para.replace("\n", " ").split("。")
                sub = ""
                for sent in sentences:
                    if len(sub) + len(sent) + 1 <= chunk_size:
                        sub = (sub + "。" + sent).strip("。") if sub else sent
                    else:
                        if sub:
                            chunks.append(sub)
                        sub = sent
                if sub:
                    current = sub
                else:
                    current = ""
            else:
                current = para

    if current:
        chunks.append(current)

    return chunks


# ── API 端点 ──


@router.post("/knowledge/upload", response_model=KnowledgeUploadResponse)
async def upload_knowledge(file: UploadFile = File(...)):
    """上传文档到知识库

    支持 PDF、TXT、Markdown 文件。
    文件会被切片、向量化后存入 ChromaDB knowledge_base collection。
    """
    # 校验文件类型
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型「{ext}」。支持：{', '.join(ALLOWED_EXTENSIONS)}",
        )

    # 读取文件
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="文件为空")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大（{len(file_bytes) / 1024 / 1024:.1f} MB），限制 {MAX_FILE_SIZE / 1024 / 1024:.0f} MB",
        )

    # 提取文本
    text = _extract_text(file.filename, file_bytes)

    if not text.strip():
        raise HTTPException(status_code=400, detail="文件中未提取到文本内容")

    # 切片
    chunks = _chunk_text(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="文本切片失败")

    # 向量化 + 存入 ChromaDB
    collection = get_knowledge_collection()

    doc_id_base = uuid.uuid4().hex[:12]
    ids = [f"{doc_id_base}_chunk_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "source_file": file.filename,
            "chunk_index": str(i),
            "total_chunks": str(len(chunks)),
            "char_count": str(len(chunk)),
        }
        for i, chunk in enumerate(chunks)
    ]

    collection.upsert(
        ids=ids,
        documents=chunks,
        metadatas=metadatas,
    )

    # 使 BM25 缓存失效（文档已变更）
    from vector import _invalidate_bm25_cache
    _invalidate_bm25_cache("knowledge_base")

    return KnowledgeUploadResponse(
        filename=file.filename,
        chunks=len(chunks),
        message=f"成功索引 {len(chunks)} 个文本片段到知识库",
    )


@router.get("/knowledge/stats", response_model=KnowledgeStatsResponse)
async def knowledge_stats():
    """获取知识库统计信息"""
    collection = get_knowledge_collection()
    count = collection.count()

    # 统计唯一文档数（通过 metadata 中的 source_file）
    if count > 0:
        # 获取所有 metadata
        result = collection.get()
        sources = set()
        if result["metadatas"]:
            for meta in result["metadatas"]:
                if meta and "source_file" in meta:
                    sources.add(meta["source_file"])
        doc_count = len(sources) if sources else count
    else:
        doc_count = 0

    return KnowledgeStatsResponse(
        total_documents=doc_count,
        total_chunks=count,
    )


# ── 文件列表 + 删除 ──


class KnowledgeFile(BaseModel):
    filename: str = Field(..., description="文件名")
    chunks: int = Field(..., description="切片数量")


@router.get("/knowledge/files", response_model=list[KnowledgeFile])
async def list_knowledge_files():
    """列出知识库中所有已上传的文件（按 source_file 分组）"""
    collection = get_knowledge_collection()
    count = collection.count()

    if count == 0:
        return []

    try:
        result = collection.get()
        file_chunks: dict[str, int] = {}
        if result.get("metadatas"):
            for meta in result["metadatas"]:
                if meta and "source_file" in meta:
                    fname = meta["source_file"]
                    file_chunks[fname] = file_chunks.get(fname, 0) + 1

        return [
            KnowledgeFile(filename=name, chunks=cnt)
            for name, cnt in sorted(file_chunks.items())
        ]
    except Exception:
        return []


@router.delete("/knowledge/files/{filename:path}")
async def delete_knowledge_file(filename: str):
    """删除知识库中指定文件的所有切片"""
    collection = get_knowledge_collection()

    if collection.count() == 0:
        raise HTTPException(status_code=404, detail="知识库为空")

    try:
        # 查找该文件的所有切片 ID
        result = collection.get()
        ids_to_delete = []
        if result.get("ids") and result.get("metadatas"):
            for i, doc_id in enumerate(result["ids"]):
                meta = result["metadatas"][i]
                if meta and meta.get("source_file") == filename:
                    ids_to_delete.append(doc_id)

        if not ids_to_delete:
            raise HTTPException(status_code=404, detail=f"未找到文件「{filename}」")

        collection.delete(ids=ids_to_delete)

        # 使 BM25 缓存失效
        from vector import _invalidate_bm25_cache
        _invalidate_bm25_cache("knowledge_base")

        return {"ok": True, "message": f"已删除「{filename}」的 {len(ids_to_delete)} 个切片"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败：{str(e)}")
