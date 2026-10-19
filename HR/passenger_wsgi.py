import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(__file__))

from edukom_hr import wsgi

application = wsgi.application
