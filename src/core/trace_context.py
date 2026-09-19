"""
Trace context — correlation ID xuyên pipeline.

Mục đích:
  - Mỗi lần chạy pipeline sinh 1 `trace_id` (8-char hex) unique.
  - Log tự động prefix `[tid:xxxxxxxx]` để dễ grep.
  - Metrics + patch_history entries include `trace_id`.
  - Propagate qua thread pool bằng `submit_with_context()`.

Design note — Contextvar & ThreadPoolExecutor:
  - `ContextVar` là per-thread → worker thread KHÔNG tự thấy context
    của main thread.
  - `copy_context()` phải chạy trong MAIN thread, SAU khi trace_context
    entered, TRƯỚC khi submit.
  - Decorator pattern KHÔNG hoạt động (decoration ở module load time).
  → Dùng helper `submit_with_context(executor, fn, *args)`.

Usage:
    from core.trace_context import trace_context, submit_with_context

    with trace_context() as tid:
        log(f"[tid:{tid}] starting...")
        with ThreadPoolExecutor() as ex:
            submit_with_context(ex, worker, arg1, arg2)

Env:
  LP_TRACE_ID=<hex>     → override trace_id (CI, debug)
  LP_TRACE_DISABLE=1    → tắt hoàn toàn (trace_id = "-")
"""
from __future__ import annotations

import contextvars
import logging
import os
import uuid
from concurrent.futures import Executor, Future
from contextlib import contextmanager
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ============================================================
# CONTEXTVAR
# ============================================================
_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "lp_trace_id", default="-"
)

_DISABLE = os.environ.get(
    "LP_TRACE_DISABLE", ""
).strip().lower() in ("1", "true", "yes", "on")


# ============================================================
# PUBLIC API
# ============================================================
def new_trace_id() -> str:
    """Sinh trace_id 8-char hex (32-bit unique đủ cho debug)."""
    if _DISABLE:
        return "-"
    env_override = os.environ.get("LP_TRACE_ID", "").strip()
    if env_override:
        return env_override
    return uuid.uuid4().hex[:8]


def get_trace_id() -> str:
    """Return current trace_id hoặc "-" nếu chưa set."""
    return _trace_id_var.get()


def set_trace_id(trace_id: str) -> contextvars.Token:
    """Set trace_id cho context hiện tại. Return Token để reset."""
    return _trace_id_var.set(trace_id)


def reset_trace_id(token: contextvars.Token) -> None:
    """Reset về giá trị trước đó."""
    try:
        _trace_id_var.reset(token)
    except (ValueError, LookupError):
        pass


@contextmanager
def trace_context(trace_id: str | None = None):
    """
    Context manager set trace_id tạm thời.

    Yields:
        trace_id string (auto-gen nếu None).
    """
    tid = trace_id or new_trace_id()
    token = set_trace_id(tid)
    try:
        yield tid
    finally:
        reset_trace_id(token)


def prefix_with_trace(message: str) -> str:
    """Prefix message với `[tid:xxxxxxxx]` nếu trace_id != "-"."""
    tid = get_trace_id()
    if tid and tid != "-":
        return f"[tid:{tid}] {message}"
    return message


# ============================================================
# THREAD POOL PROPAGATION — CORRECT PATTERN
# ============================================================
def submit_with_context(
    executor: Executor,
    fn: Callable,
    *args: Any,
    **kwargs: Any,
) -> Future:
    """
    Submit task vào executor, propagate contextvars từ caller.

    Pattern chuẩn: capture context trong MAIN thread (nơi gọi submit),
    pass cho `ctx.run()` để worker thread chạy trong context đã copy.

    Args:
        executor: ThreadPoolExecutor / ProcessPoolExecutor instance
        fn: Function cần chạy
        *args: Positional args cho fn
        **kwargs: Keyword args cho fn

    Returns:
        concurrent.futures.Future

    Notes:
        ProcessPoolExecutor: contextvars không pickle được → sẽ
        downgrade thành "-" trong worker process. Chỉ dùng cho
        ThreadPoolExecutor.
    """
    ctx = contextvars.copy_context()
    return executor.submit(ctx.run, fn, *args, **kwargs)


class ContextThreadPoolExecutor:
    """
    Wrapper class — drop-in cho ThreadPoolExecutor với context propagation.

    Usage:
        from core.trace_context import ContextThreadPoolExecutor

        with ContextThreadPoolExecutor(max_workers=4) as ex:
            ex.submit(worker, 1)  # context tự động propagate
    """

    def __init__(self, *args, **kwargs):
        from concurrent.futures import ThreadPoolExecutor
        self._executor = ThreadPoolExecutor(*args, **kwargs)

    def submit(self, fn: Callable, *args: Any, **kwargs: Any) -> Future:
        return submit_with_context(self._executor, fn, *args, **kwargs)

    def __enter__(self):
        self._executor.__enter__()
        return self

    def __exit__(self, *exc_info):
        return self._executor.__exit__(*exc_info)

    def shutdown(self, *args, **kwargs):
        return self._executor.shutdown(*args, **kwargs)


# ============================================================
# LOGGING HELPER — stdlib prefix
# ============================================================
class TraceFilter(logging.Filter):
    """
    Stdlib logging.Filter thêm `trace_id` vào record.

    Usage:
        handler = logging.StreamHandler()
        handler.addFilter(TraceFilter())
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(trace_id)s] %(message)s"
        ))
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = get_trace_id()
        return True


def bind_trace_to_loguru(
    loguru_logger: Any,
    base_format: str = "{time:HH:mm:ss} | {level:<8} | {message}",
) -> None:
    """
    Bind loguru logger với trace_id filter.

    Sau khi gọi, mọi `logger.info(...)` tự thêm `[tid:xxxxxxxx]`.

    Fix: `dict.update()` returns None → phải return `record` rõ ràng,
    nếu không loguru sẽ nhận None và crash.

    Args:
        loguru_logger: loguru.logger instance
        base_format: loguru format string

    Usage:
        from loguru import logger as lg
        from core.trace_context import bind_trace_to_loguru
        bind_trace_to_loguru(lg)
    """
    try:
        loguru_logger.configure(extra={"trace_id": "-"})

        def _patch_record(record: dict) -> dict:
            """Inject trace_id vào record.extra rồi return record."""
            record["extra"]["trace_id"] = get_trace_id()
            return record

        loguru_logger = loguru_logger.patch(_patch_record)

        def _sink(msg: Any) -> None:
            tid = msg.record["extra"].get("trace_id", "-")
            print(f"[tid:{tid}] {msg}")

        loguru_logger.add(
            _sink,
            format=base_format,
            level="INFO",
        )
    except Exception as e:
        logger.debug("bind_trace_to_loguru failed: %s", e)