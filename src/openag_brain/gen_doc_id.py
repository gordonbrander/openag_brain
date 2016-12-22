from sys import maxsize
from random import randint

def gen_doc_id(curr_time):
    """
    Given a unix time, generate a unique ID string with extremely low chance
    of collision.

    Returns a string.
    """
    return "{}-{}".format(curr_time, randint(0, maxsize))