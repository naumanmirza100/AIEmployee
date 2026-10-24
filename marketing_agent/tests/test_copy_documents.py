"""Marketing writes social media posts and ad copy, not only long documents.

The Documents screen offered strategies, proposals, reports and briefs. Copy for a post or an ad was asked of the
document prompt, which wants ordered sections, tables and "detailed in-depth analysis", so there was no way to get it.
"""
from unittest import mock

from marketing_agent.agents.document_authoring_agent import DocumentAuthoringAgent
from marketing_agent.models import MarketingDocument
from marketing_agent.tests.base import MarketingTestCase

POSTS = '## LinkedIn\n1. Your till, sorted before the weekend rush. #retail'


class CopyDocumentTests(MarketingTestCase):

    def write(self, document_type, notes='', campaign=None, user=None):
        agent = DocumentAuthoringAgent()
        with mock.patch.object(DocumentAuthoringAgent, '_call_llm_for_writing', return_value=POSTS) as llm:
            result = agent.process('create', (user or self.ann).id, document_type, {'notes': notes},
                                   campaign_id=campaign.id if campaign else None)
        return result, llm

    def test_social_posts_are_written_for_the_campaign_and_saved(self):
        spring = self.campaign(self.ann, name='Spring till offer', description='A card till for small shops',
                               industry='Retail', language='Urdu')
        result, llm = self.write('social_posts', notes='Only LinkedIn, friendly tone', campaign=spring)

        self.assertTrue(result['success'], result)
        doc = MarketingDocument.objects.get(id=result['document_id'])
        self.assertEqual((doc.document_type, doc.title, doc.content, doc.campaign), ('social_posts', 'Social media posts', POSTS, spring))
        self.assertEqual(doc.get_document_type_display(), 'Social Media Posts')
        prompt = llm.call_args.kwargs['prompt']
        for expected in ('Campaign: Spring till offer', 'About: A card till for small shops', 'Industry: Retail',
                         'Only LinkedIn, friendly tone', 'Language: Urdu', 'X up to 280'):
            self.assertIn(expected, prompt)
        self.assertNotIn('CORE RULES', prompt)                     # not the long-document prompt
        self.assertEqual(llm.call_count, 1)

    def test_ad_copy_needs_no_campaign(self):
        result, llm = self.write('ad_copy', notes='Weekend sale on tills')
        self.assertTrue(result['success'], result)
        prompt = llm.call_args.kwargs['prompt']
        self.assertIn('No campaign chosen', prompt)
        self.assertIn('at most 30 characters', prompt)
        self.assertEqual(MarketingDocument.objects.get(id=result['document_id']).title, 'Ad copy')

    def test_another_persons_campaign_is_not_used(self):
        theirs = self.campaign(self.rita, name='Rival offer')
        result, llm = self.write('social_posts', campaign=theirs)
        self.assertEqual(result, {'success': False, 'error': 'Campaign not found'})
        self.assertFalse(llm.called)

    def test_a_strategy_still_uses_the_document_prompt(self):
        result, llm = self.write('strategy', notes='Grow in Lahore')
        self.assertTrue(result['success'], result)
        self.assertIn('CORE RULES', llm.call_args.kwargs['prompt'])
