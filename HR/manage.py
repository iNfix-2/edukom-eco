#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'edukom_hr.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and available on your PYTHONPATH environment variable? If you are in a virtual environment, did you forget to activate it?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()

