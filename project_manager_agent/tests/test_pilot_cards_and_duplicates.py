"""A review card stays done once confirmed or cancelled, and the same project is not made twice by accident.

Found by Abdullah on the live site, 25 Oct 2026 evening: after a reload the Afar card showed Confirm again
although the project had been made, and uploading the same PDF again made a second project with no warning.
"""
from datetime import timedelta
from unittest import mock

from django.utils import timezone

from api.views import pm_agent
from core.models import Project, Task
from project_manager_agent import pilot_duplicates
from project_manager_agent.ai_agents.project_pilot_agent import ProjectPilotAgent
from project_manager_agent.models import PMProjectPilotChat, PMProjectPilotChatMessage
from project_manager_agent.project_pilot_pipeline import run_project_pilot_pipeline

from .base import PMTestCase

BRIEF = ('Afar is a word puzzle game for Bempoh Games: players drag letters to make words, with levels, '
         'a leaderboard, in-app purchases and a branded splash screen.')


class Proposal:
    """What the AI proposes for the brief: its wording of the name changes from run to run."""

    def __init__(self, test, name):
        self.test, self.name = test, name

    def __enter__(self):
        due = (timezone.localdate() + timedelta(days=10)).isoformat()
        self.patch = mock.patch.object(ProjectPilotAgent, 'process', return_value={'answer': '', 'actions': [
            {'action': 'create_project', 'project_name': self.name},
            {'action': 'create_task', 'task_title': 'Core puzzle mechanics', 'assignee_id': self.test.dev.id,
             'due_date': due},
        ]})
        return self.patch.__enter__()

    def __exit__(self, *exc):
        return self.patch.__exit__(*exc)


class ReviewCardOutcomeTests(PMTestCase):

    def setUp(self):
        super().setUp()
        self.chat = PMProjectPilotChat.objects.create(company_user=self.dash, title='File: Afar.pdf')
        PMProjectPilotChatMessage.objects.create(chat=self.chat, role='user', content='create this project')
        with Proposal(self, 'Afar Word Game'):
            self.draft = run_project_pilot_pipeline(company_user=self.dash, extracted_text=BRIEF, file_name='Afar.pdf',
                                                    user_prompt='create this project')['draft']
        self.card = PMProjectPilotChatMessage.objects.create(
            chat=self.chat, role='assistant', content=self.draft['answer'],
            response_data={**self.draft, 'needs_input': True})

    def confirm(self):
        return self.call(pm_agent.project_pilot_confirm, self.dash, {
            'actions': self.draft['actions'], 'chat_id': self.chat.id, 'message_id': self.card.id})

    def card_in_chat_list(self):
        code, body = self.call(pm_agent.list_project_pilot_chats, self.dash, method='get')
        [chat] = body['data']
        return next(m for m in chat['messages'] if m['id'] == self.card.id)

    def test_a_confirmed_card_stays_confirmed_after_a_reload(self):
        code, body = self.confirm()
        self.assertEqual(code, 200, body)
        self.assertEqual(body['data']['resolved']['status'], 'confirmed')
        resolved = self.card_in_chat_list()['responseData']['resolved']
        self.assertEqual((resolved['status'], resolved['answer']), ('confirmed', 'Created 1 project and 1 task.'))
        self.assertEqual(resolved['created_project_id'], Project.objects.get(name='Afar Word Game').id)

    def test_confirming_twice_makes_it_once(self):
        self.confirm()
        code, body = self.confirm()
        self.assertEqual((code, body['code']), (409, 'already_resolved'))
        self.assertEqual(Project.objects.filter(name__startswith='Afar').count(), 1)
        self.assertEqual(Task.objects.filter(title='Core puzzle mechanics').count(), 1)

    def test_a_cancelled_card_stays_cancelled(self):
        code, body = self.call(pm_agent.project_pilot_cancel_card, self.dash, chat_id=self.chat.id,
                               message_id=self.card.id)
        self.assertEqual(code, 200, body)
        self.assertEqual(self.card_in_chat_list()['responseData']['resolved']['status'], 'cancelled')
        code, body = self.confirm()
        self.assertEqual(code, 409)
        self.assertFalse(Project.objects.filter(name__startswith='Afar').exists())

    def test_someone_elses_card_is_not_theirs_to_cancel(self):
        code, body = self.call(pm_agent.project_pilot_cancel_card, self.dash_colleague, chat_id=self.chat.id,
                               message_id=self.card.id)
        self.assertEqual(code, 404)

    def test_a_card_confirmed_before_outcomes_were_kept_shows_as_done(self):
        # The live Afar card: confirmed with the old screen, so nothing was kept on the message.
        self.call(pm_agent.project_pilot_confirm, self.dash, {'actions': self.draft['actions']})
        resolved = self.card_in_chat_list()['responseData']['resolved']
        self.assertEqual((resolved['status'], resolved['answer']), ('confirmed', 'Created project “Afar Word Game”.'))
        self.card.refresh_from_db()
        self.assertEqual(self.card.response_data['resolved']['status'], 'confirmed')     # kept from now on


class SameProjectAgainTests(PMTestCase):

    def upload(self, name, prompt='create this project'):
        with Proposal(self, name):
            return run_project_pilot_pipeline(company_user=self.dash, extracted_text=BRIEF, file_name='Afar.pdf',
                                              user_prompt=prompt)

    def make(self, result):
        code, body = self.call(pm_agent.project_pilot_confirm, self.dash, {'actions': result['draft']['actions']})
        self.assertEqual(code, 200, body)

    def test_the_same_pdf_again_is_flagged_and_offered_under_a_numbered_name(self):
        self.make(self.upload('Afar Word Game'))
        first = Project.objects.get(name='Afar Word Game')
        self.assertEqual(first.source_fingerprint, pilot_duplicates.fingerprint(BRIEF))
        # The AI names it differently the second time; the document is the same.
        again = self.upload('Bempoh Word Puzzle')
        duplicate = again['draft']['duplicate']
        self.assertEqual((duplicate['existing_name'], duplicate['reason'], duplicate['new_name']),
                         ('Afar Word Game', 'same_source', 'Afar Word Game 2'))
        self.assertTrue(duplicate['message'].startswith('This project already exists: “Afar Word Game” (1 task).'))
        self.assertIn('project "Afar Word Game 2"', again['draft']['answer'])     # the card's banner says the rest
        self.assertEqual(again['draft']['rows'][0]['title'], 'Afar Word Game 2')
        self.assertEqual(Project.objects.filter(name__startswith='Afar').count(), 1)     # nothing made yet
        self.make(again)
        self.make(self.upload('Afar Game'))
        self.assertEqual(sorted(Project.objects.filter(source_fingerprint=first.source_fingerprint)
                                .values_list('name', flat=True)),
                         ['Afar Word Game', 'Afar Word Game 2', 'Afar Word Game 3'])

    def test_a_typed_request_for_a_project_by_that_name_is_flagged_too(self):
        with Proposal(self, 'Website Rebuild'):
            code, body = self.call(pm_agent.project_pilot, self.dash, {'question': 'create a website rebuild project'})
        self.assertEqual(body['status'], 'needs_input', body)
        self.assertEqual(body['data']['duplicate']['reason'], 'same_name')
        self.assertEqual(body['data']['duplicate']['new_name'], 'Website rebuild 2')

    def test_auto_confirm_still_shows_the_card_for_a_copy(self):
        self.make(self.upload('Afar Word Game'))
        self.company.pm_auto_confirm = True
        self.company.save(update_fields=['pm_auto_confirm'])
        again = self.upload('Afar Word Game')
        self.assertIn('draft', again)
        self.assertEqual(Project.objects.filter(name__startswith='Afar').count(), 1)

    def test_a_new_project_is_not_flagged(self):
        result = self.upload('Afar Word Game')
        self.assertIsNone(result['draft']['duplicate'])

    def test_numbers_and_names(self):
        self.assertEqual(pilot_duplicates.base_name('Afar Word Game 2'), 'Afar Word Game')
        self.assertEqual(pilot_duplicates.base_name('Website 2026'), 'Website 2026')
        self.assertEqual(pilot_duplicates.fingerprint('create a project'), '')
        self.assertEqual(pilot_duplicates.fingerprint('Afar  is a WORD puzzle game, for Bempoh Games: drag letters!'),
                         pilot_duplicates.fingerprint('afar is a word puzzle game for bempoh games drag letters'))
