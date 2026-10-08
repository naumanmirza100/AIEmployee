"""One user record for each dashboard login, found the same way by every agent.

Marketing and Reply Draft used to look the record up by email address. Opening
Marketing first and Frontline or HR afterwards left two records with one
address, and every Reply Draft page then failed for that login. And one address
used as a dashboard login in two companies shared a single record: one set of
campaigns, leads, mail accounts and replies between them.
"""
from importlib import import_module

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from core import logins
from core.models import Company, CompanyUser, UserProfile
from marketing_agent.models import Campaign, EmailAccount, Lead
from reply_draft_agent.models import InboxEmail, ReplyDraft

User = get_user_model()
move = import_module('marketing_agent.migrations.0039_one_user_record_per_login').link_and_move


def company(name):
    return Company.objects.create(name=name, email=f'{name.lower()}@test.local')


def login(c, email='dana@test.local', **fields):
    return CompanyUser.objects.create(company=c, email=email, full_name='Dana Scott', role='admin',
                                      password_hash='x', is_active=True, **fields)


def old_marketing_record(cu):
    """The record Marketing made for a login it met first: found again by its email address."""
    return User.objects.create_user(username=f'company_user_{cu.id}_{cu.email}', email=cu.email, password=None)


class UserForTests(TestCase):

    def setUp(self):
        self.acme, self.rival = company('Acme'), company('Rival')

    def test_a_login_gets_one_record_and_keeps_it(self):
        dana = login(self.acme)
        user = logins.user_for(dana)
        self.assertEqual((user.username, user.email, user.first_name, user.last_name),
                         (f'company_user_{dana.id}', 'dana@test.local', 'Dana', 'Scott'))
        self.assertFalse(user.has_usable_password())
        dana.refresh_from_db()
        self.assertEqual(dana.login_user_id, user.id)                    # the link is kept
        self.assertEqual(logins.user_for(CompanyUser.objects.get(pk=dana.pk)).id, user.id)
        self.assertEqual(User.objects.count(), 1)
        self.assertIsNone(logins.user_for(None))

    def test_the_same_address_in_two_companies_is_two_records(self):
        ours, theirs = logins.user_for(login(self.acme)), logins.user_for(login(self.rival))
        self.assertNotEqual(ours.id, theirs.id)

    def test_it_is_never_found_by_email(self):
        from api.views import frontline_agent, hr_agent, marketing_agent, reply_draft_agent
        stranger = User.objects.create_user(username='someone_else', email='dana@test.local', password=None)
        for find in (marketing_agent._get_or_create_user_for_company_user,
                     reply_draft_agent._get_or_create_user_for_company_user,
                     frontline_agent._get_or_create_user_for_company_user,
                     hr_agent._hr_get_or_create_user_for_company_user, logins.user_for):
            CompanyUser.objects.all().delete()
            self.assertNotEqual(find(login(self.acme)).id, stranger.id, find.__module__)

    def test_a_record_already_made_under_the_logins_name_is_taken_up(self):
        dana = login(self.acme)
        made = User.objects.create_user(username=f'company_user_{dana.id}', email=dana.email, password=None)
        self.assertEqual(logins.user_for(dana).id, made.id)
        dana.refresh_from_db()
        self.assertEqual(dana.login_user_id, made.id)

    def test_every_agent_resolves_the_same_record(self):
        from api.views import frontline_agent, hr_agent, marketing_agent, reply_draft_agent
        dana = login(self.acme)
        # The order that used to break: Marketing first, then the rest.
        found = [marketing_agent._get_or_create_user_for_company_user(dana),
                 frontline_agent._get_or_create_user_for_company_user(dana),
                 hr_agent._hr_get_or_create_user_for_company_user(dana),
                 reply_draft_agent._get_or_create_user_for_company_user(dana)]
        self.assertEqual(len({u.id for u in found}), 1)
        self.assertEqual(User.objects.filter(email=dana.email).count(), 1)

    def test_reply_draft_no_longer_fails_when_two_records_share_an_address(self):
        from api.views import reply_draft_agent
        dana = login(self.acme)
        old_marketing_record(dana)
        linked = logins.user_for(dana)                                    # what Frontline or HR then made
        self.assertEqual(User.objects.filter(email=dana.email).count(), 2)
        self.assertEqual(reply_draft_agent._get_or_create_user_for_company_user(dana).id, linked.id)

    def test_reply_draft_sees_its_own_companys_logins_only(self):
        from api.views import reply_draft_agent
        dana, eli = login(self.acme), login(self.acme, 'eli@test.local')
        gone = login(self.acme, 'gone@test.local', )
        theirs = login(self.rival)                                        # same address, another company
        ids = {u: logins.user_for(u).id for u in (dana, eli, gone, theirs)}
        CompanyUser.objects.filter(pk=gone.pk).update(is_active=False)
        self.assertEqual(set(reply_draft_agent._company_bridge_user_ids(dana)), {ids[dana], ids[eli]})
        # A colleague who has not used any agent yet has no record; the caller always has.
        fresh = login(self.acme, 'fresh@test.local')
        self.assertIn(logins.user_for(fresh).id, reply_draft_agent._company_bridge_user_ids(fresh))


class CompanyForTests(TestCase):

    def setUp(self):
        self.acme, self.rival = company('Acme'), company('Rival')

    def test_the_linked_login_says_which_company(self):
        dana, theirs = login(self.acme), login(self.rival)
        self.assertEqual(logins.company_id_for(logins.user_for(dana)), self.acme.id)
        self.assertEqual(logins.company_id_for(logins.user_for(theirs)), self.rival.id)
        self.assertIsNone(logins.company_id_for(None))

    def test_an_older_record_is_found_by_email_only_when_one_company_has_it(self):
        dana = login(self.acme)
        unlinked = old_marketing_record(dana)
        self.assertEqual(logins.company_id_for(unlinked), self.acme.id)
        login(self.rival)                                                 # now two companies use the address
        self.assertIsNone(logins.company_id_for(unlinked))               # a guess is worse than no answer
        self.assertIsNone(logins.company_id_for(User.objects.create_user(username='nobody', password=None)))

    def test_marketing_and_reply_draft_ask_the_same_question(self):
        from marketing_agent.services.reply_processor import _company_id_for_campaign
        from marketing_agent.services.subscription import company_id_for_owner
        from reply_draft_agent.permissions import _resolve_company
        dana, theirs = login(self.acme), login(self.rival)
        ours = logins.user_for(dana)
        logins.user_for(theirs)
        campaign = Campaign.objects.create(name='Spring', owner=ours)
        self.assertEqual(_company_id_for_campaign(campaign), self.acme.id)
        self.assertEqual(company_id_for_owner(ours), self.acme.id)
        self.assertEqual(_resolve_company(ours), self.acme)


class DataMoveTests(TestCase):
    """The one-off move: what was stored against the email-matched record follows the login."""

    def setUp(self):
        self.acme, self.rival = company('Acme'), company('Rival')

    def holdings(self, user):
        """(campaigns, leads, mail accounts, inbox mail and drafts) stored against a record."""
        return (Campaign.objects.filter(owner=user).count(), Lead.objects.filter(owner=user).count(),
                EmailAccount.objects.filter(owner=user).count(),
                InboxEmail.objects.filter(owner=user).count() + ReplyDraft.objects.filter(owner=user).count())

    def give(self, user, lead='lead@prospect.example'):
        Campaign.objects.create(name='Spring', owner=user)
        Lead.objects.create(email=lead, owner=user)
        account = EmailAccount.objects.create(
            name='Sales', email='sales@acme.example', owner=user, smtp_host='smtp.example',
            smtp_port=587, smtp_username='sales@acme.example', smtp_password='x')
        InboxEmail.objects.create(owner=user, email_account=account, message_id='<1@prospect.example>',
                                  from_email='lead@prospect.example')
        ReplyDraft.objects.create(owner=user, draft_subject='Re: hello', draft_body='Thanks for writing.')

    def test_a_login_marketing_met_first_is_linked_to_the_record_it_has_been_using(self):
        dana = login(self.acme)
        used = old_marketing_record(dana)
        self.give(used)
        move(apps, None)
        dana.refresh_from_db()
        self.assertEqual(dana.login_user_id, used.id)                     # linked; nothing had to move
        self.assertEqual(self.holdings(used), (1, 1, 1, 2))
        self.assertEqual(User.objects.count(), 1)

    def test_what_sat_on_the_old_record_moves_to_the_linked_one(self):
        dana = login(self.acme)
        used = old_marketing_record(dana)                                  # Marketing first...
        self.give(used)
        linked = logins.user_for(dana)                                     # ...then Frontline or HR
        move(apps, None)
        self.assertEqual((self.holdings(used), self.holdings(linked)), ((0, 0, 0, 0), (1, 1, 1, 2)))
        move(apps, None)                                                   # safe to run again
        self.assertEqual(self.holdings(linked), (1, 1, 1, 2))

    def test_a_lead_or_mailbox_the_new_record_already_has_stays_put(self):
        dana = login(self.acme)
        used = old_marketing_record(dana)
        self.give(used)
        linked = logins.user_for(dana)
        Lead.objects.create(email='lead@prospect.example', owner=linked)   # the same lead, already there
        move(apps, None)
        self.assertEqual((self.holdings(used), self.holdings(linked)), ((0, 1, 0, 0), (1, 1, 1, 2)))

    def test_an_address_two_companies_share_is_left_for_a_person_to_split(self):
        dana, theirs = login(self.acme), login(self.rival)
        used = old_marketing_record(dana)                                  # both companies wrote here
        self.give(used)
        with self.assertLogs('marketing_agent.migrations', level='WARNING') as logged:
            move(apps, None)
        self.assertIn('split it by hand', logged.output[0])
        # An empty shared record is nothing to split, and nothing to report.
        login(self.acme, 'eli@test.local'), login(self.rival, 'eli@test.local')
        User.objects.create_user(username='eli_somewhere', email='eli@test.local', password=None)
        with self.assertLogs('marketing_agent.migrations', level='WARNING') as again:
            move(apps, None)
        self.assertEqual(len(again.output), 1)
        self.assertEqual(self.holdings(used), (1, 1, 1, 2))
        for cu in (dana, theirs):
            cu.refresh_from_db()
            self.assertIsNone(cu.login_user_id)

    def test_a_record_that_is_another_companys_employee_is_not_taken_over(self):
        dana = login(self.acme)
        employee = User.objects.create_user(username='dana_at_rival', email=dana.email, password='x')
        UserProfile.objects.update_or_create(user=employee, defaults={'company': self.rival, 'role': 'team_member'})
        move(apps, None)
        dana.refresh_from_db()
        self.assertIsNone(dana.login_user_id)                              # empty: nothing to do yet
        self.give(employee)                                                # what Dana's Marketing stored there
        move(apps, None)
        dana.refresh_from_db()
        self.assertNotEqual(dana.login_user_id, employee.id)
        self.assertEqual((dana.login_user.username, self.holdings(dana.login_user), self.holdings(employee)),
                         (f'company_user_{dana.id}', (1, 1, 1, 2), (0, 0, 0, 0)))

    def test_an_employee_login_of_the_same_company_is_the_same_person(self):
        dana = login(self.acme)
        employee = User.objects.create_user(username='dana_employee', email=dana.email, password='x')
        UserProfile.objects.update_or_create(user=employee, defaults={'company': self.acme, 'role': 'team_member'})
        move(apps, None)
        dana.refresh_from_db()
        self.assertEqual(dana.login_user_id, employee.id)
        self.assertEqual(logins.user_for(dana).id, employee.id)            # and stays that record

    def test_another_logins_own_record_keeps_what_it_holds(self):
        # Eli took the address Dana's record still carries. What that record holds is Dana's.
        dana = login(self.acme)
        danas = logins.user_for(dana)
        self.give(danas)
        CompanyUser.objects.filter(pk=dana.pk).update(email='dana.scott@test.local')
        eli = login(self.acme, 'dana@test.local')
        move(apps, None)
        eli.refresh_from_db()
        self.assertIsNone(eli.login_user_id)                               # not handed Dana's record
        elis = logins.user_for(eli)
        move(apps, None)
        self.assertEqual((self.holdings(danas), self.holdings(elis)), ((1, 1, 1, 2), (0, 0, 0, 0)))
