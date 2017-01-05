"""
Implements naive unbounded memoization.

@NOTE if we ever switch to Python 3.x, we should use functools.lru_cache
decorator instead which serves the same purpose (and with more nifty features).
"""

class MemoCache(dict):
    def __init__(self, f):
        self.raw = f

    def __call__(self, *args):
        if not args in self:
            self[args] = self.raw(*args)
        return self[args]

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
    return MemoCache(f)