import requests
from importlib import import_module

__all__ = ['resolve_message_type']

def resolve_message_type(msg_type):
    """
    Resolves a string containing a ROS message type (e.g. "std_msgs/Float32")
    to the Python class for that message type
    """
    if not msg_type in resolve_message_type.cache:
        pkg, cls = msg_type.split('/')
        mod = import_module('.msg', pkg)
        resolve_message_type.cache[msg_type] = getattr(mod, cls)
    return resolve_message_type.cache[msg_type]
resolve_message_type.cache = {}

def handle_process(proc, err):
    """
    Takes a running subprocess.Popen object `proc`, rosdebugs everything it
    prints to stdout, roswarns everything it prints to stderr, and raises
    `err` if it fails
    """
    poll = select.poll()
    poll.register(proc.stdout)
    poll.register(proc.stderr)
    while proc.poll() is None and not rospy.is_shutdown():
        res = poll.poll(1)
        for fd, evt in res:
            if not (evt & select.POLLIN):
                continue
            if fd == proc.stdout.fileno():
                line = proc.stdout.readline().strip()
                if line:
                    rospy.logdebug(line)
            elif fd == proc.stderr.fileno():
                line = proc.stderr.readline().strip()
                if line:
                    rospy.logwarn(line)
    if proc.poll():
        proc.terminate()
        proc.wait()
        raise RuntimeError("Process interrupted by ROS shutdown")
    if proc.returncode:
        raise err