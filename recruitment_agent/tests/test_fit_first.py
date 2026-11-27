"""Fit first, then confidence (client decision Q3, 27 Nov 2026).

The confidence score starts from the AI's fit score and adds up to 68 for skills and experience, so a candidate the
AI rated 35 for the role reached 82 and INTERVIEW, which emails the invitation by itself. Below the minimum fit score
(50 unless the recruiter sets another) an INTERVIEW becomes HOLD for a person to look at.
"""
from unittest import mock

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import recruitment_agent as views
from core.models import Company, CompanyUser
from recruitment_agent import sharing
from recruitment_agent.agents.lead_qualification.lead_qualification_agent import (DEFAULT_MIN_FIT_SCORE,
                                                                                LeadQualificationAgent)
from recruitment_agent.models import RecruiterQualificationSettings

CV = {'skills': ['React', 'TypeScript'], 'experience': []}


def decide(decision, confidence=82):
    """The confidence rule's own answer, before the fit rule looks at it."""
    return mock.patch.object(LeadQualificationAgent, '_recruiter_decide',
                             return_value=(decision, confidence, {'base_score': 35}))


class FitFirstTests(SimpleTestCase):

    def qualify(self, fit, decision='INTERVIEW', **kwargs):
        with decide(decision):
            return LeadQualificationAgent().qualify(CV, {'role_fit_score': fit, 'total_experience_years': 4},
                                                    ['React'], **kwargs)

    def test_a_poor_fit_is_held_however_high_the_confidence(self):
        result = self.qualify(35)
        self.assertEqual(result['decision'], 'HOLD')
        self.assertEqual(result['confidence_score'], 82)
        self.assertTrue(result['confidence_breakdown']['held_by_fit'])
        self.assertEqual(result['confidence_breakdown']['min_fit_score'], DEFAULT_MIN_FIT_SCORE)
        first = result['reasoning'][0] if isinstance(result['reasoning'], list) else result['reasoning']
        self.assertTrue(first.startswith('HOLD rather than INTERVIEW: the fit score 35 is below the minimum 50 '
                                         '(confidence 82).'), first)

    def test_a_good_fit_is_still_invited(self):
        result = self.qualify(60)
        self.assertEqual(result['decision'], 'INTERVIEW')
        self.assertFalse(result['confidence_breakdown']['held_by_fit'])

    def test_exactly_the_minimum_is_enough(self):
        self.assertEqual(self.qualify(50)['decision'], 'INTERVIEW')

    def test_the_recruiters_own_minimum_is_used(self):
        self.assertEqual(self.qualify(35, min_fit_score=30)['decision'], 'INTERVIEW')
        self.assertEqual(self.qualify(65, min_fit_score=70)['decision'], 'HOLD')

    def test_zero_switches_the_rule_off(self):
        self.assertEqual(self.qualify(10, min_fit_score=0)['decision'], 'INTERVIEW')

    def test_a_cv_with_no_fit_score_is_decided_on_confidence(self):
        self.assertEqual(self.qualify(None)['decision'], 'INTERVIEW')

    def test_hold_and_reject_are_never_changed(self):
        self.assertEqual(self.qualify(10, decision='HOLD')['decision'], 'HOLD')
        self.assertEqual(self.qualify(10, decision='REJECT')['decision'], 'REJECT')
        self.assertFalse(self.qualify(10, decision='REJECT')['confidence_breakdown']['held_by_fit'])


class MinimumFitSettingTests(TestCase):

    def setUp(self):
        company = Company.objects.create(name='Acme', email='acme@test.local')
        self.ann = CompanyUser.objects.create(company=company, email='ann@test.local', full_name='Ann Owner',
                                              role='admin', password_hash='x', is_active=True)

    def call(self, method, data=None):
        factory = APIRequestFactory()
        request = factory.get('/') if method == 'get' else factory.post('/', data or {}, format='json')
        force_authenticate(request, user=self.ann)
        response = views.qualification_settings(request)
        response.render()
        return response.status_code, response.data

    def test_the_default_is_50_and_shown(self):
        status, body = self.call('get')
        self.assertEqual((status, body['data']['min_fit_score']), (200, 50))

    def test_it_is_saved_and_used_whether_or_not_custom_thresholds_are_on(self):
        status, body = self.call('post', {'min_fit_score': 40})
        self.assertEqual((status, body['data']['min_fit_score']), (200, 40))
        self.assertFalse(RecruiterQualificationSettings.objects.get(company_user=self.ann).use_custom_thresholds)
        self.assertEqual(sharing.min_fit(self.ann), 40)

    def test_out_of_range_is_refused(self):
        for bad in (-1, 101, 'many'):
            status, _ = self.call('post', {'min_fit_score': bad})
            self.assertEqual(status, 400, bad)
        self.assertEqual(sharing.min_fit(self.ann), 50)

    def test_nobody_set_means_the_default(self):
        self.assertIsNone(sharing.min_fit(None))
