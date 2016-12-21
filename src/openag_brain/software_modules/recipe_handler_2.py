import time
from multiprocessing import Process, Queue
from Queue import Empty
from openag.var_types import RECIPE_START, RECIPE_END
from openag.models import EnvironmentalDataPoint

class Recipe:
    """
    The rule for recipe readers is that they must impelement recipe
    operations as a blocking __iter__ method::

        (TIME, ENV_VAR, VALUE)

    Where

    - `TIME` is recipe relative (0 meaning start).
    - `ENV_VAR` is a valid environmental variable
    - `VALUE` is the value for the variable.
    """
    def __init__(self, recipe, start):
        raise NotImplementedError("Recipes take recipe and start args")

    def __iter__(self):
        raise NotImplementedError("Recipes must implement __iter__")

    def sleep(self, s):
        return time.sleep(s)

class SimpleRecipe(Recipe):
    def __init__(self, recipe, start):
        self.start = start
        self.id = recipe["_id"]
        self.__operations = recipe["operations"]

    def __iter__(self):
        for rel_timestamp, variable, value in self.__operations:
            now = time.time()
            timestamp = rel_timestamp + self.start
            # Block until future timestamp is "now"
            if timestamp > now:
                self.sleep(timestamp - now)
            yield (timestamp, variable, value)

RECIPE_INTERPRETERS = {
    "simple": SimpleRecipe
}

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

@Memoize
def mem_publisher(topic, type, queue_size):
    rospy.Publisher(topic, Float64, queue_size=10)

def pub_all(state):
    for topic, value in state.items():
        pub = mem_publisher("desired/"+topic, Float64, 10)
        pub.publish(value)

def accumulate_state(state, operations):
    """
    Accumulate a series of operations into a state table, mutating that
    table.
    """
    state.update({variable: value for _, variable, value in operations})
    return state

def process_recipe(queue, recipe):
    for operation in recipe:
        queue.put(operation)

def drain_queue(queue):
    """Given a queue object, drain it of all items. Returns generator."""
    while True:
        try:
            yield queue.get_nowait()
        except Empty:
            break

def run_recipe(recipe, poll_timeout=5):
    """
    Given a blocking recipe iterator, run_recipe will generate:

    - A start datapoint at the beginning
    - Interpolate between setpoints by "spamming" the previous setpoints
      every x seconds (defined by poll_timeout).
    - An end datapoint

    Datapoints are returned as tuples of (time, variable, value).

    The blocking recipe iterator will be run in a separate process. run_recipe
    polls that process for new data ever 5s. If it doesn't find any, it
    yields the current setpoint instead.
    """
    state = {}
    queue = Queue()
    proc = Process(target=process_recipe, args=(queue, recipe))
    proc.start()
    yield (recipe.start, RECIPE_START.name, recipe.id)
    while True:
        state = accumulate_state(state, drain_queue(queue))
        for variable, value in state.items():
            yield (time.time(), variable, value)
        if not proc.is_alive():
            break
        time.sleep(poll_timeout)
    yield (time.time(), RECIPE_END.name, recipe.id)

if __name__ == '__main__':
    import json
    recipe_script = json.loads("""
    {
       "_id": "recipe1",
       "_rev": "4-4b1c1f6c41c02014e43e75d58de0fca5",
       "operations": [
           [
               0,
               "air_temperature",
               26
           ],
           [
               0,
               "air_humidity",
               50
           ],
           [
               20,
               "air_temperature",
               27
           ],
           [
               30,
               "air_temperature",
               30
           ]
       ],
       "format": "simple"
    }
    """)
    recipe = SimpleRecipe(recipe_script, time.time())
    for d in run_recipe(recipe):
        print(d)
