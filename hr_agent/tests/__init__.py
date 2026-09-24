"""Tests for the HR agent.

    python manage.py test hr_agent --settings=project_manager_ai.settings_test

The settings module matters: it runs the tests on a local SQLite database, so
they never touch the Hostinger database or spend its 500-connections-an-hour
budget. See docs/TESTING.md.

Each test names the finding it guards (MDS/HR_AGENT_AUDIT.md), so a failure
says what regressed. Several pin behaviour that was *already correct* — the
leave engine's locking and balance arithmetic — because the fixes around them
touched that code.
"""
