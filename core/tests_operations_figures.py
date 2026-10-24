"""Operations pulls a document's key figures into a table, and Analytics lists them across documents.

The summary said a contract was worth something and a report had results; nothing put the numbers in one place.
"""
import json
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import operations_agent as views
from core.models import Company, CompanyModulePurchase, CompanyUser
from operations_agent import figures
from operations_agent.agents.document_processing_agent import DocumentProcessingAgent
from operations_agent.models import OperationsDocument

ANSWER = '''```json
[{"label": "Contract value", "value": "1,250,000", "unit": "PKR", "period": "2026"},
 {"label": "Uptime target", "value": 99.9, "unit": "%", "period": "monthly"},
 {"label": "Support hours", "value": "business hours", "unit": "", "period": ""},
 {"label": "", "value": 3}]
```'''


class FiguresTests(TestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.crestline = self.company('Crestline')
        self.rival = self.company('Rival')
        self.sara = CompanyUser.objects.create(company=self.crestline, email='sara@crestline.test',
                                               full_name='Sara Ahmed', role='owner', password_hash='x', is_active=True)
        self.msa = self.document(self.crestline, 'FinEdge MSA', 'The total contract value is PKR 1,250,000...')

    def company(self, name):
        company = Company.objects.create(name=name, email=f'{name.lower()}@test.local')
        CompanyModulePurchase.objects.create(company=company, module_name='operations_agent', status='active',
                                             is_complimentary=True)
        return company

    def document(self, company, title, text):
        return OperationsDocument.objects.create(company=company, title=title, original_filename=f'{title}.pdf',
                                                 file=f'operations/documents/{title}.pdf', parsed_text=text)

    def call(self, view, method='post', actor=None, **kwargs):
        request = getattr(self.factory, method)('/')
        force_authenticate(request, user=actor or self.sara)
        response = view(request, **kwargs)
        response.render()
        return response.status_code, json.loads(response.content)

    def extract(self, doc, answer=ANSWER):
        with mock.patch.object(DocumentProcessingAgent, '_call_llm_for_reasoning', return_value=answer) as llm:
            result = self.call(views.extract_document_figures, document_id=doc.id)
        return result, llm

    def test_figures_are_read_and_kept_on_the_document(self):
        (code, body), llm = self.extract(self.msa)
        self.assertEqual((code, body['count']), (200, 3), body)
        self.msa.refresh_from_db()
        items = self.msa.metadata['figures']['items']
        self.assertEqual(items[0], {'label': 'Contract value', 'value': 1250000.0, 'unit': 'PKR', 'period': '2026'})
        self.assertEqual(items[1]['value'], 99.9)
        self.assertIsNone(items[2]['value'])                        # not a number: kept, with no value
        self.assertIn('FinEdge MSA', llm.call_args[0][0])

    def test_reading_again_replaces_them_and_keeps_the_rest_of_the_metadata(self):
        self.msa.metadata = {'pages': 12}
        self.msa.save()
        self.extract(self.msa)
        self.extract(self.msa, answer='[{"label": "Penalty", "value": 5, "unit": "%"}]')
        self.msa.refresh_from_db()
        self.assertEqual(self.msa.metadata['pages'], 12)
        self.assertEqual([f['label'] for f in self.msa.metadata['figures']['items']], ['Penalty'])

    def test_an_answer_that_is_not_json_gives_no_figures(self):
        self.assertEqual(figures.parse('The contract is worth a lot.'), [])
        self.assertEqual(figures.parse('{"figures": [{"label": "Fee", "value": "12"}]}')[0]['value'], 12.0)

    def test_another_companys_document_is_not_read(self):
        theirs = self.document(self.rival, 'Rival plan', 'Revenue 10m')
        (code, _), llm = self.extract(theirs)
        self.assertEqual(code, 404)
        self.assertFalse(llm.called)

    def test_a_document_without_text_is_refused(self):
        empty = self.document(self.crestline, 'Scan', '')
        (code, _), llm = self.extract(empty)
        self.assertEqual(code, 400)
        self.assertFalse(llm.called)

    def test_analytics_lists_the_companys_figures(self):
        self.extract(self.msa)
        theirs = self.document(self.rival, 'Rival plan', 'Revenue 10m')
        theirs.metadata = {'figures': {'items': [{'label': 'Revenue', 'value': 10, 'unit': 'm', 'period': ''}]}}
        theirs.save()
        request = self.factory.get('/', {'range': 'all'})
        force_authenticate(request, user=self.sara)
        response = views.operations_analytics(request)
        rows = response.data['document_figures']
        self.assertEqual({r['label'] for r in rows}, {'Contract value', 'Uptime target', 'Support hours'})
        self.assertEqual(rows[0]['document'], 'FinEdge MSA')
