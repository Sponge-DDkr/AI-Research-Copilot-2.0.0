# Python 异步编程最佳实践（2026 版）

> 作者：李后端 | 更新日期：2026-07-01 | 适用版本：Python 3.12+

---

## 1. async/await 基础陷阱

### 1.1 不要在 async 函数里调用 time.sleep()

```python
# ❌ 错误：阻塞整个事件循环
async def bad_polling():
    while True:
        result = check_status()
        time.sleep(5)  # 所有协程卡住 5 秒！
        print(result)

# ✅ 正确：让出控制权
async def good_polling():
    while True:
        result = check_status()
        await asyncio.sleep(5)  # 其他协程可以运行
        print(result)
```

这是一个高频 bug。`time.sleep()` 是同步阻塞的，在 async 函数里调用会让整个事件循环停摆。2026 年上半年我所在的团队在 Code Review 中发现了 **23 次**这个错误。

### 1.2 不要在 async 里用同步 HTTP 库

```python
# ❌ 阻塞事件循环
import requests
async def fetch_data():
    resp = requests.get("https://api.example.com/data")  # 同步阻塞
    return resp.json()

# ✅ 使用 httpx.AsyncClient
import httpx
async def fetch_data():
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://api.example.com/data")
        return resp.json()
```

### 1.3 CPU 密集型任务必须放进线程池

```python
# ❌ 在事件循环里做 CPU 密集计算
async def process_image():
    result = heavy_image_processing(data)  # 阻塞 3 秒
    return result

# ✅ 用 run_in_executor 放到线程池
async def process_image():
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, heavy_image_processing, data)
    return result
```

---

## 2. asyncio.Queue 的正确用法

### 2.1 SSE 流式推送的标准模式

这是 AI 应用开发中最常见的场景——Agent 在后台运行，SSE 事件通过队列流向前端：

```python
import asyncio
import json

async def sse_event_generator(queue: asyncio.Queue, agent_task):
    """SSE 事件生成器——从队列消费事件，产出 SSE 格式"""
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=0.1)
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except asyncio.TimeoutError:
            # 检查 Agent 是否完成
            if agent_task.done():
                break

    # Agent 完成后的收尾
    if agent_task.exception():
        yield f"data: {json.dumps({'type': 'error', 'message': str(agent_task.exception())})}\n\n"
    yield "data: [DONE]\n\n"
```

### 2.2 Queue 必须设 maxsize

```python
# ❌ 无限制队列——内存泄漏风险
queue = asyncio.Queue()

# ✅ 设 maxsize，背压保护
queue = asyncio.Queue(maxsize=100)
```

如果 Agent 产出速度 > SSE 消费速度（比如用户网络慢），无限制队列会把内存撑爆。设 `maxsize=100` 后，队列满时 `put()` 会阻塞，形成天然的背压。

---

## 3. ensure_future vs create_task

很多人分不清这两个的区别，实际差异很小但很关键：

| | `asyncio.ensure_future` | `asyncio.create_task` |
|---|---|---|
| 引入版本 | Python 3.4.4 | Python 3.7 |
| 参数类型 | Future/Task/coroutine 都接受 | 只接受 coroutine |
| 推荐场景 | 不确定传入类型时（框架代码） | 确定是 coroutine 时（应用代码） |
| 性能 | 略慢（有类型检查开销） | 略快 |

**结论**：应用代码一律用 `create_task`。只有写框架/库代码且不确认传入类型时用 `ensure_future`。

---

## 4. FastAPI 中的异步陷阱

### 4.1 不要在 Depends 里做同步 IO

```python
# ❌ Depends 里同步读数据库 → 阻塞
def get_db():
    conn = sqlite3.connect("app.db")  # 同步阻塞
    return conn

@app.get("/users")
async def get_users(db = Depends(get_db)):
    ...

# ✅ SQLAlchemy 2.0 异步 Session
from sqlalchemy.ext.asyncio import AsyncSession

async def get_db():
    async with async_session() as session:
        yield session
```

*注意：这是为什么本项目的数据库层虽然当前用 SQLite（不支持 async 驱动），但架构上不直接用 `sqlite3` 模块而是通过 SQLAlchemy 2.0 ORM——为了将来换 PostgreSQL 时启用 `asyncpg` 驱动时改动量最小。*

### 4.2 Lifespan 优于 on_event

```python
# ❌ 已废弃
@app.on_event("startup")
async def startup():
    init_chromadb()

# ✅ FastAPI 推荐
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_chromadb()
    yield
    cleanup()
```

---

## 5. ChromaDB 的异步使用

ChromaDB 的 Python 客户端是同步的，在 async FastAPI 里直接调用会阻塞事件循环。推荐做法：

```python
import asyncio
import chromadb
from concurrent.futures import ThreadPoolExecutor

# 线程池包装 ChromaDB 操作
_chroma_executor = ThreadPoolExecutor(max_workers=4)

async def query_chroma(query: str, top_k: int = 5):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _chroma_executor,
        lambda: collection.query(query_texts=[query], n_results=top_k)
    )
```

`max_workers=4` 的设定理由：ChromaDB 查询主要是 CPU 轻量的 I/O（读磁盘 + 向量计算），4 个线程足以应对 50 并发的 FastAPI 实例。

---

## 6. 常见错误速查表

| 错误代码 | 症状 | 根因 | 出现频率（2026H1 统计） |
|---------|------|------|------------------------|
| `RuntimeError: This event loop is already running` | 在 Jupyter 里跑 asyncio | Jupyter 自带 event loop | ⭐⭐⭐⭐⭐ #1 |
| `Task was destroyed but it is pending!` | 程序退出时报错 | 忘记 await 某个任务 | ⭐⭐⭐⭐ #2 |
| `Timeout context manager should be used inside a task` | asyncio.timeout 报错 | 在非 task 上下文用 timeout | ⭐⭐⭐ #3 |
| `got Future attached to a different loop` | 跨线程传递 Future | 在多线程环境混用 event loop | ⭐⭐⭐ #3 |
| ChromaDB 查询超时 | 请求堆积 | 同步调用阻塞事件循环 | ⭐⭐ #5 |

---

## 7. 关键版本变更（Python 3.12 → 3.13）

Python 3.13 在异步方面有三个重要变更：

1. **`asyncio.timeout` 成为正式 API**（3.11 是实验性的），推荐替代 `asyncio.wait_for`
2. **新增 `TaskGroup` 增强**：子任务异常时自动取消其他任务，不需要手动 try/except
3. **`loop.run_in_executor` 性能提升 30%**（GIL 优化相关）

*特别提醒：本项目当前运行在 Python 3.13.7，但 `sentence-transformers` 对 3.13 的支持仍不完整，建议 ChromaDB 的 embedding 模型使用 ONNX 格式而非 PyTorch 格式，避免兼容性问题。*
