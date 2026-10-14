"""When a marketer's login is switched off, the company keeps control of their campaigns.

Every campaign, lead and mailbox is stored against the login that made it, and
every Marketing screen showed only the caller's own. Switching a login off
signed it out and nothing else: the leaver's campaigns went on sending, and no
admin could open, pause or delete them. A colleague could not even connect the
company's shared mailbox, because another login already had it.
"""
from unittest import mock

from api.views import company_logins
from api.views import marketing_agent as views
from core.leavers import login_switched_off
from core.logins import user_for
from core.models import CompanyUser
from marketing_agent import leavers
from marketing_agent.models import Campaign, EmailAccount, EmailSequence
from marketing_agent.services.subscription import PayingCampaigns
from marketing_agent.tests.base import MarketingTestCase
from project_manager_agent.models import PMNotification


class MarketingLeaversTestCase(MarketingTestCase):
    """Ann is Acme's admin. Mona markets at Acme and is the one who leaves."""

    def setUp(self):
        super().setUp()
        self.mona_login = self.login(self.acme, 'mona@acme.test', 'Mona Malik', role='company_user')
        self.mona = user_for(self.mona_login)
        self.monas = self.campaign(self.mona, name='Mona spring')
        self.main = self.sequence(self.monas, steps=2)
        self.lead_m = self.lead(self.mona, 'bilal@customer.test', campaign=self.monas)

    def switch_off(self, login=None, by=None):
        login = login or self.mona_login
        CompanyUser.objects.filter(pk=login.pk).update(is_active=False)
        login.refresh_from_db()
        return login_switched_off(login, by=by)

    def status(self, campaign=None):
        return Campaign.objects.get(pk=(campaign or self.monas).pk).status


class SwitchedOffTests(MarketingLeaversTestCase):

    def test_their_running_and_scheduled_campaigns_are_paused(self):
        later = self.campaign(self.mona, name='Mona autumn', status='scheduled')
        draft = self.campaign(self.mona, name='Mona draft', status='draft')
        said = self.switch_off()
        self.assertEqual((self.status(), self.status(later), self.status(draft)), ('paused', 'paused', 'draft'))
        self.assertEqual(len(said), 1)
        self.assertIn('2 marketing campaigns of theirs were paused', said[0])

    def test_pausing_goes_through_save_so_the_sequences_stop_too(self):
        self.switch_off()
        self.assertFalse(EmailSequence.objects.get(pk=self.main.pk).is_active)

    def test_nothing_more_is_sent_and_a_colleagues_campaign_carries_on(self):
        anns = self.campaign(self.ann, name='Ann spring')
        self.sequence(anns, steps=1, name='Ann')
        self.lead(self.ann, 'sana@customer.test', campaign=anns)
        self.switch_off()
        self.assertEqual(self.run_sender(), [('sana@customer.test', 'Ann 1')])
        self.assertEqual(self.status(anns), 'active')

    def test_the_admins_are_told_which(self):
        self.switch_off()
        [alert] = PMNotification.objects.filter(company_user=self.ann_login)
        self.assertIn("Mona Malik's login was switched off", alert.title)
        self.assertIn('"Mona spring"', alert.message)

    def test_an_admin_switching_the_login_off_on_logins_and_roles_does_it(self):
        code, body = self.call(company_logins.company_login, self.ann_login, {'is_active': False}, method='patch',
                               login_id=self.mona_login.id)
        self.assertEqual(code, 200, body)
        self.assertEqual(self.status(), 'paused')
        self.assertIn('1 marketing campaign of theirs was paused', ' '.join(body['switched_off']))

    def test_switching_the_login_back_on_does_not_start_them_again(self):
        self.switch_off()
        CompanyUser.objects.filter(pk=self.mona_login.pk).update(is_active=True)
        self.assertEqual(self.status(), 'paused')

    def test_a_login_that_never_used_marketing_has_nothing_to_pause(self):
        new = self.login(self.acme, 'nadia@acme.test', 'Nadia', role='company_user')
        self.assertIsNone(new.login_user_id)
        self.assertEqual(leavers.login_switched_off(new), '')


class TheSenderTests(MarketingLeaversTestCase):
    """A campaign still marked active although its owner's login is off (missed, or from before)."""

    def test_it_is_passed_over(self):
        CompanyUser.objects.filter(pk=self.mona_login.pk).update(is_active=False)
        self.assertEqual(self.status(), 'active')
        self.assertEqual(self.run_sender(), [])
        self.assertFalse(PayingCampaigns().allows(self.monas))

    def test_while_the_login_is_on_it_sends(self):
        self.assertEqual(self.run_sender(), [('bilal@customer.test', 'Main 1')])
        self.assertTrue(PayingCampaigns().allows(self.monas))

    def test_an_owner_no_login_points_at_is_not_taken_for_a_leaver(self):
        from django.contrib.auth import get_user_model
        old = get_user_model().objects.create_user('legacy', email='legacy@nowhere.test', password='x')
        self.assertFalse(leavers.owner_switched_off(old.id))
        self.assertFalse(leavers.owner_switched_off(None))
        self.assertTrue(PayingCampaigns().allows(self.campaign(old, name='Legacy')))


class OwnersAndAdminsTests(MarketingLeaversTestCase):

    def listed(self, actor):
        code, body = self.call(views.colleagues_campaigns, actor, method='get')
        self.assertEqual(code, 200, body)
        return body['data']

    def stop(self, actor, campaign):
        return self.call(views.stop_colleagues_campaign, actor, campaign_id=campaign.id)

    def test_an_admin_is_shown_every_colleagues_campaign_and_whose_it_is(self):
        self.campaign(self.ann, name='Ann own')
        data = self.listed(self.ann_login)
        self.assertTrue(data['can_manage'])
        [row] = data['campaigns']
        self.assertEqual((row['name'], row['status'], row['leads'], row['owner']['name'], row['owner']['is_active']),
                         ('Mona spring', 'active', 1, 'Mona Malik', True))

    def test_a_login_that_has_been_switched_off_is_still_listed(self):
        self.switch_off()
        [row] = self.listed(self.ann_login)['campaigns']
        self.assertEqual((row['status'], row['owner']['is_active']), ('paused', False))

    def test_someone_who_does_not_run_the_company_is_shown_nothing(self):
        self.campaign(self.ann, name='Ann own')
        self.assertEqual(self.listed(self.mona_login), {'can_manage': False, 'campaigns': []})
        code, _ = self.stop(self.mona_login, Campaign.objects.get(name='Ann own'))
        self.assertEqual(code, 403)

    def test_another_companys_campaigns_are_never_listed_or_stopped(self):
        theirs = self.campaign(self.rita, name='Rival offer')
        self.assertEqual([row['name'] for row in self.listed(self.ann_login)['campaigns']], ['Mona spring'])
        code, _ = self.stop(self.ann_login, theirs)
        self.assertEqual((code, self.status(theirs)), (404, 'active'))

    def test_an_admin_can_stop_a_colleagues_running_campaign(self):
        code, body = self.stop(self.ann_login, self.monas)
        self.assertEqual((code, body['data']['status'], self.status()), (200, 'paused', 'paused'))
        self.assertFalse(EmailSequence.objects.get(pk=self.main.pk).is_active)
        self.assertEqual(self.run_sender(), [])

    def test_stopping_one_that_is_not_running_changes_nothing(self):
        Campaign.objects.filter(pk=self.monas.pk).update(status='completed')
        code, body = self.stop(self.ann_login, self.monas)
        self.assertEqual((code, self.status()), (200, 'completed'))

    def test_their_own_campaign_is_not_among_the_colleagues(self):
        own = self.campaign(self.ann, name='Ann own')
        self.assertEqual(self.stop(self.ann_login, own)[0], 404)


class SharedMailboxTests(MarketingLeaversTestCase):
    """One mailbox per company was being applied as one mailbox per login."""

    BODY = {'name': 'Shared', 'email': 'Sales@Acme.test', 'smtp_host': 'smtp.acme.test', 'smtp_password': 'synthetic',
            'smtp_username': 'sales@acme.test'}

    def connect(self, actor):
        with mock.patch.object(views, 'verify_imap_credentials', return_value=(True, ''), create=True), \
                mock.patch('threading.Thread'):
            return self.call(views.create_email_account, actor, dict(self.BODY))

    def test_a_colleague_in_the_same_company_can_connect_it_too(self):
        self.mailbox(self.mona, 'sales@acme.test')
        code, body = self.connect(self.ann_login)
        self.assertIn(code, (200, 201), body)
        self.assertEqual(EmailAccount.objects.filter(email__iexact='sales@acme.test').count(), 2)

    def test_another_company_still_cannot(self):
        self.mailbox(self.mona, 'sales@acme.test')
        code, body = self.connect(self.rita_login)
        self.assertEqual((code, body['error']), (409, 'email_already_used_by_another_company'))
        self.assertEqual(EmailAccount.objects.filter(email__iexact='sales@acme.test').count(), 1)

    def test_same_company_means_the_same_company(self):
        self.assertTrue(leavers.same_company(self.mona, self.ann))
        self.assertTrue(leavers.same_company(self.ann, self.ann))
        self.assertFalse(leavers.same_company(self.mona, self.rita))
        self.assertFalse(leavers.same_company(None, self.ann))
