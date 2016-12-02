#!/usr/bin/env python
"""
This node can be used to start up the CouchDB database from a roslaunch file.
"""
import rospy
import subprocess

if __name__ == '__main__':
    rospy.init_node("db")

    db_server = rospy.get_param("~db_server", "http://localhost:5984")
    api_server = rospy.get_param("~api_server", "http://localhost:5000")

    # Constuct command. We init the database by calling out to CouchDB
    # through the openag db command.
    command = [
        "openag", "db", "init",
        "--db_url", db_server,
        "--api_url", api_server
    ]

    if subprocess.call(command):
        raise RuntimeError("Failed to initialize database")
