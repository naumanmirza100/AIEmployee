"""Prioritize's reasoning names tasks by their titles: it wrote "Task 873, 'Design…'," and "backend API development
(875)", though nobody sees task ids (PM demo rehearsal, 25 Oct 2026)."""
from django.test import SimpleTestCase

from project_manager_agent.ai_agents.task_prioritization_agent import _without_task_ids

TITLES = {'873': 'Design and implement database schema', '875': 'Develop backend APIs'}


class ReasoningWordsTests(SimpleTestCase):

    def test_ids_give_way_to_titles(self):
        text = ("Task 873, 'Design and implement database schema,' is positioned first because tasks like backend "
                "API development (875) depend on it. Task 875 follows.")
        self.assertEqual(_without_task_ids(text, TITLES),
                         "'Design and implement database schema,' is positioned first because tasks like backend "
                         'API development depend on it. "Develop backend APIs" follows.')

    def test_numbers_that_are_not_task_ids_stay(self):
        text = 'It takes 3 days (about 24 hours) and saves 875 rupees.'
        self.assertEqual(_without_task_ids(text, {'873': 'Schema'}), text)
        self.assertIsNone(_without_task_ids(None, TITLES))
