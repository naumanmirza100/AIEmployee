"""Tests for the Project Manager agent's project/task APIs.

    python manage.py test project_manager_agent --settings=project_manager_ai.settings_test

The settings module matters: it runs the tests on a local SQLite database, so
they never touch the Hostinger database or spend its 500-connections-an-hour
budget. See docs/TESTING.md.
"""
