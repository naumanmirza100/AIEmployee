"""Scoring matches whole terms, not pieces of words.

"it" was found inside "university", so every degree counted as a computing degree; "api" inside "rapid", "java"
inside "javascript" and "bert" inside "Robert" changed which skills a candidate was said to have.
"""
from unittest import mock

from django.test import SimpleTestCase

from recruitment_agent.agents.summarization.summarization_agent import SummarizationAgent
from recruitment_agent.skill_equivalences import contains_term, is_exact_match, skill_matches_keyword


class WholeWordTests(SimpleTestCase):

    def test_terms(self):
        self.assertTrue(contains_term('react.js developer', 'react'))
        self.assertTrue(contains_term('c++ and c#', 'c++'))
        self.assertFalse(contains_term('rapid prototyping', 'api'))
        self.assertFalse(contains_term('javascript', 'java'))
        self.assertFalse(contains_term('university of punjab', 'it'))

    def test_skills(self):
        self.assertFalse(skill_matches_keyword('rapid prototyping', 'api'))
        self.assertFalse(is_exact_match('javascript', 'java'))
        self.assertTrue(skill_matches_keyword('react.js developer', 'react'))

    def test_a_business_degree_is_not_a_computing_degree(self):
        agent = SummarizationAgent(groq_client=mock.Mock(), log_service=mock.Mock())
        business = agent._calculate_education_relevance([{'degree': 'BBA', 'institution': 'University of the Punjab'}], None)
        computing = agent._calculate_education_relevance([{'degree': 'BS IT', 'institution': 'University of the Punjab'}], None)
        self.assertLess(business, computing)
