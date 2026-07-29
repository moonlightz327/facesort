"""Bounded, order-preserving parallel map used by the analyze stage.

Photo analysis is the pipeline's bottleneck and splits into two GIL-releasing
halves: JPEG/RAW decode (PIL/rawpy) and onnx inference. Running a few photos at
once wins on both, but the pool must stay small — measured on a 12-core M2,
4 workers ran ~1.4x faster end-to-end while 8 workers were *slower* than 4 from
oversubscribing onnxruntime's own intra-op threads.

Two properties the pipeline depends on:
  * results come back in input order, so clustering stays deterministic;
  * at most `workers + 1` decoded images are alive at once (a 24MP frame is
    ~72MB as BGR), so memory does not scale with the size of the shoot.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Iterable, Iterator, Optional, TypeVar

T = TypeVar("T")
R = TypeVar("R")


def default_workers(cpu: Optional[int] = None) -> int:
    """Small pool sized to leave room for onnxruntime's internal threads."""
    n = cpu if cpu is not None else (os.cpu_count() or 2)
    return max(1, min(4, (n + 2) // 3))


def resolve_workers(requested: int = 0) -> int:
    """`0` (or anything falsy) means auto; negative is clamped to 1."""
    if not requested:
        return default_workers()
    return max(1, int(requested))


def imap_ordered(
    fn: Callable[[T], R],
    items: Iterable[T],
    workers: int = 0,
    cancel: Optional[threading.Event] = None,
) -> Iterator[tuple[T, Optional[R], Optional[BaseException]]]:
    """Yield `(item, result, exception)` in the order of `items`.

    Exceptions from `fn` are handed back per item instead of raised, so one
    corrupt photo cannot abort a whole run. Setting `cancel` stops submitting
    new work and ends the iteration once in-flight items drain.

    With `workers == 1` this runs inline — no threads, identical semantics.
    """
    workers = resolve_workers(workers)
    items = iter(items)

    if workers == 1:
        for item in items:
            if cancel is not None and cancel.is_set():
                return
            try:
                yield item, fn(item), None
            except BaseException as e:  # noqa: BLE001 - reported, not swallowed
                yield item, None, e
        return

    # Keep one extra task queued so a worker never idles between photos.
    max_inflight = workers + 1
    pending: list[tuple[T, Future]] = []

    def submit_next(pool: ThreadPoolExecutor) -> bool:
        try:
            item = next(items)
        except StopIteration:
            return False
        pending.append((item, pool.submit(fn, item)))
        return True

    with ThreadPoolExecutor(max_workers=workers,
                            thread_name_prefix="facesort") as pool:
        try:
            while len(pending) < max_inflight and submit_next(pool):
                pass
            while pending:
                item, fut = pending.pop(0)
                try:
                    yield item, fut.result(), None
                except BaseException as e:  # noqa: BLE001
                    yield item, None, e
                if cancel is not None and cancel.is_set():
                    break
                submit_next(pool)
        finally:
            # Drop queued work immediately on cancel/early exit; already-running
            # tasks still finish, which the `with` block waits for.
            for _, fut in pending:
                fut.cancel()


def map_values(fn: Callable[[T], R], items: list[T], workers: int = 0) -> list[Any]:
    """Simple ordered parallel map that propagates the first exception."""
    out: list[Any] = []
    for _item, result, exc in imap_ordered(fn, items, workers=workers):
        if exc is not None:
            raise exc
        out.append(result)
    return out
