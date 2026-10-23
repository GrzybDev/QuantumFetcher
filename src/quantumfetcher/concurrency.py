from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager


@contextmanager
def results_in_order[T, R](
    function: Callable[[T], R], items: Iterable[T], workers: int
) -> Iterator[Iterator[R]]:
    """Call `function` with each item on worker threads, giving the results in item order.

    Only about twice as many calls as there are workers run ahead of the result waited for, so a
    slow call does not leave the results of all the others piling up in memory. The first call
    that raises ends the results with its error. Leaving the context cancels the calls that have
    not started and, unless Ctrl+C was pressed, waits for the ones under way, so that none goes on
    in the background.

    Args:
        function: The call to make with each item.
        items: The items to call it with.
        workers: The number of threads making the calls.
    """
    executor = ThreadPoolExecutor(workers)
    wait = True
    try:
        yield executor.map(function, items, buffersize=2 * workers)
    except KeyboardInterrupt:
        # Waiting would delay closing the HttpClient, which stops the requests under way.
        wait = False
        raise
    finally:
        executor.shutdown(wait, cancel_futures=True)
