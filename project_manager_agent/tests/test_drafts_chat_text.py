"""`drafts.chat_text` — the sentence shown above the gap form.

The agent's `answer` is frequently the JSON its actions were parsed from. It
used to be passed straight to the chat and rendered as a screen of code above
the form.
"""

from django.test import SimpleTestCase

from project_manager_agent import drafts


class ChatTextTests(SimpleTestCase):

    actions = [
        {'action': 'create_project', 'project_name': 'Rebuild'},
        {'action': 'create_task', 'task_title': 'A'},
        {'action': 'create_task', 'task_title': 'B'},
    ]

    def test_json_is_replaced_with_a_plain_summary(self):
        for raw in ('[{"action": "create_task"}]', '{"action": "create_project"}',
                    '  [\n {"action": "x"} ]'):
            with self.subTest(raw=raw):
                text = drafts.chat_text(self.actions, raw)
                self.assertNotIn('{', text)
                self.assertIn('1 project and 2 tasks', text)

    def test_prose_with_embedded_actions_is_replaced_too(self):
        text = drafts.chat_text(self.actions, 'Sure! Here: {"action": "create_task"}')
        self.assertIn('1 project and 2 tasks', text)

    def test_a_real_sentence_is_kept(self):
        self.assertEqual(drafts.chat_text(self.actions, 'I split this into three tasks.'),
                         'I split this into three tasks.')

    def test_no_answer_still_gives_a_sentence(self):
        self.assertIn('2 tasks', drafts.chat_text(self.actions[1:], None))

    def test_singular_nouns(self):
        self.assertIn('1 task.', drafts.chat_text([{'action': 'create_task'}], ''))
