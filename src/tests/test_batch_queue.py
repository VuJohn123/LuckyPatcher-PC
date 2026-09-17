"""Test patcher/batch_queue.py — BatchQueue."""
import threading
import time

import pytest

from patcher.batch_queue import BatchQueue


# ============================================================
# Construction
# ============================================================
def test_init_requires_callback():
    with pytest.raises(TypeError):
        BatchQueue()  # type: ignore


def test_init_with_callback():
    q = BatchQueue(pipeline_callback=lambda *_: None)
    assert q.cb is not None
    assert q.queue.empty()


def test_init_with_log_callback():
    logs = []
    q = BatchQueue(
        pipeline_callback=lambda *_: None,
        log_callback=logs.append,
    )
    # Bound method không so sánh được bằng `is` — test bằng behavior
    q.log("hello")
    assert logs == ["hello"]


# ============================================================
# add
# ============================================================
def test_add_single():
    logs = []
    q = BatchQueue(lambda *_: None, logs.append)
    q.add("test.apk")
    assert q.queue.qsize() == 1
    assert any("Queued" in l for l in logs)


def test_add_with_mode():
    q = BatchQueue(lambda *_: None)
    q.add("test.apk", mode="license")
    item = q.queue.get_nowait()
    assert item == ("test.apk", "license")


def test_add_default_mode_all():
    q = BatchQueue(lambda *_: None)
    q.add("test.apk")
    apk, mode = q.queue.get_nowait()
    assert mode == "all"


def test_add_multiple():
    q = BatchQueue(lambda *_: None)
    q.add("a.apk")
    q.add("b.apk")
    q.add("c.apk")
    assert q.queue.qsize() == 3


# ============================================================
# start + run
# ============================================================
def test_start_processes_queue():
    processed = []
    q = BatchQueue(lambda apk, mode: processed.append(apk))

    q.add("a.apk")
    q.add("b.apk")
    q.start()

    # Đợi queue xử lý xong (tối đa 3s)
    deadline = time.monotonic() + 3
    while q.queue.qsize() > 0 and time.monotonic() < deadline:
        time.sleep(0.05)

    assert "a.apk" in processed
    assert "b.apk" in processed
    q.stop()


def test_start_idempotent():
    q = BatchQueue(lambda *_: None)
    q.add("a.apk")
    q.start()
    q.start()  # Lần 2 no-op
    q.stop()


def test_callback_error_isolated():
    """Callback lỗi → queue tiếp tục xử lý item khác."""
    processed = []

    def cb(apk, mode):
        if apk == "bad.apk":
            raise RuntimeError("boom")
        processed.append(apk)

    q = BatchQueue(cb)
    q.add("good1.apk")
    q.add("bad.apk")
    q.add("good2.apk")
    q.start()

    deadline = time.monotonic() + 3
    while q.queue.qsize() > 0 and time.monotonic() < deadline:
        time.sleep(0.05)

    assert "good1.apk" in processed
    assert "good2.apk" in processed
    q.stop()


def test_progress_callback_invoked():
    progress_calls = []
    q = BatchQueue(lambda *_: None)
    q.progress_cb = lambda done, total, apk: progress_calls.append((done, total))

    q.add("a.apk")
    q.start()

    deadline = time.monotonic() + 3
    while not progress_calls and time.monotonic() < deadline:
        time.sleep(0.05)

    assert len(progress_calls) >= 1
    q.stop()


def test_progress_callback_error_isolated():
    """Progress callback lỗi → không crash."""
    q = BatchQueue(lambda *_: None)
    q.progress_cb = lambda *_: (_ for _ in ()).throw(RuntimeError("boom"))

    q.add("a.apk")
    q.start()
    time.sleep(0.3)
    q.stop()


# ============================================================
# stop
# ============================================================
def test_stop_before_start():
    """Stop khi chưa start → không crash."""
    q = BatchQueue(lambda *_: None)
    q.stop()


def test_stop_idempotent():
    q = BatchQueue(lambda *_: None)
    q.add("a.apk")
    q.start()
    q.stop()
    q.stop()  # Không crash