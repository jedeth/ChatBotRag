#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chatbot_rag.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you on the correct PYTHONPATH extension? "
            "Try running 'python manage.py' from the same directory you used to "
            "'django-admin startproject'."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
