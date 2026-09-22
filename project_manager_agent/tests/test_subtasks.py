"""Subtask CRUD (GAP-1).

Before this existed, subtasks could only be created by the AI, and their
`status` and `order` fields were unreachable.
"""
from django.utils import timezone

from api.views import pm_subtasks
from core.models import Subtask, Task

from .base import PMTestCase


class SubtaskTests(PMTestCase):

    def setUp(self):
        super().setUp()
        self.parent = self.task(title='Parent')

    def create(self, data=None, task=None, actor=None):
        return self.call(pm_subtasks.create_subtask, actor or self.dash, data or {'title': 'Step'},
                         task_id=(task or self.parent).id)

    def test_created_subtasks_are_appended_in_order(self):
        first = self.create({'title': 'First'})[1]['data']
        second = self.create({'title': 'Second'})[1]['data']
        self.assertEqual(second['order'], first['order'] + 1)

    def test_a_blank_title_is_refused(self):
        code, _ = self.create({'title': '  '})
        self.assertEqual(code, 400)

    def test_listing_reports_progress(self):
        self.create({'title': 'First'})
        done = Subtask.objects.create(task=self.parent, title='Second', status='done')
        code, body = self.call(pm_subtasks.list_subtasks, self.dash, method='get',
                               task_id=self.parent.id)
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data']['total'], 2)
        self.assertEqual(body['data']['done'], 1)
        self.assertIn(done.id, [s['id'] for s in body['data']['subtasks']])

    def test_marking_done_stamps_the_completion_time(self):
        subtask = Subtask.objects.create(task=self.parent, title='Step')
        code, body = self.call(pm_subtasks.update_subtask, self.dash, {'status': 'done'},
                               method='patch', subtask_id=subtask.id)
        self.assertEqual(code, 200, body)
        subtask.refresh_from_db()
        self.assertIsNotNone(subtask.completed_at)

    def test_reopening_clears_the_completion_time(self):
        subtask = Subtask.objects.create(task=self.parent, title='Step', status='done',
                                         completed_at=timezone.now())
        code, body = self.call(pm_subtasks.update_subtask, self.dash, {'status': 'todo'},
                               method='patch', subtask_id=subtask.id)
        self.assertEqual(code, 200, body)
        subtask.refresh_from_db()
        self.assertIsNone(subtask.completed_at)

    def test_an_invalid_status_is_refused(self):
        subtask = Subtask.objects.create(task=self.parent, title='Step')
        code, _ = self.call(pm_subtasks.update_subtask, self.dash, {'status': 'nope'},
                            method='patch', subtask_id=subtask.id)
        self.assertEqual(code, 400)

    def test_reordering_needs_the_complete_list(self):
        one = Subtask.objects.create(task=self.parent, title='One', order=0)
        Subtask.objects.create(task=self.parent, title='Two', order=1)
        code, body = self.call(pm_subtasks.reorder_subtasks, self.dash, {'order': [one.id]},
                               task_id=self.parent.id)
        self.assertEqual(code, 400, body)
        self.assertIn('every subtask', body['message'])

    def test_reordering_moves_them(self):
        one = Subtask.objects.create(task=self.parent, title='One', order=0)
        two = Subtask.objects.create(task=self.parent, title='Two', order=1)
        code, body = self.call(pm_subtasks.reorder_subtasks, self.dash, {'order': [two.id, one.id]},
                               task_id=self.parent.id)
        self.assertEqual(code, 200, body)
        one.refresh_from_db()
        two.refresh_from_db()
        self.assertLess(two.order, one.order)

    def test_deleting_one(self):
        subtask = Subtask.objects.create(task=self.parent, title='Step')
        code, body = self.call(pm_subtasks.delete_subtask, self.dash, method='delete',
                               subtask_id=subtask.id)
        self.assertEqual(code, 200, body)
        self.assertFalse(Subtask.objects.filter(pk=subtask.pk).exists())

    def test_another_companys_task_is_not_found(self):
        foreign = Task.objects.create(project=self.rival_project, title='Theirs')
        code, _ = self.create({'title': 'Step'}, task=foreign)
        self.assertEqual(code, 404)
        self.assertFalse(Subtask.objects.filter(task=foreign).exists())

    def test_another_companys_subtask_cannot_be_edited(self):
        foreign_task = Task.objects.create(project=self.rival_project, title='Theirs')
        foreign = Subtask.objects.create(task=foreign_task, title='Theirs')
        code, _ = self.call(pm_subtasks.update_subtask, self.dash, {'title': 'Mine now'},
                            method='patch', subtask_id=foreign.id)
        self.assertEqual(code, 404)
