"""
Clojure-esque multimethods.

@NOTE if we ever upgrade to Python 3, we should consider using
functools.singledispatch instead. It should do the trick.
"""
class MultiDispatch(dict):
    def __init__(self, f, key):
        self.key = key
        self.default = f

    def __call__(self, *args, **kwargs):
        method = self.get(self.key(*args), self.default)
        return method(*args, **kwargs)

    def register(self, k):
        def decorate(f):
            self[k] = f
            return f
        return decorate

def multidispatch(key):
    """
    Clojure-style fancy multimethods as a Python decorator.
    Clojure-style Multimethods are able to dispatch on any combination of
    arguments by producing a key via a key function. If no key is found for
    the argument combo, a default function is called.

    Note that key function has to consume all positional arguments, but
    ignores keyword arguments.

    Usage:

        @multimethod(lambda x: type(x).__name__)
        def add(x): return 'default'

        @add.register('float')
        def add_float(x): return 'float'

        add(1.0) # 'float'

    All registered methods are stored on MultiDispatch, which is a dict-like
    object, so you can inspect them.
    """
    def decorate_default(f):
        return MultiDispatch(f, key)
    return decorate_default