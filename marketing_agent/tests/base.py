"""What the Marketing tests share: two companies, a login in each, and the things a campaign is made of."""
import json

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from core.logins import user_for
from core.models import Company, CompanyModulePurchase, CompanyUser
from marketing_agent.models import (Campaign, CampaignLead, EmailAccount, EmailSendHistory, EmailSequence,
                                    EmailSequenceStep, EmailTemplate, Lead)


class MarketingTestCase(TestCase):
    """Ann runs Marketing at Acme. Rita does the same at Rival, a different company."""

    def setUp(self):
        self.acme = self.company('Acme')
        self.rival = self.company('Rival')
        self.ann_login = self.login(self.acme, 'ann@acme.test', 'Ann Ahmed')
        self.rita_login = self.login(self.rival, 'rita@rival.test', 'Rita Raza')
        self.ann = user_for(self.ann_login)
        self.rita = user_for(self.rita_login)

    def company(self, name):
        company = Company.objects.create(name=name, email=f'{name.lower()}@test.local')
        CompanyModulePurchase.objects.create(company=company, module_name='marketing_agent', status='active',
                                             is_complimentary=True)
        return company

    def login(self, company, email, name, role='admin'):
        return CompanyUser.objects.create(company=company, email=email, full_name=name, role=role,
                                          password_hash='x', is_active=True)

    def mailbox(self, owner, email, **more):
        fields = dict(name=email, email=email, smtp_host='smtp.test', smtp_username=email, smtp_password='not-a-real-one',
                      is_active=True, is_marketing_account=True)
        fields.update(more)
        return EmailAccount.objects.create(owner=owner, **fields)

    def campaign(self, owner, name='Spring offer', status='active', **more):
        return Campaign.objects.create(owner=owner, name=name, status=status, **more)

    def lead(self, owner, email, campaign=None, **more):
        lead = Lead.objects.create(owner=owner, email=email, **more)
        if campaign is not None:
            CampaignLead.objects.create(campaign=campaign, lead=lead)
        return lead

    def template(self, campaign, name='Hello', subject='Hello {{first_name}}', **more):
        fields = dict(html_content='<p>Hi</p>', text_content='Hi')
        fields.update(more)
        return EmailTemplate.objects.create(campaign=campaign, name=name, subject=subject, **fields)

    def sequence(self, campaign, steps=1, **more):
        fields = dict(name='Main', is_active=True)
        fields.update(more)
        sequence = EmailSequence.objects.create(campaign=campaign, **fields)
        for order in range(1, steps + 1):
            EmailSequenceStep.objects.create(
                sequence=sequence, step_order=order, delay_days=0,
                template=self.template(campaign, name=f'{sequence.name} step {order}',
                                       subject=f'{sequence.name} {order}'))
        return sequence

    def run_sender(self, *outcomes):
        """One run of the scheduled sequence sender, with nothing really sent.

        `outcomes` are what each send in turn reports (True, False or 'blocked');
        any send beyond them succeeds. Returns who was sent what:
        [(lead email, template subject), ...]."""
        from io import StringIO
        from unittest import mock
        from django.core.management import call_command
        from marketing_agent.management.commands import send_sequence_emails as sender

        answers = list(outcomes)
        sent = []

        def send_email(template, lead, campaign, **more):
            sent.append((lead.email, template.subject))
            outcome = answers.pop(0) if answers else True
            if outcome == 'blocked':
                return {'success': False, 'blocked': True}
            # The row the real service leaves behind; reply matching reads these.
            EmailSendHistory.objects.create(
                campaign=campaign, lead=lead, email_template=template, subject=template.subject,
                recipient_email=lead.email, status='sent' if outcome else 'failed',
                sent_at=timezone.now() if outcome else None)
            return {'success': True} if outcome else {'success': False, 'error': 'mailbox said no'}

        with mock.patch.object(sender.email_service, 'send_email', side_effect=send_email):
            call_command('send_sequence_emails', stdout=StringIO())
        return sent

    def call(self, view, actor, data=None, method='post', **kwargs):
        request = getattr(APIRequestFactory(), method)('/', data or {}, format='json')
        force_authenticate(request, user=actor)
        response = view(request, **kwargs)
        if hasattr(response, 'render'):
            response.render()
        return response.status_code, (json.loads(response.content) if response.content else {})
