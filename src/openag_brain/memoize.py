"""
Implements naive unbounded memoization.

@NOTE if we ever switch to Python 3.x, we should use functools.lru_cache
decorator instead which serves the same purpose (and with more nifty features).
"""
from functools import wraps

def memoize(f):
    """
    Memoize a function based on the arguments tuple passed in. Example::

        @memoize
        def foo(x, y): return x + y

    The returned MemoCache instance is a callable::

        foo(1, 2) # 3

    You can also invalidate the cache by calling method `clear`::

        foo.clear()

    MemoCache is a dict-like, so you can also inspect its memoized keys
    and values.
    """
    cache = {}
    @wraps(f)
    def memo(*args):
        if not args in cache:
            cache[args] = f(*args)
        return cache[args]
    # Expose cache on function so it can be inspected and cleared.
    memo.cache = cache
    return memo
