#!/usr/bin/python
"""
The `recipe_handler.py` module is in charge of running recipes. It provides a
service `/<environment_id>/start_recipe` which takes as input a recipe ID and
starts the recipe. It also provides a service `/<environment_id>/stop_recipe`
which takes no inputs and stops the currently running recipe. It defines a
parameter `current_recipe` which stores the ID of the currently running recipe.
It also defines a parameter `current_recipe_start` which stores the UNIX
timestamp at which the currently running recipe was started. If no recipe is
running, `current_recipe` will be set to an empty string and
`current_recipe_start` will be set to 0. There should always be exactly one
instance of this module per environment in the system.
"""

import time
import rospy
from rospy import sleep
from multiprocessing import Process, Queue, Event
from Queue import Empty

from couchdb import Server

from openag.db_names import ENVIRONMENTAL_DATA_POINT, RECIPE
from openag.var_types import RECIPE_START, RECIPE_END
from openag.models import EnvironmentalDataPoint

from openag_brain.keyframe_proxy_store import (
    KeyframeProxyStore, key_by_env_var, should_update_value
)
from openag_brain import params, services
from openag_brain.srv import StartRecipe, Empty
from openag_brain.gen_doc_id import gen_doc_id
from openag_brain.memoize import Memoize

# Create a memoized publisher function that will return a cached publisher
# instance for the same topic, type and queue_size.
@Memoize
def publisher_memo(topic, type, queue_size):
    return rospy.Publisher(topic, Float64, queue_size=10)

class RecipeRunningError(Exception):
    pass

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
        """
        Recipes must implement an __init__ method that consumes a
        recipe argument (the recipe record) and a start argument (the start
        time as unix epoch seconds).
        """
        raise NotImplementedError("Recipes must take recipe and start args")

    def __iter__(self):
        """
        Recipe subclasses must implement an iter method, which will yield
        setpoints at the walltime they should be processed by the system.
        __iter__ should block until it has a setpoint to yield.
        """
        raise NotImplementedError("Recipes must implement __iter__")

    def sleep(self, s):
        """
        Recipe subclasses should use the sleep method to block until
        they are ready to yield a setpoint from __iter__.
        """
        return sleep(s)

class SimpleRecipe(Recipe):
    """
    Interpret "simple" recipe format.
    """
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

# A map of recipe format keys to classnames
RECIPE_INTERPRETERS = {
    "simple": SimpleRecipe
}

def accumulate_state(state, operations):
    """
    Accumulate a series of operations into a state table, mutating that
    table.
    """
    state.update({variable: value for _, variable, value in operations})
    return state

def drain_queue(queue):
    """Given a queue object, drain it of all items. Returns generator."""
    while True:
        try:
            yield queue.get_nowait()
        except Empty:
            break

def fill_queue(queue, iterable):
    """
    Given a queue and an iterable, put items in iterable into queue until
    iterable is exhausted. If no slot is available in queue, will block
    until slot is available.
    Mutates queue.
    """
    for x in iterable:
        queue.put(x)
    return queue

def wrap_recipe(recipe, flag, timeout=1):
    """
    Given a blocking recipe iterator this generator will create a new
    generator that will take care of a lot of the boilerplate of managing
    recipes:

    - Generate a start datapoint at the beginning
    - Interpolate between setpoints by "spamming" the previous setpoints
      every x seconds (defined by timeout).
    - Allow recipes to be cancelled via a flag.
    - Generate an end datapoint

    Datapoints are returned as tuples of (time, variable, value).

    The blocking recipe iterator will be run in a separate process. run_recipe
    polls that process for new data ever 5s. If it doesn't find any, it
    yields the current setpoint instead.
    """
    if flag.is_set():
        raise RecipeRunningError()
    state = {}
    queue = Queue()
    proc = Process(target=fill_queue, args=(queue, recipe))
    proc.start()
    flag.set()
    yield (recipe.start, RECIPE_START.name, recipe.id)
    while True:
        state = accumulate_state(state, drain_queue(queue))
        for variable, value in state.items():
            yield (time.time(), variable, value)
        if not proc.is_alive() or not flag.is_set():
            break
        sleep(timeout)
    yield (time.time(), RECIPE_END.name, recipe.id)
    flag.clear()

class RecipeHandler:
    def __init__(self, server, environment):

        # Create keyframe store for environmental variables
        store = KeyframeProxyStore(
            env_var_db, should_update_value, key=key_by_env_var
        )
        self.store = store
        self.environment = environment
        self.recipe_flag = Event()

    def run_recipe(self, recipe):
        for timestamp, variable, value in wrap_recipe(recipe, self.recipe_flag):
            pub = publisher_memo("desired/{}".format(topic), Float64, 10)
            pub(value)
            # @TODO ideally, this should be handled in a separate
            # desired_persistence ros node.
            record = EnvironmentalDataPoint({
                "environment": self.environment,
                "variable": variable,
                "is_desired": True,
                "value": value,
                "timestamp": timestamp
            })
            doc_id = gen_doc_id(time.time())
            self.store.put(doc_id, record)

    def is_recipe_running(self):
        return self.recipe_flag.is_set()

    def cancel_recipe(self):
        """
        Cancel any currently running recipe.
        It is safe to cancel even if there is no recipe running.
        """
        self.recipe_flag.clear()
        return self

    def start_recipe_service(self, data, start_time=None):
        recipe_id = data.recipe_id
        if not recipe_id:
            return False, "No recipe id was specified"
        if self.recipe_flag.is_set():
            return False, "There is already a recipe running. Please stop it "\
                "before attempting to start a new one"
        try:
            recipe = self.recipe_db[recipe_id]
        except Exception as e:
            return False, "\"{}\" does not reference a valid "\
            "recipe".format(recipe_id)
        start_time = start_time or time.time()
        recipe_format = recipe.get("format", "simple")
        RecipeInterpreter = RECIPE_INTERPRETERS[recipe_format]
        recipe = RecipeInterpreter(recipe, start_time)
        rospy.set_param(params.CURRENT_RECIPE, recipe_id)
        rospy.set_param(params.CURRENT_RECIPE_START, start_time)
        proc = Process(target=self.run_recipe, recipe)
        proc.start()
        rospy.loginfo('Starting recipe "{}"'.format(recipe_id))
        return True, "Success"

    def stop_recipe_service(self, data):
        """Stop recipe ROS service"""
        if self.is_recipe_running():
            self.cancel_recipe()
            while self.is_recipe_running():
                rospy.sleep(1)
            return True, "Success"
        else:
            return False, "There is no recipe running"

    def register_services(self):
        """Register services for instance"""
        rospy.Service(services.START_RECIPE, StartRecipe, self.start_recipe_service)
        rospy.Service(services.STOP_RECIPE, Empty, self.stop_recipe_service)
        rospy.set_param(
            params.SUPPORTED_RECIPE_FORMATS,
            ','.join(self.recipe_class_map.keys())
        )
        return self

    def resume(self):
        """Attempt to resume any previous state"""
                # Get the recipe that has been started most recently
        start_view = self.env_data_db.view("openag/by_variable", startkey=[
            self.environment, "desired", RECIPE_START.name
        ], endkey=[
            self.environment, "desired", RECIPE_START.name, {}
        ], group_level=3)
        if len(start_view) == 0:
            return
        start_doc = start_view.rows[0].value

        # If a recipe has been ended more recently than the most recent time a
        # recipe was started, don't run the recipe
        end_view = self.env_data_db.view("openag/by_variable", startkey=[
            self.environment, "desired", RECIPE_END.name,
        ], endkey=[
            self.environment, "desired", RECIPE_END.name, {}
        ], group_level=3)
        if len(end_view):
            end_doc = end_view.rows[0].value
            if (end_doc["timestamp"] > start_doc["timestamp"]):
                return

if __name__ == '__main__':
    namespace = rospy.get_namespace()
    environment = self.namespace.split('/')[-2]
    db_server = cli_config["local_server"]["url"]
    if not db_server:
        raise RuntimeError("No local database specified")
    server = Server(db_server)
    handler = RecipeHandler(server, environment)
    handler.register_services()
    handler.resume()

    rospy.spin()