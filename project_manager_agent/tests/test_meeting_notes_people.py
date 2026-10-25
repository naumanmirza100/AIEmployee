"""Meeting notes that name the client or someone not yet on a task are analysed; notes naming no one on the project
are refused as likely meant for another project.

Seen while rehearsing the PM demo (25 Oct 2026): kickoff notes naming the PM (no tasks yet) and the client were
refused outright, although everyone else in them was on the project.
"""
import json
from unittest import mock

from django.test import SimpleTestCase

from project_manager_agent.ai_agents.meeting_notetaker_agent import MeetingNotetakerAgent

NOTES = 'Kickoff. Bilal will build the API by Friday. Farhan Qureshi (client) wants card payments.'
SUMMARY = json.dumps({'summary': 'Kickoff.', 'action_items': [{'action': 'Build the API', 'owner': 'Bilal'}]})


def analyse(names, team):
    replies = ['yes', json.dumps(names), SUMMARY]
    with mock.patch.object(MeetingNotetakerAgent, '_call_llm', side_effect=replies):
        return MeetingNotetakerAgent().summarize_meeting(NOTES, None, {'name': 'Bakehouse', 'team_members': team})


class MeetingNotesPeopleTests(SimpleTestCase):

    def test_a_client_named_beside_the_team_is_a_warning(self):
        result = analyse(['Bilal', 'Farhan Qureshi'], ['Bilal Ahmed'])
        self.assertTrue(result['success'])
        self.assertEqual(result['summary'], 'Kickoff.')
        self.assertTrue(result['warnings'][0].startswith('Not on this project yet: Farhan Qureshi.'))

    def test_notes_naming_no_one_on_the_project_are_refused(self):
        result = analyse(['Farhan Qureshi'], ['Bilal Ahmed'])
        self.assertFalse(result['success'])
        self.assertIn('Unrecognized members: Farhan Qureshi', result['instructions'])

    def test_a_project_with_no_one_on_tasks_yet_takes_its_kickoff_notes(self):
        result = analyse(['Bilal', 'Farhan Qureshi'], [])
        self.assertTrue(result['success'])
        self.assertIn('Bilal, Farhan Qureshi', result['warnings'][0])

    def test_everyone_on_the_project_means_no_warning(self):
        result = analyse(['Bilal'], ['Bilal Ahmed'])
        self.assertNotIn('warnings', result)
