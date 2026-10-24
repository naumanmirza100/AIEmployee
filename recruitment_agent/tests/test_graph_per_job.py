""""Candidates per job by decision" is a bar per job and decision, not three bars for all jobs together.

A chart holds one series, and the AI was given the decision totals and the job totals apart, so it drew
Interview / Hold / Reject across every job.
"""
from unittest import mock

from django.test import TestCase

from core.models import Company, CompanyUser
from recruitment_agent.agents.graph_generator_agent import GraphGeneratorAgent
from recruitment_agent.models import CVRecord, JobDescription


class DecisionsPerJobChartTests(TestCase):

    def setUp(self):
        company = Company.objects.create(name='Acme', email='acme@test.local')
        hira = CompanyUser.objects.create(company=company, email='hira@test.local', full_name='Hira',
                                          role='admin', password_hash='x', is_active=True)
        flutter = JobDescription.objects.create(title='Flutter Developer', description='Apps', company=company,
                                                company_user=hira, type='Full-time')
        qa = JobDescription.objects.create(title='QA Engineer', description='Tests', company=company,
                                           company_user=hira, type='Full-time')
        for job, decision in [(flutter, 'INTERVIEW'), (flutter, 'INTERVIEW'), (flutter, 'REJECT'), (qa, 'HOLD')]:
            CVRecord.objects.create(file_name='cv.pdf', parsed_json='{}', job_description=job,
                                    qualification_decision=decision)
        self.llm = mock.Mock()
        self.agent = GraphGeneratorAgent(self.llm, hira)

    def test_one_bar_per_job_and_decision_without_asking_the_ai(self):
        result = self.agent.generate_graph('Candidates per job by decision, as a bar chart')
        self.assertEqual(result['chart']['data'], {'Flutter Developer · Interview': 2, 'Flutter Developer · Reject': 1,
                                                   'QA Engineer · Hold': 1})
        self.assertEqual(result['chart']['type'], 'bar')
        self.assertIn('Flutter Developer has the most candidates (3)', result['insights'])
        self.llm.send_prompt_text.assert_not_called()

    def test_other_charts_still_go_to_the_ai(self):
        self.llm.send_prompt_text.return_value = '{"chart_type": "pie", "title": "Decisions", "data": {"INTERVIEW": 2}}'
        result = self.agent.generate_graph('Candidates by decision as a pie chart')
        self.llm.send_prompt_text.assert_called_once()
        self.assertEqual(result['chart']['title'], 'Decisions')
