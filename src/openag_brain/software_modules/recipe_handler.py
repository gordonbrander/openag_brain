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
from openag.db_names import ENVIRONMENTAL_DATA_POINT, RECIPE
from openag.cli.config import config as cli_config
from openag.models import EnvironmentalDataPoint
from openag.var_types import RECIPE_START, RECIPE_END
from couchdb import Server
from std_msgs.msg import Float64
from threading import RLock
from openag_brain import params, services
from openag_brain.srv import StartRecipe, Empty
from openag_brain.utils import gen_doc_id
from openag_brain.memoize import memoize
from openag_brain.multidispatch import multidispatch

class EventAlreadySetError(Exception):
    pass

def set_if_clear(event):
    """
    This function is used to ensure set on an event is only called if
    the current state of the event is unset
    """
    if event.is_set():
        raise EventAlreadySetError()
    event.set()
    return event

@memoize
def publisher_memo(topic, MsgType, queue_size=10):
    """
    A memoized publisher function which will return a cached publisher
    instance for the same topic, type and queue_size.
    """
    return rospy.Publisher(topic, MsgType, queue_size=queue_size)

@multidispatch(lambda x: x.get("type", "simple"))
def interpret_recipe(recipe):
    """We don't support default behavior for recipe interpretation"""
    raise ValueError("Recipe type not supported")

# Register simple recipe handler
@interpret_recipe.register("simple")
class SimpleRecipe:
    def __init__(self, recipe, start_time=None, timeout=1):
        self.start_time = start_time or time.time()
        self.id = recipe["id"]
        self.operations = recipe["operations"]
        self.timeout = timeout

    def __iter__(self):
        """
        Create a blocking recipe generator for simple recipes.
        Yields a series of setpoints for current time.

        This function serves as a good example of how to create recipe interpreters.
        A recipe interpreter is a function which:

        - Takes a recipe description object of whatever format it supports
        - A start_time
        - A timeout

        ...and is able to generate setpoint tuples via Python's generator interface.
        Setpoint tuples are of format `(timestamp, variable, value)`.

        Recipe interpreters are responsible for generating a recipe_start
        setpoint at the beginning and a recipe_end setpoint at the end.
        """
        # Create a state object to accrue recipe setpoint values.
        start_time = self.start_time
        recipe_id = self.id
        operations = self.operations
        timeout = self.timeout
        state = {}
        # Start by yielding a RECIPE_START setpoint
        yield (start_time, RECIPE_START.name, recipe_id)
        for t, variable, value in operations:
            # While we wait for time to catch up to timestamp, yield the
            # previous state once every second.
            while t > time.time() - start_time:
                for variable, value in state.iteritems():
                    yield (time.time(), variable, value)
                    rospy.sleep(timeout)
            # Ok, setpoint has reached the present. Assign it to state.
            # Then loop until we hit a future state, at which point, we
            # start yielding the present state again.
            state[variable] = value
        # We're done! Yield a RECIPE_END setpoint
        yield (time.time(), RECIPE_END.name, recipe_id)

class RecipeRunningError(Exception):
    """Thrown when trying to set a recipe, but recipe is already running."""
    pass

class RecipeIdleError(Exception):
    """Thrown when trying to clear a recipe, but recipe is already clear."""
    pass

class RecipeHandler:
    def __init__(self, server, environment):
        # We create a lock to ensure threadsafety, since service handlers are
        # run in a separate thread by ROS.
        self.lock = RLock()
        self.env_data_db = server[ENVIRONMENTAL_DATA_POINT]
        self.recipe_db = server[RECIPE]
        self.environment = environment
        self.__recipe = None

    def get_recipe():
        with self.lock:
            return self.__recipe

    def set_recipe(id, recipe, start_time=None):
        with self.lock:
            if self.__recipe is not None:
                raise RecipeRunningError("Recipe is already running")
            self.__recipe = recipe
        return self

    def clear_recipe(recipe):
        with self.lock:
            if self.__recipe is None:
                raise RecipeIdleError("No recipe is running")
            self.__recipe = None
        return self

    def loop(self):
        while not rospy.is_shutdown():
            recipe = self.get_recipe()
            if recipe:
                rospy.set_param(params.CURRENT_RECIPE, recipe.id)
                rospy.set_param(params.CURRENT_RECIPE_START, recipe.start_time)
                rospy.loginfo('Starting recipe "{}"'.format(recipe.id))
                state = {}
                for timestamp, variable, value in recipe:
                    # If recipe was canceled, break setpoint iteration
                    if not self.get_recipe():
                        break

                    topic_name = "desired/{}".format(variable)
                    pub = publisher_memo(topic_name, Float64, queue_size=10)
                    pub.publish(value)

                    # Advance state
                    prev = state.get(variable, None)
                    state[variable] = value
                    # Store unique datapoints
                    if prev != value:
                        # @TODO ideally, this should be handled in a separate
                        # desired_persistence ros node and we should only publish to
                        # topic endpoint.
                        doc = EnvironmentalDataPoint({
                            "environment": self.environment,
                            "variable": variable,
                            "is_desired": True,
                            "value": value,
                            "timestamp": timestamp
                        })
                        doc_id = gen_doc_id(time.time())
                        self.env_data_db[doc_id] = doc
                rospy.set_param(params.CURRENT_RECIPE, "")
                rospy.set_param(params.CURRENT_RECIPE_START, 0)
            rospy.sleep(1)

    def start_recipe_service(self, data, start_time=None):
        recipe_id = data.recipe_id
        if not recipe_id:
            return False, "No recipe id was specified"
        try:
            recipe = self.recipe_db[recipe_id]
        except Exception as e:
            return False, "\"{}\" does not reference a valid "\
            "recipe".format(recipe_id)
        try:
            recipe_interpreter = interpret_recipe(recipe)
        except ValueError:
            return False, "Unsupported recipe type"
        try:
            self.set_recipe(recipe_interpreter)
        except RecipeRunningError:
            return (
                False,
                "There is already a recipe running. Please stop it "
                "before attempting to start a new one"
            )
        return True, "Success"

    def stop_recipe_service(self, data):
        """Stop recipe ROS service"""
        try:
            self.clear_recipe()
        except RecipeIdleError:
            return False, "There is no recipe running"
        return True, "Success"

    def register_services(self):
        """Register services for instance"""
        rospy.Service(services.START_RECIPE, StartRecipe, self.start_recipe_service)
        rospy.Service(services.STOP_RECIPE, Empty, self.stop_recipe_service)
        rospy.set_param(
            params.SUPPORTED_RECIPE_FORMATS,
            ','.join(interpret_recipe.methods.keys())
        )
        return self

    def resume(self):
        """
        Attempt to resume any previous recipe that was started but
        not completed.
        """
        # Get the recipe that has been started most recently
        start_view = self.env_data_db.view(
            "openag/by_variable",
            startkey=[self.environment, "desired", RECIPE_START.name],
            endkey=[self.environment, "desired", RECIPE_START.name, {}],
            group_level=3
        )
        if len(start_view) == 0:
            return
        start_doc = start_view.rows[0].value
        # If a recipe has been ended more recently than the most recent time a
        # recipe was started, don't run the recipe
        end_view = self.env_data_db.view(
            "openag/by_variable",
            startkey=[self.environment, "desired", RECIPE_END.name],
            endkey=[self.environment, "desired", RECIPE_END.name, {}],
            group_level=3
        )
        if len(end_view):
            end_doc = end_view.rows[0].value
            if (end_doc["timestamp"] > start_doc["timestamp"]):
                return
        # Run the recipe
        self.start_recipe_service(
            StartRecipe._request_class(start_doc["value"]),
            start_doc["timestamp"]
        )

if __name__ == '__main__':
    rospy.init_node('recipe_handler')
    namespace = rospy.get_namespace()
    environment = namespace.split('/')[-2]
    db_server = cli_config["local_server"]["url"]
    if not db_server:
        raise RuntimeError("No local database specified")
    server = Server(db_server)
    handler = RecipeHandler(server, environment)
    # Register ROS service handlers
    handler.register_services()
    # Resume any previous recipes
    handler.resume()
    # Start the recipe loop
    handler.loop()
