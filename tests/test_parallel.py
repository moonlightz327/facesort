"""Ordering, error isolation and cancellation for the analyze-stage thread pool."""

import threading
import time

import pytest

from facesort.core.parallel import default_workers, imap_ordered, resolve_workers


def test_default_workers_scales_with_cpu_but_stays_small():
    assert default_workers(1) == 1
    assert default_workers(4) == 2
    assert default_workers(12) == 4
    # Never oversubscribe: measured slower at 8 workers on a 12-core machine.
    assert default_workers(64) == 4


def test_resolve_workers_zero_is_auto_and_negative_clamps():
    assert resolve_workers(0) == default_workers()
    assert resolve_workers(3) == 3
    assert resolve_workers(-5) == 1


@pytest.mark.parametrize("workers", [1, 2, 4])
def test_results_keep_input_order_regardless_of_completion_order(workers):
    """Clustering depends on face order, so out-of-order results would change
    which cluster is 人物1."""

    def slow_for_early_items(i):
        time.sleep(0.02 if i < 3 else 0.0)
        return i * 10

    out = [(item, res) for item, res, exc in
           imap_ordered(slow_for_early_items, range(10), workers=workers)]
    assert [item for item, _ in out] == list(range(10))
    assert [res for _, res in out] == [i * 10 for i in range(10)]


@pytest.mark.parametrize("workers", [1, 3])
def test_exception_is_reported_per_item_not_raised(workers):
    def boom(i):
        if i == 2:
            raise ValueError("bad photo")
        return i

    results = list(imap_ordered(boom, range(5), workers=workers))
    assert [r[0] for r in results] == [0, 1, 2, 3, 4]
    assert isinstance(results[2][2], ValueError)
    assert results[2][1] is None
    # The rest still come through.
    assert [r[1] for r in results if r[2] is None] == [0, 1, 3, 4]


@pytest.mark.parametrize("workers", [1, 4])
def test_cancel_stops_early(workers):
    cancel = threading.Event()
    seen = []

    def work(i):
        return i

    for item, _res, _exc in imap_ordered(work, range(100), workers=workers,
                                         cancel=cancel):
        seen.append(item)
        if len(seen) == 5:
            cancel.set()

    assert len(seen) < 100
    assert seen[:5] == [0, 1, 2, 3, 4]


def test_single_worker_runs_inline_without_threads():
    main = threading.current_thread().name
    names = [n for _i, n, _e in
             imap_ordered(lambda _: threading.current_thread().name,
                          range(3), workers=1)]
    assert names == [main, main, main]
