"""An Operations summary is stored as markdown, not as a code block.

Asked for markdown, the AI sometimes wrapped the whole summary in a ``` block, and
the summary page then showed it as raw code: hashes and stars instead of headings.
"""
from unittest import mock

from django.test import SimpleTestCase

from operations_agent.agents.summarization_agent import DocumentSummarizationAgent, unfence

SUMMARY = '## Overview\nA three-year agreement.\n\n## Key Findings\n1. Uptime of 99.5%\n2. Renewal notice of 60 days'


class SummaryUnfencedTests(SimpleTestCase):

    def test_a_summary_wrapped_in_a_fence_is_unwrapped(self):
        for wrapped in (f'```markdown\n{SUMMARY}\n```', f'```\n{SUMMARY}\n```', f'  ```md\r\n{SUMMARY}\r\n```  \n'):
            self.assertEqual(unfence(wrapped), SUMMARY)

    def test_plain_markdown_and_a_code_block_inside_it_are_left_alone(self):
        self.assertEqual(unfence(SUMMARY), SUMMARY)
        inner = f'{SUMMARY}\n\n```\nGET /api/accounts\n```'
        self.assertEqual(unfence(inner), inner)
        self.assertEqual(unfence(''), '')

    def test_the_summary_saved_is_the_unwrapped_one_and_its_findings_are_read(self):
        agent = DocumentSummarizationAgent()
        with mock.patch.object(agent, '_call_llm_for_writing', return_value=f'```markdown\n{SUMMARY}\n```'):
            result = agent._summarize_single('The agreement text.', 'msa.pdf', 3)
        self.assertEqual(result['rich_summary'], SUMMARY)
        self.assertEqual(result['key_findings'], ['Uptime of 99.5%', 'Renewal notice of 60 days'])
