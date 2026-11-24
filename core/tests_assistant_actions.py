"""The Company Assistant proposes actions, and does them once confirmed (24 Nov 2026).

It only read, and said where to go. Asked to do something, it now comes back with a card; nothing changes until the
asker confirms it, and then through the agent's own code, with the asker's rights. No test reaches an AI: a stand-in
plans the action.
"""
import json
from datetime import date, timedelta

from api.views import company_assistant as views
from core.assistant import actions, engine
from core.models import Task
from Frontline_agent.models import Ticket
from hr_agent.models import Employee, LeaveRequest

from .tests_company_assistant import AssistantTestCase, FakeAI


class ProposingAI(FakeAI):
    """Plans one action."""

    def __init__(self, kind, args):
        super().__init__()
        self.kind, self.args = kind, args

    def _call_llm(self, prompt, system_prompt=None, temperature=0.7, max_tokens=1024, json_mode=False):
        self.prompts.append(prompt)
        return json.dumps({'calls': [], 'action': {'kind': self.kind, 'args': self.args}, 'ask_back': None,
                           'needs': [], 'english': '', 'language': 'english'})


class Proposals(AssistantTestCase):

    def propose(self, who, kind, args):
        return self.ask(who, ProposingAI(kind, args))

    def act(self, who, token):
        return self.call(views.assistant_act, who, {'token': token})

    def test_a_task_is_proposed_then_made_only_on_confirm(self):
        due = (date.today() + timedelta(days=7)).isoformat()
        result = self.propose(self.admin, 'create_task',
                              {'title': 'Fix the login page', 'project': 'website', 'assignee': 'Ali', 'due_date': due})
        card = result['proposal']
        self.assertEqual(card['title'], 'Create a task')
        self.assertIn(['For', 'Ali Staff'], card['rows'])
        self.assertIn('press Confirm', result['answer'])
        self.assertFalse(Task.objects.filter(title='Fix the login page').exists())        # nothing yet
        code, body = self.act(self.admin, card['token'])
        self.assertEqual(code, 200, body)
        task = Task.objects.get(title='Fix the login page')
        self.assertEqual((task.project_id, task.assignee_id), (self.project.id, self.ali.user_id))
        code, body = self.act(self.admin, card['token'])                                  # a second Confirm
        self.assertEqual((code, body['message']), (400, 'This was done already.'))
        self.assertEqual(Task.objects.filter(title='Fix the login page').count(), 1)

    def test_a_name_that_fits_nobody_or_two_is_asked_back(self):
        result = self.propose(self.admin, 'create_task', {'title': 'X', 'project': 'website', 'assignee': 'Zed'})
        self.assertTrue(result['asked_back'])
        self.assertIn('could not find anyone called "Zed"', result['answer'])
        self.assertNotIn('proposal', result)

    def test_a_task_is_changed(self):
        task = Task.objects.create(project=self.project, title='Write the release notes', status='todo')
        card = self.propose(self.admin, 'update_task', {'task': 'release notes', 'status': 'done'})['proposal']
        self.assertIn(['Status', 'Done'], card['rows'])
        self.assertEqual(self.act(self.admin, card['token'])[0], 200)
        task.refresh_from_db()
        self.assertEqual(task.status, 'done')

    def test_leave_is_decided_by_who_may_decide_it(self):
        Employee.objects.filter(pk=self.member_emp.pk).update(manager=self.admin_emp)
        lr = self.leave_request(self.member_emp, approver=self.admin_emp)
        result = self.propose(self.member, 'decide_leave', {'person': 'me', 'decision': 'approve'})
        self.assertIn("only their approver or HR can", result['answer'])          # not their own
        card = self.propose(self.admin, 'decide_leave', {'person': 'Mo', 'decision': 'approve'})['proposal']
        self.assertEqual(card['title'], 'Approve leave')
        code, body = self.act(self.admin, card['token'])
        self.assertEqual(code, 200, body)
        lr.refresh_from_db()
        self.assertEqual(lr.status, 'approved')

    def test_a_proposal_is_the_askers_own_and_expires(self):
        card = self.propose(self.admin, 'create_task', {'title': 'Plan Q1', 'project': 'website'})['proposal']
        self.assertEqual(self.act(self.member, card['token'])[1]['message'], 'This suggestion was made for someone else.')
        self.assertIn('could not be read', self.act(self.admin, card['token'] + 'x')[1]['message'])

    def test_an_agent_the_company_lacks_is_not_offered(self):
        result = self.propose(self.admin, 'update_ticket', {'ticket': '1', 'status': 'closed'})
        self.assertTrue(result['asked_back'])
        self.assertIn("can't do that here", result['answer'])

    def test_the_plan_is_told_the_actions_and_the_answer_what_it_cannot_do(self):
        ai = FakeAI()
        self.ask(self.admin, ai, 'Who is away?')
        self.assertIn('create_task', ai.prompts[0])
        self.assertIn('say in one sentence that you\ncan\'t do that one', ai.prompts[-1].replace('\n  ', '\n'))


class Tickets(AssistantTestCase):

    def test_a_ticket_is_changed_through_frontlines_own_rules(self):
        self.buy_module(self.company, 'frontline_agent')
        from django.contrib.auth.models import User
        ticket = Ticket.objects.create(title='Printer on fire', description='Help', company=self.company,
                                       created_by=User.objects.create_user('cust', password='x'), status='open')
        result = engine.ask(self.admin, 'Mark ticket {} resolved'.format(ticket.id), [],
                            ai=ProposingAI('update_ticket', {'ticket': str(ticket.id), 'status': 'resolved'}))
        card = result['proposal']
        self.assertIn([f'Ticket', f'#{ticket.id} Printer on fire'], card['rows'])
        code, body = self.call(views.assistant_act, self.admin, {'token': card['token']})
        self.assertEqual(code, 200, body)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, 'resolved')
        bad = engine.ask(self.admin, 'x', [], ai=ProposingAI('update_ticket', {'ticket': str(ticket.id), 'status': 'new'}))
        code, body = self.call(views.assistant_act, self.admin, {'token': bad['proposal']['token']})
        self.assertEqual(code, 400)                     # Frontline's own state rules refuse it
