"""A support ticket becomes a project task, and hears when it's done.

A bug report or feature request reaching Frontline had to be retyped into the
Project Manager agent, and the ticket never learned when the work was done.
"""
from django.contrib.auth import get_user_model
from django.utils import timezone

from api.views import frontline_agent as views
from core.models import Project, Task, UserProfile
from Frontline_agent.models import TicketNote
from project_manager_agent.models import PMNotification

from .base import FrontlineTestCase


class TicketToTaskTests(FrontlineTestCase):

    def setUp(self):
        super().setUp()
        self.buy_module(self.company, 'project_manager_agent')
        self.dev = get_user_model().objects.create_user(username='dev', email='dev@test.local', password='x',
                                                        first_name='Dev', last_name='Eloper')
        UserProfile.objects.update_or_create(user=self.dev, defaults={'company': self.company, 'role': 'team_member'})
        self.project = Project.objects.create(name='App', company=self.company,
                                              created_by_company_user=self.admin, owner=self.dev)
        self.rival_project = Project.objects.create(name='Theirs', company=self.rival,
                                                    created_by_company_user=self.rival_admin, owner=self.rival_user)
        self.ticket.priority = 'urgent'
        self.ticket.assigned_to = self.admin_user
        self.ticket.save()

    def form(self):
        return self.call(views.ticket_pm_task, self.member, method='get', ticket_id=self.ticket.id)

    def create(self, **overrides):
        data = dict(self.form()[1]['data']['prefill'], project_id=self.project.id, assignee_id=self.dev.id)
        data.update(overrides)
        return self.call(views.ticket_pm_task, self.member, data, ticket_id=self.ticket.id)

    # ---- the form -------------------------------------------------------------

    def test_the_form_is_filled_in_from_the_ticket(self):
        code, body = self.form()
        self.assertEqual(code, 200)
        data = body['data']
        self.assertTrue(data['pm_available'])
        self.assertEqual(data['prefill']['title'], 'Printer on fire')
        self.assertIn(f'From Frontline ticket #{self.ticket.id}', data['prefill']['description'])
        self.assertEqual(data['prefill']['priority'], 'high')                 # urgent → PM's top
        self.assertGreater(data['prefill']['due_date'], timezone.localdate().isoformat())
        self.assertEqual([p['name'] for p in data['projects']], ['App'])        # not the rival's

    # ---- creating it ------------------------------------------------------------

    def test_confirming_creates_the_task_and_links_both_ways(self):
        code, body = self.create()
        self.assertEqual(code, 201, body)
        task = Task.objects.get(pk=body['data']['id'])
        self.assertEqual((task.project, task.assignee, task.priority), (self.project, self.dev, 'high'))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.pm_task, task)
        self.assertEqual(list(task.frontline_tickets.all()), [self.ticket])
        self.assertTrue(TicketNote.objects.filter(ticket=self.ticket, body__startswith='Project task created').exists())

    def test_the_ticket_list_shows_its_task(self):
        self.create()
        code, body = self.call(views.list_tickets, self.admin, method='get')     # lists the caller's tickets
        row = next(r for r in body['data'] if r['id'] == self.ticket.id)
        self.assertEqual(row['pm_task']['title'], 'Printer on fire')

    def test_only_once(self):
        self.create()
        code, body = self.create(title='Again')
        self.assertEqual((code, body['code']), (409, 'already_linked'))

    def test_pm_still_decides_what_is_valid(self):
        code, _ = self.create(project_id=self.rival_project.id)
        self.assertIn(code, (400, 404))
        code, _ = self.create(assignee_id=self.rival_user.id)
        self.assertEqual(code, 400)
        self.ticket.refresh_from_db()
        self.assertIsNone(self.ticket.pm_task)

    def test_not_without_the_project_manager_agent(self):
        from core.models import CompanyModulePurchase
        CompanyModulePurchase.objects.filter(company=self.company, module_name='project_manager_agent').delete()
        self.assertFalse(self.form()[1]['data']['pm_available'])
        code, body = self.create()
        self.assertEqual((code, body['code']), (403, 'no_pm'))

    # ---- when the task is done ----------------------------------------------

    def finish(self, task, status='done'):
        task.status = status
        task.save()

    def test_finishing_the_task_notes_the_ticket_and_tells_its_owner_once(self):
        task = Task.objects.get(pk=self.create()[1]['data']['id'])
        self.finish(task)
        self.finish(task)                                     # saved again: no second note
        notes = TicketNote.objects.filter(ticket=self.ticket, body__contains='is done')
        self.assertEqual(notes.count(), 1)
        [alert] = PMNotification.objects.filter(company_user=self.admin, title__startswith='Done: the task')
        self.assertEqual(alert.data['link'], '/frontline/dashboard?tab=tickets')

    def test_reopened_and_finished_again_is_noted_again(self):
        task = Task.objects.get(pk=self.create()[1]['data']['id'])
        self.finish(task)
        self.finish(task, 'in_progress')
        self.finish(task)
        self.assertEqual(TicketNote.objects.filter(ticket=self.ticket, body__contains='is done').count(), 2)
