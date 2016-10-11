import rospy
import subprocess
from openag_brain.util import handle_process

rospy.init_node("flash_arduino", anonymous=True)

def flash_arduino(build_dir):
	# Create temporary dir for building Arduino code
    rospy.loginfo("Initializing firmware project for Arduino")
    proc = subprocess.Popen(
        ["openag", "firmware", "init"],
        cwd=build_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    # Watch process until it completes
    handle_process(proc, RuntimeError(
        "Failed to iniailize OpenAg firmware project"
    ))
    rospy.loginfo("Flashing Arduino")
    try:
        proc = subprocess.Popen(
            [
                "openag", "firmware", "run", "-p", "ros", "-t",
                "upload"
            ],
            cwd=build_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        handle_process(proc, Exception())
    except Exception:
        rospy.logerr("Failed to update Arduino")
