"""Research & Enrichment is real (docx item 3): the candidate's public GitHub and an AI research profile.

It was word rules over the CV; the LinkedIn and GitHub links from the apply form were never used.
"""
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from core.api_key_service import QuotaExhausted
from recruitment_agent.agents.lead_enrichment import research
from recruitment_agent.agents.lead_enrichment.lead_research_enrichment_agent import LeadResearchEnrichmentAgent

CV = {'name': 'Cara Khan', 'skills': ['Python', 'Django'], 'summary': 'Backend developer',
      'experience': [{'company': 'Systems Ltd', 'role': 'Developer', 'start_date': '2020', 'end_date': 'Present'}],
      'education': [{'degree': 'BS CS'}], 'certifications': []}


def github_api(path, timeout):
    if path == '/users/cara-khan':
        return {'name': 'Cara Khan', 'created_at': '2019-01-01T00:00:00Z', 'public_repos': 12, 'followers': 3}
    return [{'name': 'shop-api', 'description': 'Django REST shop', 'language': 'Python', 'stargazers_count': 4,
             'fork': False, 'pushed_at': '2026-09-01T00:00:00Z'},
            {'name': 'forked-lib', 'language': 'C', 'fork': True}]


class ResearchTests(SimpleTestCase):

    def test_a_profile_link_and_not_a_repository_link(self):
        self.assertEqual(research.github_login('https://github.com/cara-khan'), 'cara-khan')
        self.assertEqual(research.github_login('github.com/cara-khan/'), 'cara-khan')
        self.assertIsNone(research.github_login('https://github.com/cara-khan/shop-api'))
        self.assertIsNone(research.github_login('https://linkedin.com/in/cara'))

    def test_github_facts_leave_out_forks(self):
        with mock.patch.object(research, '_get', side_effect=github_api):
            facts = research.github_facts('https://github.com/cara-khan')
        self.assertEqual((facts['login'], facts['public_repos'], facts['top_languages']), ('cara-khan', 12, ['Python']))
        self.assertEqual([r['name'] for r in facts['recent']], ['shop-api'])

    def test_github_not_answering_is_no_facts(self):
        with mock.patch.object(research, '_get', side_effect=OSError('timed out')):
            self.assertIsNone(research.github_facts('https://github.com/cara-khan'))

    def test_enrichment_adds_the_ai_profile_and_github(self):
        client = mock.Mock()
        client.send_prompt.return_value = {'headline': 'Backend developer, 6 years of Django', 'seniority': 'Senior',
                                           'strengths': ['Django REST work on GitHub'], 'gaps': ['No AWS shown'],
                                           'verify': ['Ask about the shop API'], 'based_on': ['CV', 'GitHub']}
        application = SimpleNamespace(github_url='https://github.com/cara-khan', cover_letter='I love APIs.',
                                      linkedin_url=None, current_location='Lahore', education=None,
                                      previous_company=None, other_links=None)
        agent = LeadResearchEnrichmentAgent(groq_client=client)
        with mock.patch.object(research, '_get', side_effect=github_api):
            enriched = agent.enrich(CV, {'total_experience_years': 6}, application=application,
                                    job=SimpleNamespace(title='Backend Engineer'), job_keywords=['django', 'aws'])
        self.assertEqual(enriched['research']['seniority'], 'Senior')
        self.assertEqual(enriched['github']['login'], 'cara-khan')
        sent = client.send_prompt.call_args.args[1]
        self.assertIn('shop-api', sent)              # the GitHub facts went to the AI
        self.assertIn('I love APIs.', sent)          # and the cover letter
        self.assertIn('primary_role', enriched)      # the rule-based part is still there

    def test_an_ai_failure_keeps_the_rule_based_enrichment(self):
        client = mock.Mock()
        client.send_prompt.side_effect = RuntimeError('model down')
        enriched = LeadResearchEnrichmentAgent(groq_client=client).enrich(CV, {})
        self.assertIsNone(enriched['research'])
        self.assertIn('seniority_level', enriched)

    def test_running_out_of_tokens_stops_the_run(self):
        client = mock.Mock()
        client.send_prompt.side_effect = QuotaExhausted('used up')
        with self.assertRaises(QuotaExhausted):
            LeadResearchEnrichmentAgent(groq_client=client).enrich(CV, {})
