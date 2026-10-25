"""Project Pilot asks with buttons and takes "no, because…" for an answer.

Asked for by Abdullah on 25 Oct 2026 (night): a reply asking to confirm was a paragraph of text; it should be
short and organised, with Confirm and "reject with reason" buttons. And "i have selected it", answering Pilot's
"which project?", got a paragraph back instead of the change.
"""
import json
from datetime import timedelta
from unittest import mock

from django.utils import timezone

from api.views import pm_agent
from core.models import Project
from project_manager_agent import pilot_deadlines
from project_manager_agent.ai_agents.project_pilot_agent import TEXT_REPLY_FORMAT, ProjectPilotAgent
from project_manager_agent.models import PMProjectPilotChat, PMProjectPilotChatMessage

from .base import PMTestCase

MOVE = 'change the deadline of the whole project to next 20 days, and the tasks accordingly'


class RejectAndReviseTests(PMTestCase):

    def setUp(self):
        super().setUp()
        self.project.start_date = timezone.localdate()
        self.project.save(update_fields=['start_date'])
        self.task(title='Design', due_date=timezone.now() + timedelta(days=20))
        self.task(title='Launch', due_date=timezone.now() + timedelta(days=60))
        self.chat = PMProjectPilotChat.objects.create(company_user=self.dash, title='Website')

    def card_for(self, question, **extra):
        code, body = self.call(pm_agent.project_pilot, self.dash, {'question': question, **extra})
        self.assertEqual(body['status'], 'needs_input', body)
        PMProjectPilotChatMessage.objects.create(chat=self.chat, role='user', content=question)
        return PMProjectPilotChatMessage.objects.create(
            chat=self.chat, role='assistant', content=body['data']['answer'],
            response_data={**body['data'], 'needs_input': True})

    def reject(self, card, reason):
        return self.call(pm_agent.project_pilot_cancel_card, self.dash, {'reason': reason},
                         chat_id=self.chat.id, message_id=card.id)

    def revise(self, card, reason):
        self.reject(card, reason)
        return self.call(pm_agent.project_pilot, self.dash, {'question': reason, 'revise_of': card.id})

    def test_a_card_rejected_with_a_reason_keeps_it(self):
        card = self.card_for(MOVE, project_id=self.project.id)
        code, body = self.reject(card, 'Too tight, the client wants 15 days')
        self.assertEqual(body['data']['resolved']['status'], 'rejected')
        card.refresh_from_db()
        self.assertEqual(card.response_data['resolved']['reason'], 'Too tight, the client wants 15 days')

    def test_a_deadline_in_the_reason_revises_the_move_without_the_ai(self):
        card = self.card_for(MOVE, project_id=self.project.id)
        with mock.patch.object(ProjectPilotAgent, '_call_llm', side_effect=AssertionError('the AI was asked')):
            code, body = self.revise(card, 'make it 15 days instead')
        self.assertEqual(body['status'], 'needs_input', body)
        deadline = (timezone.localdate() + timedelta(days=15)).isoformat()
        self.assertEqual(body['data']['actions'][0]['updates'], {'deadline': deadline})
        self.assertTrue(all(a['updates']['due_date'] <= deadline for a in body['data']['actions'][1:]))
        self.assertTrue(body['data']['answer'].startswith('Revised: **Website rebuild** now finishes on'))

    def test_a_new_project_revised_to_a_later_deadline_spreads_its_tasks(self):
        today = timezone.localdate()
        actions = [{'action': 'create_project', 'project_name': 'Shop', 'start_date': today.isoformat(),
                    'deadline': (today + timedelta(days=10)).isoformat(), 'source_fingerprint': 'f' * 64},
                   {'action': 'create_task', 'task_title': 'Cart', 'due_date': (today + timedelta(days=5)).isoformat()},
                   {'action': 'create_task', 'task_title': 'Go live', 'due_date': (today + timedelta(days=10)).isoformat()}]
        with mock.patch.object(ProjectPilotAgent, 'process', return_value={'answer': '', 'actions': actions}):
            card = self.card_for('create a shop project')
        code, body = self.revise(card, 'give it 30 days')
        new_deadline = (today + timedelta(days=30)).isoformat()
        project_row = next(r for r in body['data']['rows'] if r['action'] == 'create_project')
        self.assertEqual(project_row['deadline'], new_deadline)
        last = next(r for r in body['data']['rows'] if r['title'] == 'Go live')
        self.assertGreater(last['due_date'], (today + timedelta(days=20)).isoformat())     # spread, not left early

    def test_any_other_change_goes_to_the_ai_with_the_proposal(self):
        actions = [{'action': 'create_project', 'project_name': 'Shop 2', 'source_fingerprint': 'a' * 64},
                   {'action': 'create_task', 'task_title': 'Cart', 'assignee_id': self.dev.id}]
        with mock.patch.object(ProjectPilotAgent, 'process', return_value={'answer': '', 'actions': actions}):
            card = self.card_for('create a shop project')
        revised = [{'action': 'create_project', 'project_name': 'Shop'},          # the model dropped the copy number
                   {'action': 'create_task', 'task_title': 'Cart', 'assignee_id': self.pm.id}]
        with mock.patch.object(ProjectPilotAgent, '_call_llm', return_value=json.dumps(revised)) as llm:
            code, body = self.revise(card, 'give the cart to Pat')
        self.assertIn('give the cart to Pat', llm.call_args.args[0])
        self.assertIn('"task_title": "Cart"', llm.call_args.args[0])                 # the proposal it made
        self.assertEqual(body['data']['actions'][1]['assignee_id'], self.pm.id)
        self.assertEqual(body['data']['actions'][0]['project_name'], 'Shop 2')       # kept
        self.assertEqual(body['data']['actions'][0]['source_fingerprint'], 'a' * 64)


class WhichProjectTests(PMTestCase):

    def test_the_question_offers_the_projects_and_the_request_to_send_again(self):
        code, body = self.call(pm_agent.project_pilot, self.dash, {'question': MOVE})
        data = body['data']
        self.assertEqual(data['answer'], pilot_deadlines.WHICH_PROJECT)
        self.assertIn({'id': self.project.id, 'name': 'Website rebuild'}, data['choices'])
        self.assertEqual(data['retry'], MOVE)

    def test_a_typed_answer_to_it_is_joined_to_the_request(self):
        # "i have selected it", with the project now chosen in the box.
        history = [{'role': 'user', 'content': MOVE},
                   {'role': 'assistant', 'content': pilot_deadlines.WHICH_PROJECT}]
        with mock.patch.object(ProjectPilotAgent, 'process', side_effect=AssertionError('the AI was asked')):
            code, body = self.call(pm_agent.project_pilot, self.dash, {
                'question': 'i have selected it', 'project_id': self.project.id, 'chat_history': history})
        self.assertEqual(body['status'], 'needs_input', body)
        self.assertEqual(body['data']['actions'][0]['project_id'], self.project.id)


class TextReplyFormatTests(PMTestCase):

    def test_a_reply_in_words_is_asked_to_be_short_and_in_bullets(self):
        agent = ProjectPilotAgent()
        with mock.patch.object(agent, '_call_llm', return_value='Use Knowledge Q&A for that.') as llm:
            agent.process(question='what is the status of my projects?', context={'all_projects': []})
        self.assertTrue(llm.call_args.args[0].endswith(TEXT_REPLY_FORMAT))
        self.assertIn('at most 4 bullet points', TEXT_REPLY_FORMAT)
