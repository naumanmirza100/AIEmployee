"""The PM Q&A sees due dates, today's date and what is late (21 Nov 2026, the test report's PM 1).

Its context gave each task a title, status, priority and assignee but never a due date, and the prompt had no today's
date: "Which tasks are overdue?" was answered "I don't see any tasks marked as overdue" with "Book the movers" three
days late, which the project record and the notification scan both reported.
"""
from datetime import timedelta
from unittest import mock

from django.utils import timezone

from api.views import pm_agent
from project_manager_agent.ai_agents.knowledge_qa_agent import KnowledgeQAAgent

from .base import PMTestCase


class DueDates(PMTestCase):

    def test_the_prompt_has_today_the_due_dates_and_the_late_tasks(self):
        late = timezone.now() - timedelta(days=3)
        self.task(title='Book the movers', status='todo', due_date=late)
        self.task(title='Pack the IT equipment', status='done', due_date=late)       # done: not late
        self.task(title='Order boxes', status='todo', due_date=timezone.now() + timedelta(days=4))
        prompts = []

        def answer(*args, **kwargs):
            prompts.append(kwargs.get('prompt') or (args[0] if args else ''))
            return 'Book the movers is three days late.'
        with mock.patch.object(KnowledgeQAAgent, '_call_llm', side_effect=answer):
            code, body = self.call(pm_agent.knowledge_qa, self.dash, {'question': 'Which tasks are overdue right now?'})
        self.assertEqual(code, 200, body)
        prompt = '\n'.join(prompts)
        self.assertIn(f'Today is {timezone.localdate().isoformat()}.', prompt)
        self.assertIn('[OVERDUE by 3 day(s)]', prompt)
        overdue = prompt.split('Overdue right now', 1)[1].split('\n\n', 1)[0]
        self.assertIn('Book the movers', overdue)
        self.assertNotIn('Pack the IT equipment', overdue)
        self.assertNotIn('Order boxes', overdue)
        self.assertIn('[Deadline: ', prompt)
