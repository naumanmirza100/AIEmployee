"""Tests for the Frontline agent.

    python manage.py test Frontline_agent --settings=project_manager_ai.settings_test

The settings module matters: it runs the tests on a local SQLite database, so
they never touch the Hostinger database or spend its 500-connections-an-hour
budget. See docs/TESTING.md.

These cover the findings in MDS/FRONTLINE_AGENT_AUDIT.md — each test names the
FL-SEC / FL-DATA / FL-PERF item it guards, so a failure says what regressed.
"""
