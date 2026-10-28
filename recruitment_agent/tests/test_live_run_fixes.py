"""What the Recruitment live run on Margalla (28 Oct 2026) found, fixed.

- The candidate page said a candidate's years four ways (5.75, ~5.8, "5-8", and the AI summary's own "about 3").
- The assistant gave interview times in UTC, could not see the Research, and answered "delete every rejected
  candidate" as if it were about decisions.
- "Interviews per day" counted the day an interview was made; a bar chart of a trend came back as a line.
- Messages named the CV file, or "1 candidate(s)", instead of the person.
- A workflow template already in use could be added again.
"""
import json
from datetime import datetime, timedelta
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import recruitment_agent as rec_views
from api.views import recruitment_workflows as wf_views
from core.models import Company, CompanyModulePurchase, CompanyUser
from recruitment_agent import intent
from recruitment_agent.agents.graph_generator_agent import GraphGeneratorAgent
from recruitment_agent.agents.recruitment_qa_agent import RecruitmentQAAgent
from recruitment_agent.agents.summarization.summarization_agent import SummarizationAgent
from recruitment_agent.experience import about_years
from recruitment_agent.models import CVRecord, Interview, JobDescription


class YearsTests(SimpleTestCase):

    def test_one_way_to_say_the_years(self):
        self.assertEqual(about_years(5.75), 'about 6 years')
        self.assertEqual(about_years(5.25), 'about 5.5 years')
        self.assertEqual(about_years(1.1), 'about 1 year')
        self.assertEqual(about_years(0.4), 'about 5 months')
        self.assertEqual(about_years(None), '')

    def test_a_year_alone_counts_from_the_middle_of_it(self):
        agent = SummarizationAgent.__new__(SummarizationAgent)
        self.assertEqual(agent._parse_date('2021'), datetime(2021, 7, 1))
        self.assertEqual(agent._parse_date('Mar 2021'), datetime(2021, 3, 1))
        self.assertEqual(agent._parse_date('2021-03'), datetime(2021, 3, 1))
        years = agent._estimate_total_experience_years([
            {'company': 'Saddar Web Studio', 'role': 'Junior Developer', 'start_date': '2021', 'end_date': '2022'},
            {'company': 'Potohar Labs', 'role': 'Frontend Engineer', 'start_date': '2022', 'end_date': 'Present'}])
        expected = (timezone.now().year - 2021) + (timezone.now().month - 7) / 12
        self.assertAlmostEqual(years, expected, delta=0.1)


class AssistantTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Margalla Software', email='hello@margalla.test')
        self.owner = CompanyUser.objects.create(company=self.company, email='sana@margalla.test', full_name='Sana',
                                                role='owner', password_hash='x', is_active=True)
        self.job = JobDescription.objects.create(title='Senior Frontend Engineer', description='React.',
                                                 company=self.company, company_user=self.owner)
        self.cv = CVRecord.objects.create(
            file_name='Hira_Siddiqui_CV.pdf', job_description=self.job, qualification_decision='INTERVIEW',
            role_fit_score=90, parsed_json=json.dumps({'name': 'Hira Siddiqui', 'email': 'hira@mail.test'}),
            enriched_json=json.dumps({
                'research': {'headline': 'Frontend engineer, four years of React', 'seniority': 'Mid',
                             'strengths': ['Vite migration'], 'gaps': ['No team lead experience'],
                             'verify': ['GitHub shows HTML only: ask for React code'], 'based_on': ['CV', 'GitHub']},
                'github': {'url': 'https://github.com/hira', 'public_repos': 8, 'account_years': 3,
                           'top_languages': ['HTML', 'CSS'], 'recent': [{'name': 'hello-world'}]}}))
        Interview.objects.create(candidate_name='Hira Siddiqui', candidate_email='hira@mail.test',
                                 job_role='Senior Frontend Engineer', cv_record=self.cv, available_slots_json='[]',
                                 company_user=self.owner, status='SCHEDULED', timezone_name='Asia/Karachi',
                                 scheduled_datetime=timezone.make_aware(datetime(2026, 10, 29, 5, 0),
                                                                        timezone.utc))
        self.agent = RecruitmentQAAgent(groq_client=mock.Mock())

    def test_the_dossier_holds_the_research_and_the_time_on_the_companys_clock(self):
        dossier = self.agent._build_candidate_dossier(self.owner, 'What does the research say about Hira Siddiqui?')
        self.assertIn('Research: check in the interview: GitHub shows HTML only', dossier)
        self.assertIn('Research gaps against the job: No team lead experience', dossier)
        self.assertIn('8 public repositories', dossier)
        self.assertIn('10:00 AM', dossier)
        self.assertIn('Asia/Karachi', dossier)
        self.assertNotIn('05:00:00+00:00', dossier)

    def test_the_jobs_listing_gives_interview_times_on_the_companys_clock(self):
        data = self.agent._get_recruitment_data(self.owner)
        [iv] = data['jobs'][0]['interview_details']
        self.assertIn('10:00 AM', iv['scheduled_datetime'])

    def test_answers_lead_with_the_answer_not_the_job(self):
        prompt = self.agent._answer_instructions('Which interviews are booked?', 'CONTEXT', wants='list')
        self.assertIn('Start with the answer itself', prompt)
        self.assertNotIn('description, requirements, scores', prompt)
        # Read as "detail" (live run, Q1: "how many applied, and what did each one get?") it still dumped the job.
        detail = self.agent._answer_instructions('How many applied and what did each get?', 'CONTEXT', wants='detail')
        self.assertIn("do NOT repeat the job's description", detail)

    def test_the_dossier_says_the_years_as_the_page_does(self):
        self.cv.insights_json = json.dumps({'total_experience_years': 5.75})
        self.cv.save()
        dossier = self.agent._build_candidate_dossier(self.owner, 'Tell me about Hira Siddiqui')
        self.assertIn('Years of experience: about 6 years', dossier)

    def test_a_delete_request_says_where_deleting_is_done(self):
        answer = intent.reply({'kind': 'action', 'area': 'delete'})
        self.assertIn('Delete candidate', answer)
        self.assertNotIn("change a candidate's decision", answer)


class ChartTests(TestCase):

    def setUp(self):
        company = Company.objects.create(name='Margalla Software', email='hello@margalla.test')
        owner = CompanyUser.objects.create(company=company, email='sana@margalla.test', full_name='Sana', role='owner',
                                           password_hash='x', is_active=True)
        cv = CVRecord.objects.create(file_name='cv.pdf', parsed_json='{}')
        tomorrow = timezone.now() + timedelta(days=1)
        for days in (1, 2, 2):
            Interview.objects.create(candidate_name='C', candidate_email='c@mail.test', job_role='Engineer',
                                     cv_record=cv, available_slots_json='[]', company_user=owner, status='SCHEDULED',
                                     timezone_name='Asia/Karachi',
                                     scheduled_datetime=tomorrow + timedelta(days=days - 1))
        self.llm = mock.Mock()
        self.agent = GraphGeneratorAgent(self.llm, owner)

    def test_interviews_by_the_day_they_take_place_as_bars(self):
        self.llm.send_prompt_text.return_value = ('{"dataset": "interviews_by_date", "chart_type": "bar", '
                                                  '"title": "Interviews per day", "orientation": null}')
        result = self.agent.generate_graph('Interviews per day this week as a bar chart')
        chart = result['chart']
        self.assertEqual(chart['type'], 'bar')                      # it was always turned into a line
        self.assertEqual(sorted(chart['data'].values()), [1, 2])    # by the interview's day, not the day it was made
        self.assertEqual(chart['orientation'], 'vertical')         # days read left to right


class MessagesTests(TestCase):

    def setUp(self):
        self.company = Company.objects.create(name='Margalla Software', email='hello@margalla.test')
        CompanyModulePurchase.objects.create(company=self.company, module_name='recruitment_agent', status='active',
                                             is_complimentary=True)
        self.owner = CompanyUser.objects.create(company=self.company, email='sana@margalla.test', full_name='Sana',
                                                role='owner', password_hash='x', is_active=True)
        self.job = JobDescription.objects.create(title='Senior Frontend Engineer', description='React.',
                                                 company=self.company, company_user=self.owner)

    def call(self, view, method='get', data=None, **kwargs):
        request = getattr(APIRequestFactory(), method)('/x', data or {}, format='json')
        force_authenticate(request, user=self.owner)
        return view(request, **kwargs)

    def cv(self, name, decision='INTERVIEW'):
        return CVRecord.objects.create(file_name=f"{name.replace(' ', '_')}_CV.pdf", job_description=self.job,
                                       qualification_decision=decision,
                                       parsed_json=json.dumps({'name': name, 'email': 'x@mail.test'}))

    def test_deleting_names_the_person(self):
        cv = self.cv('Ahmed Raza')
        response = self.call(rec_views.delete_cv_record, 'delete', record_id=cv.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['message'].startswith('Ahmed Raza was deleted'), response.data['message'])

    def test_a_finished_interview_says_who_and_where_the_decision_is_set(self):
        cv = self.cv('Ahmed Raza')
        Interview.objects.create(candidate_name='Ahmed Raza', candidate_email='x@mail.test', cv_record=cv,
                                 job_role='Senior Frontend Engineer', available_slots_json='[]',
                                 company_user=self.owner, status='COMPLETED')
        response = self.call(rec_views.bulk_update_cv_records, 'post',
                             {'cv_record_ids': [cv.id], 'qualification_decision': 'HOLD'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Ahmed Raza has already had the interview', response.data['message'])
        self.assertIn('Change Decision', response.data['message'])

    def test_a_template_in_use_is_marked(self):
        self.call(wf_views.workflow_from_template, 'post', {'template_key': 'strong_candidate'})
        templates = {t['key']: t for t in self.call(wf_views.workflow_list).data['data']['templates']}
        self.assertTrue(templates['strong_candidate']['in_use'])
        self.assertFalse(templates['hold_update']['in_use'])


class JobKeywordsTests(SimpleTestCase):
    """The clean run's job came back with 'Leadership', 'Code quality' and 'Testing' among its keywords, and the
    same strong candidates scored 34 to 48 instead of 88 to 92."""

    def test_soft_skills_and_practices_are_not_scored(self):
        from recruitment_agent.agents.job_description_parser.job_description_parser_agent import (
            JobDescriptionParserAgent)
        agent = JobDescriptionParserAgent.__new__(JobDescriptionParserAgent)
        out = agent._normalize_output({
            'required_skills': ['React', 'TypeScript', 'Leadership', 'Code quality'],
            'soft_skills': ['Leadership', 'Communication'], 'practices': ['Code quality', 'Testing'],
            'keywords': ['React', 'TypeScript', 'Jest', 'Testing', 'Communication', 'Code quality']})
        self.assertEqual(out['keywords'], ['React', 'TypeScript', 'Jest'])
        self.assertEqual(out['required_skills'], ['React', 'TypeScript'])
        self.assertEqual(out['practices'], ['Code quality', 'Testing'])


class SummaryYearsTests(SimpleTestCase):
    """The clean run's AI summary said "approximately 2 years of professional experience" beside "about 5.5 years"."""

    def test_the_summary_says_the_total_from_the_dates(self):
        agent = SummarizationAgent.__new__(SummarizationAgent)
        said = agent._say_total_years('Hira is a frontend engineer with approximately 2 years of professional experience '
                                      'and 4 years of React experience.', 5.25)
        self.assertEqual(said, 'Hira is a frontend engineer with about 5.5 years of professional experience '
                               'and 4 years of React experience.')
        self.assertEqual(agent._say_total_years('Has 3+ years of experience.', 3.0), 'Has about 3 years of experience.')
        self.assertIsNone(agent._say_total_years(None, 3.0))
