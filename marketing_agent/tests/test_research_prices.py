"""A question about prices gets a short answer with price ranges, not a competitor report.

"Typical monthly prices for app maintenance plans in Pakistan, and what they include" was classed as a competitor
study: three invented rival companies, a comparison table shown as raw pipes, and no price.
"""
from unittest import mock

from django.test import SimpleTestCase

from marketing_agent.agents.market_research_agent import MarketResearchAgent


class PriceQuestionTests(SimpleTestCase):

    def setUp(self):
        self.agent = MarketResearchAgent()

    def test_a_price_question_is_answered_briefly_by_the_ais_reading(self):
        # The AI decides, told that a price question is brief; a word list decided before it (29 Oct 2026).
        self.assertIn('prices, costs, rates or fees is brief', self.agent.DEPTH_SYSTEM)
        with mock.patch.object(MarketResearchAgent, '_call_llm_for_reasoning', return_value='brief') as llm:
            brief = self.agent._wants_brief_answer(
                'Typical monthly prices for app maintenance plans in Pakistan, and what they include')
        self.assertTrue(brief)
        llm.assert_called_once()

    def test_a_request_for_a_report_still_gets_one(self):
        with mock.patch.object(MarketResearchAgent, '_call_llm_for_reasoning', return_value='full') as llm:
            self.assertFalse(self.agent._wants_brief_answer('Competitor analysis of pricing for app maintenance'))
        llm.assert_called_once()

    def test_the_short_answer_asks_for_price_ranges_and_no_invented_companies(self):
        self.assertIn('typical ranges in the local', self.agent.BRIEF_TEMPLATE)
        self.assertIn('Name no company the user did not name', self.agent.BRIEF_TEMPLATE)
