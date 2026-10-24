"""The PM Q&A is given an activity entry's details without the rows' ids.

A task's "created" entry keeps {'title': ..., 'project_id': 178}; passed as it was, the answer spoke of "bulk task
creations for project 178", a number the user never sees.
"""
from django.test import SimpleTestCase

from api.views.pm_agent import _readable_activity_details


class ActivityDetailsTests(SimpleTestCase):

    def test_ids_are_left_out(self):
        details = {'title': 'Implement live order tracking system', 'status': 'todo', 'priority': 'high',
                   'project_id': 178, 'id': 9, 'assignee_id': None}
        self.assertEqual(_readable_activity_details(details),
                         'title: Implement live order tracking system, status: todo, priority: high')

    def test_text_and_empty_details_pass_through(self):
        self.assertEqual(_readable_activity_details('Moved to Done'), 'Moved to Done')
        self.assertIsNone(_readable_activity_details({}))
        self.assertIsNone(_readable_activity_details({'project_id': 178}))
