class Memoize:
    """
    Memoize a function based on the arguments passed in. Example::

        @Memoize
        def foo(x, y): return x + y
    """
    def __init__(self, f):
        self.__function = f
        self.__cache = {}

    def __call__(self, *args):
        if not args in self.__cache:
            self.__cache[args] = self.__function(*args)
        return self.__cache[args]

    def invalidate(self, *args):
        """Invalidate the memoized value for a set of arguments."""
        del self.__cache[args]
        return self