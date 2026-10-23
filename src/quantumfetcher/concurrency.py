from collections import deque
from collections.abc import Callable, Generator, Iterable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from itertools import islice

# An untimed wait for a thread cannot be interrupted with Ctrl+C on Windows.
_POLL_SECONDS = 0.5


def completed_in_order[T, R](
    function: Callable[[T], R], items: Iterable[T], workers: int
) -> Generator[Future[R]]:
    """Call `function` with each item on `workers` threads, yielding each call's future in the
    order of the items once it is done.

    Only twice as many items as there are workers run ahead of the one waited for, so a slow
    call does not leave the results of all the others piling up in memory. Closing the iterator
    cancels the calls that have not started.
    """
    executor = ThreadPoolExecutor(workers)
    remaining = iter(items)
    pending = deque(executor.submit(function, item) for item in islice(remaining, 2 * workers))
    try:
        while pending:
            future = pending.popleft()
            while not wait([future], _POLL_SECONDS).done:
                pass
            pending.extend(executor.submit(function, item) for item in islice(remaining, 1))
            yield future
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
