"""The Company Assistant reads every agent (CO-18, phase 2, 2 Nov 2026), each by that agent's own rule.

Recruitment, Operations, Reply Draft and CRM Sync are the company's; Executive Meeting shows a login only what it
organises or is invited to; Marketing a login's own campaigns, an owner's or admin's the company's; AI SDR a login's
own. No test reaches an AI or a search service.
"""
import json
from datetime import timedelta
from unittest import mock

from django.utils import timezone

from core.assistant import engine
from core.assistant import lookups as L
from core.assistant import more_lookups as M
from core.logins import user_for
from core.models import Agent
from hr_agent.tests.base import HRTestCase

ALL = ('project_manager_agent', 'frontline_agent', 'recruitment_agent', 'exec_meeting_agent', 'operations_agent',
       'marketing_agent', 'ai_sdr_agent', 'reply_draft_agent', 'crm_sync_agent')


def text(facts):
    return ' '.join(f.text for f in facts)


class AllAgentsTestCase(HRTestCase):

    def setUp(self):
        super().setUp()
        Agent.objects.get_or_create(slug='company_assistant', defaults={'name': 'Company Assistant',
                                                                        'is_purchasable': False})
        for module in ALL:
            self.buy_module(self.company, module)
        self.buy_module(self.rival, 'recruitment_agent')
        for cu in (self.admin, self.member, self.rival_admin):
            cu.refresh_from_db()

    def ctx(self, company_user):
        return engine.context_for(company_user)


class WhatTheyRead(AllAgentsTestCase):

    def test_every_agent_has_lookups_and_documents_need_an_agent_with_documents(self):
        names = {lk.name for lk in L.available(self.ctx(self.admin).modules)}
        for name in ('jobs', 'interviews', 'exec_meetings', 'ops_deadlines', 'campaigns', 'sdr_leads', 'inbox',
                     'crm_status', 'documents', 'week'):
            self.assertIn(name, names)
        only_recruitment = {lk.name for lk in L.available({'recruitment_agent'})}
        self.assertIn('week', only_recruitment)
        self.assertNotIn('documents', only_recruitment)
        self.assertNotIn('campaigns', only_recruitment)
        self.assertEqual(engine.unread(self.ctx(self.admin)), [])

    def test_recruitment_is_the_companys_and_never_another_companys(self):
        from recruitment_agent.models import CVRecord, JobDescription
        job = JobDescription.objects.create(title='React Developer', description='x', company=self.company,
                                            company_user=self.member)
        CVRecord.objects.create(file_name='a.pdf', parsed_json=json.dumps({'name': 'Areeba Nadeem'}), job_description=job,
                                role_fit_score=91, qualification_decision='INTERVIEW')
        JobDescription.objects.create(title='Rival secret job', description='x', company=self.rival,
                                      company_user=self.rival_admin)
        seen = text(M.jobs(self.ctx(self.admin), {}))           # a colleague's job: the company's
        self.assertIn('React Developer', seen)
        self.assertIn('interview 1', seen)
        self.assertNotIn('Rival secret job', seen)
        self.assertIn('Areeba Nadeem', text(M.candidates(self.ctx(self.admin), {'job': 'react'})))

    def test_executive_meetings_only_those_organised_or_invited_to(self):
        from meeting_agent.models import ExecutiveMeeting, ExecutiveMeetingParticipant
        when = timezone.now() + timedelta(days=1)
        mine = ExecutiveMeeting.objects.create(organizer=self.admin, title='Board prep', scheduled_at=when)
        ExecutiveMeetingParticipant.objects.create(meeting=mine, company_user=self.member)
        ExecutiveMeeting.objects.create(organizer=self.admin, title='Salary review', scheduled_at=when)
        member_sees = text(M.exec_meetings(self.ctx(self.member), {}))
        self.assertIn('Board prep', member_sees)
        self.assertNotIn('Salary review', member_sees)
        self.assertIn('Salary review', text(M.exec_meetings(self.ctx(self.admin), {})))

    def test_marketing_own_campaigns_and_an_admin_the_companys(self):
        from marketing_agent.models import Campaign
        Campaign.objects.create(name='Mo spring push', owner=user_for(self.member))
        Campaign.objects.create(name='Dana winter push', owner=user_for(self.admin))
        member_sees = text(M.campaigns(self.ctx(self.member), {}))
        self.assertIn('Mo spring push', member_sees)
        self.assertNotIn('Dana winter push', member_sees)
        admin_sees = text(M.campaigns(self.ctx(self.admin), {}))
        self.assertIn('Mo spring push', admin_sees)
        self.assertIn('Dana winter push', admin_sees)

    def test_ai_sdr_leads_are_the_logins_own(self):
        from ai_sdr_agent.models import SDRLead
        SDRLead.objects.create(company_user=self.member, full_name='Kiran Shah', company_name='Capital Dental')
        SDRLead.objects.create(company_user=self.admin, full_name='Rabia Anwar', company_name='Margalla Smiles')
        member_sees = text(M.sdr_leads(self.ctx(self.member), {}))
        self.assertIn('Kiran Shah', member_sees)
        self.assertNotIn('Rabia Anwar', member_sees)

    def test_crm_status_says_what_is_wrong(self):
        from crm_sync_agent.models import CRMIntegration
        CRMIntegration.objects.create(company=self.company, provider='hubspot', last_ping_ok=True,
                                      last_ping_at=timezone.now(), missing_permission='sales-email-read')
        seen = text(M.crm_status(self.ctx(self.member), {}))
        self.assertIn('HubSpot: connected', seen)
        self.assertIn('sales-email-read', seen)

    def test_documents_are_searched_as_each_agent_shows_them_to_this_login(self):
        with mock.patch('core.HR_agent.services.HRKnowledgeService.search_knowledge',
                        return_value=[{'title': 'Leave policy', 'content': 'Half days count as 0.5.'}]) as hr, \
                mock.patch('core.Frontline_agent.services.KnowledgeService.search_knowledge',
                           return_value={'results': [{'title': 'Refunds', 'content': 'Within 14 days.'}]}) as fl, \
                mock.patch('operations_agent.agents.knowledge_qa_agent.OperationsKnowledgeQAAgent._build_context',
                           return_value=('', [], False)):
            seen = text(M.documents(self.ctx(self.member), {'query': 'half days'}))
        self.assertIn('Half days count as 0.5', seen)
        self.assertIn('Within 14 days', seen)
        self.assertEqual(hr.call_args.kwargs['asker_role'], 'employee')      # HR's own rule for a plain login
        self.assertEqual(fl.call_args.kwargs['company_user_id'], self.member.pk)

    def test_the_week_has_a_line_for_each_agent_the_company_has(self):
        lines = text(M.week(self.ctx(self.admin), {}))
        for agent in ('Project Manager:', 'Frontline:', 'HR:', 'Recruitment:', 'Executive Meeting:', 'Marketing:',
                      'AI SDR:', 'Operations:', 'CRM Sync:'):
            self.assertIn(agent, lines)
        rival_week = text(M.week(self.ctx(self.rival_admin), {}))     # Rival has HR and Recruitment only
        self.assertIn('Recruitment:', rival_week)
        self.assertNotIn('Marketing:', rival_week)
