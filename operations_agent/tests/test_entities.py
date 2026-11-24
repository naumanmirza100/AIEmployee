"""An uploaded contract's entities include its amounts, wherever in the document they are.

Entities were taken from the first 3,000 characters only. The FinEdge agreement's fees ("The fee for the build of
the App is PKR 18,500,000") begin at character 3,183, after the definitions, so the contract had no amounts.
"""
from django.test import SimpleTestCase

from operations_agent.agents.document_processing_agent import _entity_excerpt


class EntityExcerptTests(SimpleTestCase):

    def test_amounts_after_the_opening_pages_are_read_too(self):
        text = ('1. Definitions. ' * 250 + '\n5.1 The fee for the build of the App is PKR 18,500,000, payable in milestones.'
                '\nNothing to see on this line.\n5.2 Support: PKR 650,000 per calendar month.\nService credit of 5% a month.')
        excerpt = _entity_excerpt(text)
        self.assertTrue(excerpt.startswith('1. Definitions.'))
        for figure in ('PKR 18,500,000', 'PKR 650,000', '5% a month'):
            self.assertIn(figure, excerpt)
        self.assertNotIn('Nothing to see', excerpt)

    def test_a_short_document_is_read_whole(self):
        self.assertEqual(_entity_excerpt('A short memo. Budget PKR 2,000,000.'), 'A short memo. Budget PKR 2,000,000.')

    def test_the_extra_lines_are_capped(self):
        text = 'x' * 3000 + '\n' + '\n'.join(f'Line {i}: PKR {i},000,000' for i in range(1000))
        self.assertLessEqual(len(_entity_excerpt(text)), 3000 + 2500 + 10)
