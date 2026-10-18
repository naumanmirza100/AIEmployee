"""A job's requirements written as phrases are matched to the skills a CV names in its own words.

Keywords an AI drew from a job's description came out as phrases ("Writing tests", "Secure coding"), and
matched only word for word, a Flutter developer with exactly those skills was held back as missing them.
"""
from django.test import SimpleTestCase

from recruitment_agent.agents.lead_qualification.lead_qualification_agent import LeadQualificationAgent
from recruitment_agent.skill_equivalences import is_related_match


class SkillPhraseTests(SimpleTestCase):

    def test_a_phrase_and_a_skill_sharing_a_word_that_names_it_are_related(self):
        for skill, requirement in [('unit tests', 'writing tests'), ('secure storage', 'secure coding'),
                                   ('payment integrations', 'integration with payment gateways'),
                                   ('github actions', 'ci/cd'), ('flutter', 'mobile app development')]:
            self.assertTrue(is_related_match(skill, requirement), (skill, requirement))

    def test_a_word_that_names_nothing_does_not_make_them_related(self):
        for skill, requirement in [('data entry', 'data protection'), ('react', 'scalable architecture'),
                                   ('project management', 'stakeholder management')]:
            self.assertFalse(is_related_match(skill, requirement), (skill, requirement))

    def test_a_strong_candidate_is_invited_when_the_job_names_its_skills_in_phrases(self):
        cv = {'skills': ['Flutter', 'Dart', 'Bloc', 'Riverpod', 'REST', 'GraphQL', 'Firebase', 'secure storage',
                         'biometrics', 'payment integrations', 'unit tests', 'widget tests', 'GitHub Actions', 'Git'],
              'experience': [{'role': 'Senior Flutter Developer', 'company': 'PayWave', 'start_date': 'March 2023',
                              'end_date': 'present'}]}
        insights = {'total_experience_years': 3.8, 'key_skills': cv['skills']}
        keywords = ['Flutter', 'Dart', 'Bloc', 'Riverpod', 'REST', 'GraphQL', 'Firebase', 'Git', 'CI/CD',
                    'Mobile app development', 'Secure coding', 'Scalable architecture', 'Writing tests']
        result = LeadQualificationAgent().qualify(cv, insights, keywords, {'normalized_skills': cv['skills']})
        self.assertEqual(result['decision'], 'INTERVIEW', result.get('confidence_breakdown'))
        self.assertIn('Writing tests', result['related_matched_skills'])
