#!/usr/bin/env python
"""
This rosnode manages starting up and shutting down the database
"""
import rospy

if __name__ == '__main__':
    rospy.init_node("db")

    db_server = rospy.get_param("~db_server", "http://localhost:5984")
    api_server = rospy.get_param("~api_server", "http://localhost:5000")

    command = [
        "openag", "db", "init",
        "--db_url", db_server,
        "--api_url", api_server
    ]

    if subprocess.call(command):
        raise RuntimeError("Failed to initialize database")