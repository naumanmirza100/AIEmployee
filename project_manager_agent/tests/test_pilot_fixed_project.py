"""A Project Pilot conversation is about one project, fixed once set.

Asked for by Abdullah on 25 Oct 2026 (night): the project box could be changed in the middle of a conversation,
which mixes up which project and which tasks are meant once there are dozens of projects. Now the project picked
when a conversation starts is its project; a conversation started on "All projects" takes the first project it
settles on (a "Which project?" button, or the project it makes); after that the box gives way to the project's
name, and another project takes a new conversation. The server enforces it too.
"""
import shutil
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from api.views import pm_agent
from project_manager_agent.ai_agents.project_pilot_agent import ProjectPilotAgent
from project_manager_agent.models import PMProjectPilotChat, PMProjectPilotChatMessage, ProjectPilotJob

from .base import PMTestCase


class FixedProjectTests(PMTestCase):

    def chat_list(self):
        code, body = self.call(pm_agent.list_project_pilot_chats, self.dash, method='get')
        return {c['id']: c for c in body['data']}

    def ask(self, chat, project_id=None):
        """What the agent was given as the project, for a request in `chat` naming `project_id`."""
        with mock.patch.object(ProjectPilotAgent, 'process', return_value={'answer': 'Fine.'}) as process:
            self.call(pm_agent.project_pilot, self.dash, {'question': 'how is it going?', 'chat_id': chat.id,
                                                          'project_id': project_id})
        return (process.call_args.kwargs['context'].get('project') or {}).get('id')

    def test_the_project_picked_at_the_start_is_kept_with_the_chat(self):
        code, body = self.call(pm_agent.create_project_pilot_chat, self.dash, {
            'title': 'Website', 'project_id': self.project.id,
            'messages': [{'role': 'user', 'content': 'hi'}, {'role': 'assistant', 'content': 'Hello.'}]})
        self.assertEqual((body['data']['projectId'], body['data']['projectName']),
                         (str(self.project.id), 'Website rebuild'))
        self.assertEqual(self.chat_list()[body['data']['id']]['projectName'], 'Website rebuild')

    def test_a_request_in_the_chat_uses_its_project_whatever_it_names(self):
        chat = PMProjectPilotChat.objects.create(company_user=self.dash, project=self.project)
        self.assertEqual(self.ask(chat, project_id=self.colleague_project.id), self.project.id)
        self.assertEqual(self.ask(chat), self.project.id)

    def test_a_chat_without_one_takes_the_first_project_named_and_keeps_it(self):
        chat = PMProjectPilotChat.objects.create(company_user=self.dash)
        self.assertEqual(self.ask(chat, project_id=self.colleague_project.id), self.colleague_project.id)
        self.assertEqual(self.ask(chat, project_id=self.project.id), self.colleague_project.id)
        chat.refresh_from_db()
        self.assertEqual(chat.project, self.colleague_project)

    def test_another_companys_project_is_never_taken(self):
        code, body = self.call(pm_agent.create_project_pilot_chat, self.dash, {
            'title': 'x', 'project_id': self.rival_project.id})
        self.assertIsNone(body['data']['projectId'])
        chat = PMProjectPilotChat.objects.get(pk=body['data']['id'])
        code, body = self.call(pm_agent.project_pilot, self.dash, {'question': 'hi', 'chat_id': chat.id,
                                                                   'project_id': self.rival_project.id})
        self.assertEqual(code, 404)
        chat.refresh_from_db()
        self.assertIsNone(chat.project)

    def test_the_project_a_conversation_makes_becomes_its_project(self):
        chat = PMProjectPilotChat.objects.create(company_user=self.dash)
        card = PMProjectPilotChatMessage.objects.create(chat=chat, role='assistant', content='plan',
                                                        response_data={'needs_input': True})
        code, body = self.call(pm_agent.project_pilot_confirm, self.dash, {
            'actions': [{'action': 'create_project', 'project_name': 'Afar Word Game'}],
            'chat_id': chat.id, 'message_id': card.id})
        self.assertEqual(body['data']['chat_project']['name'], 'Afar Word Game')
        chat.refresh_from_db()
        self.assertEqual(chat.project.name, 'Afar Word Game')

    def test_a_chat_from_before_takes_the_project_its_messages_were_about(self):
        chat = PMProjectPilotChat.objects.create(company_user=self.dash, title='old')
        PMProjectPilotChatMessage.objects.create(chat=chat, role='user', content='add a task',
                                                 response_data={'project_id': str(self.project.id)})
        PMProjectPilotChatMessage.objects.create(chat=chat, role='assistant', content='Done.')
        self.assertEqual(self.chat_list()[str(chat.id)]['projectName'], 'Website rebuild')
        chat.refresh_from_db()
        self.assertEqual(chat.project, self.project)

    def test_a_file_sent_in_the_chat_is_read_for_its_project(self):
        chat = PMProjectPilotChat.objects.create(company_user=self.dash, project=self.project)
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        request = self.factory.post('/', {
            'file': SimpleUploadedFile('brief.txt', b'Add a careers page to the site.', content_type='text/plain'),
            'chat_id': str(chat.id), 'project_id': str(self.colleague_project.id), 'prompt': 'add these tasks',
        }, format='multipart')
        from rest_framework.test import force_authenticate
        force_authenticate(request, user=self.dash)
        with override_settings(MEDIA_ROOT=media), mock.patch('project_manager_agent.tasks.run_project_pilot_job.delay'):
            response = pm_agent.project_pilot_from_file(request)
        self.assertEqual(response.status_code, 202, getattr(response, 'data', None))
        self.assertEqual(ProjectPilotJob.objects.get().project_id, self.project.id)
