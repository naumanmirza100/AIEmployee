"""The company's reply mailbox does not vanish with the person who connected it.

The mailbox, its mail and its drafts belong to the one login that connected it,
and every screen finds the mailbox through the company's active logins. When
that login was switched off, everyone else saw 'no mailbox connected' and an
empty inbox, could not connect the same mailbox again because the old
connection still existed, and could not disconnect it either.
"""
import importlib

from django.apps import apps
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from api.views import company_logins
from api.views import reply_draft_agent as views
from core.leavers import login_switched_off
from core.logins import user_for
from core.models import Company, CompanyModulePurchase, CompanyUser
from marketing_agent.models import EmailAccount
from reply_draft_agent import leavers
from reply_draft_agent.models import InboxEmail, ReplyDraft


class ReplyMailboxTestCase(TestCase):
    """Omar connected Acme's reply mailbox. Dana is an admin there; Mo is not."""

    def setUp(self):
        self.acme = Company.objects.create(name='Acme', email='acme@test.local')
        CompanyModulePurchase.objects.create(company=self.acme, module_name='reply_draft_agent', status='active',
                                             is_complimentary=True)
        self.dana = self.login('dana@acme.test', 'Dana Malik', 'admin')
        self.omar = self.login('omar@acme.test', 'Omar Sheikh', 'company_user')
        self.mo = self.login('mo@acme.test', 'Mo Khan', 'company_user')
        self.mailbox = self.reply_mailbox(self.omar, 'support@acme.test')
        self.mail = InboxEmail.objects.create(
            owner=user_for(self.omar), email_account=self.mailbox, message_id='<m1@customer.test>',
            from_email='bilal@customer.test', subject='A question', body='Hello', received_at=timezone.now())
        self.draft = ReplyDraft.objects.create(owner=user_for(self.omar), inbox_email=self.mail,
                                               email_account=self.mailbox, draft_subject='Re: A question',
                                               draft_body='Hello Bilal')

    def login(self, email, name, role, company=None, active=True):
        return CompanyUser.objects.create(company=company or self.acme, email=email, full_name=name, role=role,
                                          password_hash='x', is_active=active)

    def reply_mailbox(self, login, address, **more):
        fields = dict(name=address, email=address, smtp_host='smtp.acme.test', smtp_username=address,
                      smtp_password='synthetic', imap_host='imap.acme.test', imap_username=address,
                      imap_password='synthetic', enable_imap_sync=True, is_reply_agent_account=True,
                      is_marketing_account=False)
        fields.update(more)
        return EmailAccount.objects.create(owner=user_for(login), **fields)

    def switch_off(self, login=None, by=None):
        login = login or self.omar
        CompanyUser.objects.filter(pk=login.pk).update(is_active=False)
        login.refresh_from_db()
        return login_switched_off(login, by=by)

    def seen_by(self, login):
        """The reply mailboxes this login's Reply Draft screen shows."""
        request = APIRequestFactory().get('/x')
        force_authenticate(request, user=login)
        response = views.list_sync_accounts(request)
        self.assertEqual(response.status_code, 200, response.data)
        payload = response.data.get('data', response.data)
        rows = payload.get('accounts', payload) if isinstance(payload, dict) else payload
        return [row['email'] for row in rows]

    def owner_of(self, row):
        return type(row).objects.get(pk=row.pk).owner_id


class HandedOnTests(ReplyMailboxTestCase):

    def test_before_anyone_leaves_every_colleague_sees_the_mailbox(self):
        self.assertEqual(self.seen_by(self.dana), ['support@acme.test'])
        self.assertEqual(self.seen_by(self.mo), ['support@acme.test'])

    def test_when_the_login_that_connected_it_is_switched_off_it_goes_to_the_admin_who_did_it(self):
        said = self.switch_off(by=self.dana)
        dana = user_for(self.dana).id
        self.assertEqual((self.owner_of(self.mailbox), self.owner_of(self.mail), self.owner_of(self.draft)),
                         (dana, dana, dana))
        self.assertTrue(EmailAccount.objects.get(pk=self.mailbox.pk).is_reply_agent_account)
        self.assertIn('support@acme.test', ' '.join(said))
        self.assertIn('now belongs to Dana Malik', ' '.join(said))

    def test_and_everyone_still_sees_it(self):
        self.switch_off(by=self.dana)
        self.assertEqual(self.seen_by(self.dana), ['support@acme.test'])
        self.assertEqual(self.seen_by(self.mo), ['support@acme.test'])

    def test_without_this_it_would_have_vanished(self):
        # What used to happen, to show the test above means something.
        CompanyUser.objects.filter(pk=self.omar.pk).update(is_active=False)
        self.assertEqual(self.seen_by(self.dana), [])

    def test_hr_offboarding_gives_it_to_an_owner_or_admin(self):
        owner = self.login('zara@acme.test', 'Zara Owner', 'owner')
        self.switch_off()                                   # nobody pressed a button: no `by`
        self.assertEqual(self.owner_of(self.mailbox), user_for(owner).id)

    def test_an_admin_is_preferred_to_an_ordinary_login(self):
        self.switch_off()
        self.assertEqual(self.owner_of(self.mailbox), user_for(self.dana).id)

    def test_with_nobody_else_in_the_company_it_stays_and_says_so(self):
        CompanyUser.objects.filter(company=self.acme).exclude(pk=self.omar.pk).update(is_active=False)
        said = ' '.join(self.switch_off())
        self.assertEqual(self.owner_of(self.mailbox), user_for(self.omar).id)
        self.assertIn('no other login to give it to', said)

    def test_it_never_goes_to_another_company(self):
        rival = Company.objects.create(name='Rival', email='rival@test.local')
        rita = self.login('rita@rival.test', 'Rita', 'admin', company=rival)
        CompanyUser.objects.filter(company=self.acme).exclude(pk=self.omar.pk).update(is_active=False)
        self.switch_off(by=rita)
        self.assertEqual(self.owner_of(self.mailbox), user_for(self.omar).id)

    def test_a_mailbox_they_only_send_marketing_from_is_not_handed_on(self):
        # Marketing's mailboxes go with its campaigns, which are paused, not given away.
        sending = self.reply_mailbox(self.omar, 'offers@acme.test', is_reply_agent_account=False,
                                     is_marketing_account=True)
        said = ' '.join(self.switch_off(by=self.dana))
        self.assertEqual(self.owner_of(sending), user_for(self.omar).id)
        self.assertNotIn('offers@acme.test', said)
        self.assertEqual(self.owner_of(self.mailbox), user_for(self.dana).id)       # the reply mailbox still went

    def test_a_login_with_no_reply_mailbox_has_nothing_to_hand_on(self):
        self.assertEqual(leavers.login_switched_off(self.mo), '')
        self.assertEqual(self.owner_of(self.mailbox), user_for(self.omar).id)

    def test_through_the_logins_and_roles_screen(self):
        request = APIRequestFactory().patch('/x', {'is_active': False}, format='json')
        force_authenticate(request, user=self.dana)
        response = company_logins.company_login(request, login_id=self.omar.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.owner_of(self.mailbox), user_for(self.dana).id)
        self.assertIn('support@acme.test', ' '.join(response.data['switched_off']))


class AlreadyConnectedForSendingTests(ReplyMailboxTestCase):
    """The new holder may have the same address connected already, for Marketing."""

    def setUp(self):
        super().setUp()
        self.danas = EmailAccount.objects.create(
            owner=user_for(self.dana), name='Support', email='Support@acme.test', smtp_host='smtp.acme.test',
            smtp_username='support@acme.test', smtp_password='synthetic', is_marketing_account=True)

    def test_their_own_row_becomes_the_reply_mailbox_and_takes_the_inbox_settings(self):
        self.switch_off(by=self.dana)
        danas = EmailAccount.objects.get(pk=self.danas.pk)
        self.assertEqual((danas.is_reply_agent_account, danas.is_marketing_account, danas.imap_host,
                          danas.enable_imap_sync), (True, True, 'imap.acme.test', True))
        self.assertFalse(EmailAccount.objects.get(pk=self.mailbox.pk).is_reply_agent_account)
        self.assertEqual(EmailAccount.objects.filter(is_reply_agent_account=True).count(), 1)

    def test_the_mail_and_the_drafts_follow_to_that_row(self):
        self.switch_off(by=self.dana)
        mail, draft = InboxEmail.objects.get(pk=self.mail.pk), ReplyDraft.objects.get(pk=self.draft.pk)
        dana = user_for(self.dana).id
        self.assertEqual((mail.email_account_id, mail.owner_id), (self.danas.pk, dana))
        self.assertEqual((draft.email_account_id, draft.owner_id), (self.danas.pk, dana))
        self.assertEqual(self.seen_by(self.mo), ['Support@acme.test'])

    def test_a_message_both_rows_already_hold_is_not_doubled(self):
        InboxEmail.objects.create(owner=user_for(self.dana), email_account=self.danas, message_id='<m1@customer.test>',
                                  from_email='bilal@customer.test', subject='A question', received_at=timezone.now())
        self.switch_off(by=self.dana)
        self.assertEqual(InboxEmail.objects.filter(email_account=self.danas, message_id='<m1@customer.test>').count(),
                         1)
        dana = user_for(self.dana).id
        self.assertEqual((self.owner_of(self.mail), self.owner_of(self.draft)), (dana, dana))     # and the rest still moved


class StrandedBeforeThisTests(ReplyMailboxTestCase):
    """The one-off step for mailboxes whose login was switched off earlier."""

    def rescue(self):
        migration = importlib.import_module('reply_draft_agent.migrations.0014_rescue_stranded_reply_mailboxes')
        migration.rescue(apps, None)
        migration.rescue(apps, None)                        # and it can run again

    def test_a_stranded_mailbox_is_given_to_an_active_admin_with_its_mail(self):
        CompanyUser.objects.filter(pk=self.omar.pk).update(is_active=False)
        dana = user_for(self.dana).id                       # Dana has used the product: she has a user record
        self.rescue()
        self.assertEqual((self.owner_of(self.mailbox), self.owner_of(self.mail), self.owner_of(self.draft)),
                         (dana, dana, dana))
        self.assertEqual(self.seen_by(self.mo), ['support@acme.test'])

    def test_it_is_not_given_to_another_login_that_is_switched_off(self):
        gone = self.login('zara@acme.test', 'Zara Owner', 'owner', active=False)     # an owner, but she left too
        user_for(gone)
        CompanyUser.objects.filter(pk=self.omar.pk).update(is_active=False)
        dana = user_for(self.dana).id
        self.rescue()
        self.assertEqual(self.owner_of(self.mailbox), dana)

    def test_a_mailbox_whose_login_is_still_on_is_left_alone(self):
        user_for(self.dana)
        self.rescue()
        self.assertEqual(self.owner_of(self.mailbox), user_for(self.omar).id)

    def test_a_company_with_nobody_to_take_it_is_left_as_it_is(self):
        CompanyUser.objects.filter(company=self.acme).update(is_active=False)
        self.rescue()
        self.assertEqual(self.owner_of(self.mailbox), user_for(self.omar).id)
