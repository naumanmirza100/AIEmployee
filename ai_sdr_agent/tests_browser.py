"""The AI SDR's screens in a real browser: headless Chromium signs in through the login page and uses the screens,
against the throwaway test database (see browser_testing.py). They catch what the API tests cannot: a screen that no
longer loads, a form that sends the wrong thing, a message that never shows.

They need Node (to build the screens once) and Playwright's Chromium; without them they skip and say why.
"""
import unittest
from datetime import timedelta
from unittest import mock

from django.contrib.auth.hashers import make_password
from django.test import LiveServerTestCase
from django.utils import timezone

from ai_sdr_agent import browser_testing
from ai_sdr_agent.models import (SDRAgentSettings, SDRCampaign, SDRCampaignStep, SDRIcpProfile, SDRLead,
                                 SDRMeeting)
from core.models import Company, CompanyModulePurchase, CompanyUser, DoNotEmail

PASSWORD = 'Correct-horse-9'
WAIT = 20_000  # ms; the first load of the app parses a large bundle


class BrowserTestCase(LiveServerTestCase):
    host = '127.0.0.1'  # 'localhost' tries IPv6 first on Windows and waits 2 s on every request
    static_handler = browser_testing.SpaHandler

    @classmethod
    def setUpClass(cls):
        try:
            browser_testing.frontend_build()
            cls.chrome = browser_testing.BrowserThread()
        except browser_testing.Unavailable as missing:
            raise unittest.SkipTest(str(missing))
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.chrome.close()

    def setUp(self):
        self.company = Company.objects.create(name='Margalla Dental', email='office@margalla.test')
        CompanyModulePurchase.objects.create(company=self.company, module_name='ai_sdr_agent', status='active',
                                             is_complimentary=True)
        self.owner = self.login_row('sana@margalla.test', 'owner', 'Sana Owner')

        def open_page():
            context = self.chrome.browser.new_context()
            page = context.new_page()
            page.set_default_timeout(WAIT)
            return context, page
        self.context, self.page = self.chrome.run(open_page)

    def tearDown(self):
        self.chrome.run(self.context.close)

    def login_row(self, email, role, name):
        return CompanyUser.objects.create(company=self.company, email=email, full_name=name, role=role,
                                          password_hash=make_password(PASSWORD), is_active=True)

    # Each step runs on the browser's thread (see BrowserThread).
    def on_page(self, fn, *args):
        return self.chrome.run(fn, *args)

    def goto(self, path):
        self.on_page(self.page.goto, self.live_server_url + path)

    def fill(self, selector, value):
        self.on_page(self.page.fill, selector, value)

    def click(self, selector):
        self.on_page(self.page.click, selector)

    def see(self, text):
        """Wait until the text shows on the page; fail if it never does."""
        self.on_page(lambda: self.page.get_by_text(text).first.wait_for())

    def current_url(self):
        return self.on_page(lambda: self.page.url)

    def valid(self, selector):
        return self.on_page(self.page.eval_on_selector, selector, 'el => el.checkValidity()')

    def token(self):
        return self.on_page(self.page.evaluate, "() => localStorage.getItem('company_auth_token')")

    def sign_in(self, email='sana@margalla.test', password=PASSWORD):
        self.goto('/company/login')
        self.fill('#email', email)
        self.fill('#password', password)
        self.click('button[type=submit]')

    def signed_in(self, email='sana@margalla.test'):
        self.sign_in(email)
        self.on_page(self.page.wait_for_url, '**/company/dashboard**')

    def button(self, name, dialog=False):
        """Click the button with this name; in the open dialog when dialog=True (the page behind may have one too)."""
        def press():
            scope = self.page.get_by_role('dialog') if dialog else self.page
            scope.get_by_role('button', name=name, exact=True).first.click()
        self.on_page(press)

    def type_into(self, placeholder, value, exact=True):
        """Fill the field that shows this placeholder."""
        self.on_page(lambda: self.page.get_by_placeholder(placeholder, exact=exact).first.fill(value))

    def gone(self, text):
        """Wait until the text is no longer on the page; fail if it stays."""
        self.on_page(lambda: self.page.get_by_text(text).first.wait_for(state='hidden'))

    def row(self, text):
        """Wait until a table row with this text shows."""
        self.on_page(lambda: self.page.locator('tr', has_text=text).first.wait_for())

    def row_gone(self, text):
        self.on_page(lambda: self.page.locator('tr', has_text=text).first.wait_for(state='hidden'))

    def upload(self, selector, name, content, mime='text/csv'):
        """Choose a file in a file input, as if picked in the file dialog."""
        self.on_page(self.page.set_input_files, selector, {'name': name, 'mimeType': mime, 'buffer': content})

    def pause(self, ms=500):
        self.on_page(self.page.wait_for_timeout, ms)


class SdrScreenTestCase(BrowserTestCase):
    """Signed in as the owner, with nothing able to reach an AI model: no key resolves, so the agents fall back to
    their built-in text (the campaign's default steps) instead of calling out."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch('ai_sdr_agent.agents.sdr_key_resolver.resolve_sdr_groq_client', return_value=(None, None))
        patcher.start()
        self.addCleanup(patcher.stop)

    def lead(self, name, email, **kw):
        return SDRLead.objects.create(company_user=self.owner, full_name=name, email=email, **kw)


class SignInTests(BrowserTestCase):
    def test_signing_in_with_the_right_password_opens_the_dashboard(self):
        self.signed_in()
        self.assertTrue(self.token())

    def test_a_wrong_password_says_so_and_stays_on_the_login_page(self):
        self.sign_in(password='wrong-password')
        self.see('Invalid email or password')
        self.assertIn('/company/login', self.current_url())
        self.assertFalse(self.token())

    def test_the_form_will_not_send_without_an_email(self):
        self.goto('/company/login')
        self.fill('#password', PASSWORD)
        self.click('button[type=submit]')
        self.assertFalse(self.valid('#email'))
        self.on_page(self.page.wait_for_timeout, 500)
        self.assertIn('/company/login', self.current_url())
        self.assertFalse(self.token())

    def test_the_form_will_not_send_an_address_that_is_not_an_email(self):
        self.goto('/company/login')
        self.fill('#email', 'not-an-email')
        self.fill('#password', PASSWORD)
        self.click('button[type=submit]')
        self.assertFalse(self.valid('#email'))
        self.assertFalse(self.token())


class AiSdrScreensTests(BrowserTestCase):
    def setUp(self):
        super().setUp()
        SDRLead.objects.create(company_user=self.owner, full_name='Dr Ayesha Khan', email='ayesha@clinic.test',
                               company_name='Smile Clinic', job_title='Practice Owner')
        SDRCampaign.objects.create(company_user=self.owner, name='Clinics in Islamabad', status='draft')

    def test_the_leads_screen_lists_the_companys_leads(self):
        self.signed_in()
        self.goto('/ai-sdr/leads')
        self.see('Dr Ayesha Khan')

    def test_the_outreach_screen_lists_the_campaigns(self):
        self.signed_in()
        self.goto('/ai-sdr/outreach')
        self.see('Clinics in Islamabad')

    def test_an_owner_sees_the_checks_on_the_tests_screen(self):
        self.signed_in()
        self.goto('/ai-sdr/tests')
        self.see('Health checks')
        self.see('Live tests')

    def test_a_salesperson_is_told_the_tests_screen_is_for_owners(self):
        self.login_row('omar@margalla.test', 'company_user', 'Omar Sales')
        self.signed_in('omar@margalla.test')
        self.goto('/ai-sdr/tests')
        self.see("Only your company's owner or an admin")


class LeadsScreenTests(SdrScreenTestCase):
    """/ai-sdr/leads: adding, finding, deleting and importing leads, and the ICP profile."""

    def setUp(self):
        super().setUp()
        self.ayesha = self.lead('Dr Ayesha Khan', 'ayesha@clinic.test', company_name='Smile Clinic', score=82,
                                temperature='hot')
        self.imran = self.lead('Imran Qureshi', 'imran@bright.test', company_name='Bright Dental', score=20,
                               temperature='cold')
        self.signed_in()
        self.goto('/ai-sdr/leads')
        self.row('Dr Ayesha Khan')

    def open_add_lead(self):
        self.button('Add Lead')
        self.see('Add Lead Manually')

    def test_a_lead_with_no_name_and_no_email_is_refused_and_says_why(self):
        self.open_add_lead()
        self.type_into('Acme Corp', 'Nameless Ltd')
        self.button('Add Lead', dialog=True)
        self.see('Enter at least a name or a business email.')
        self.assertFalse(SDRLead.objects.filter(company_name='Nameless Ltd').exists())

    def test_a_malformed_email_is_refused_and_says_why(self):
        self.open_add_lead()
        self.type_into('Jane', 'Bilal')
        self.type_into('jane@company.com', 'bilal@nowhere')
        self.button('Add Lead', dialog=True)
        self.see('Enter a valid business email like jane@company.com.')
        self.assertEqual(SDRLead.objects.count(), 2)

    def test_a_valid_lead_is_saved_and_shows_in_the_list(self):
        self.open_add_lead()
        self.type_into('Jane', 'Bilal')
        self.type_into('Doe', 'Ahmed')
        self.type_into('jane@company.com', 'bilal@smiles.test')
        self.type_into('Acme Corp', 'Smiles Lahore')
        self.button('Add Lead', dialog=True)
        self.see('Lead added')
        self.row('Bilal Ahmed')
        lead = SDRLead.objects.get(email='bilal@smiles.test')
        self.assertEqual(lead.full_name, 'Bilal Ahmed')
        self.assertEqual(lead.company_name, 'Smiles Lahore')
        self.assertEqual(lead.company_user, self.owner)
        self.assertEqual(lead.source, 'manual')

    def test_searching_narrows_the_list(self):
        self.row('Imran Qureshi')
        self.type_into('Search name, company', 'Bright', exact=False)
        self.row_gone('Dr Ayesha Khan')
        self.row('Imran Qureshi')
        self.see('filtered')

    def test_the_temperature_filter_narrows_the_list(self):
        self.row('Imran Qureshi')
        self.button('Filters')
        self.button('All Temperatures')
        self.button('Hot')
        self.row_gone('Imran Qureshi')
        self.row('Dr Ayesha Khan')

    def test_deleting_a_lead_asks_first_then_undo_brings_it_back(self):
        self.on_page(lambda: self.page.locator('tr', has_text='Dr Ayesha Khan').get_by_title('Delete').click())
        self.see('Confirm Delete')
        self.button('Delete', dialog=True)
        self.see('You can undo this.')
        self.row_gone('Dr Ayesha Khan')
        self.assertTrue(SDRLead.all_objects.get(id=self.ayesha.id).is_deleted)
        self.assertFalse(SDRLead.objects.filter(id=self.ayesha.id).exists())

        self.button('Undo')
        self.see('Restored')
        self.row('Dr Ayesha Khan')
        self.assertFalse(SDRLead.all_objects.get(id=self.ayesha.id).is_deleted)

    def open_icp(self):
        self.button('Setup')
        self.type_into('SaaS, FinTech, E-commerce', 'Dental clinics')
        self.type_into('CEO, VP Sales, Head of Growth', 'Practice Owner')

    def test_the_icp_profile_saves(self):
        self.open_icp()
        self.type_into('10', '5')
        self.type_into('500', '200')
        self.button('Save ICP')
        self.see('ICP Profile saved!')
        icp = SDRIcpProfile.objects.get(company_user=self.owner, is_active=True)
        self.assertEqual(icp.industries, ['Dental clinics'])
        self.assertEqual(icp.job_titles, ['Practice Owner'])
        self.assertEqual((icp.company_size_min, icp.company_size_max), (5, 200))
        self.button('Edit')  # the panel now shows the saved profile
        self.assertEqual(self.on_page(lambda: self.page.get_by_placeholder('SaaS, FinTech, E-commerce').input_value()),
                         'Dental clinics')

    def test_a_back_to_front_icp_size_range_shows_the_servers_message(self):
        self.open_icp()
        self.type_into('10', '500')
        self.type_into('500', '10')
        self.button('Save ICP')
        self.see('Save failed')
        self.see('The minimum company size cannot be above the maximum.')
        self.assertFalse(SDRIcpProfile.objects.filter(company_user=self.owner).exists())

    def test_a_csv_with_no_rows_is_refused_and_says_why(self):
        self.button('Import CSV')
        self.upload('input[type=file][accept=".csv"]', 'leads.csv', b'Full Name,Email\n')
        self.see('Nothing to import')
        self.assertEqual(SDRLead.objects.count(), 2)

    def test_a_file_that_is_not_a_csv_shows_the_servers_message(self):
        self.button('Import CSV')
        self.upload('input[type=file][accept=".csv"]', 'leads.csv', b'Full Name,Email\nSara \xff\xfe,sara@x.test\n')
        self.see('1 lead to import')
        self.button('Import 1 leads', dialog=True)
        self.see('Import failed')
        self.see('That file is not a CSV.')
        self.assertEqual(SDRLead.objects.count(), 2)

    def test_a_good_csv_imports_its_leads(self):
        self.button('Import CSV')
        self.upload('input[type=file][accept=".csv"]', 'leads.csv',
                    b'Full Name,Email,Company\nSara Malik,sara@care.test,Care Dental\nOmar Riaz,omar@care.test,'
                    b'Care Dental\n')
        self.see('2 leads to import')
        self.button('Import 2 leads', dialog=True)
        self.see('Imported 2 leads')
        self.row('Sara Malik')
        self.assertEqual(set(SDRLead.objects.filter(company_name='Care Dental').values_list('email', flat=True)),
                         {'sara@care.test', 'omar@care.test'})


class OutreachScreenTests(SdrScreenTestCase):
    """/ai-sdr/outreach: creating a campaign and editing its steps."""

    def setUp(self):
        super().setUp()
        self.signed_in()

    def test_a_campaign_with_no_name_is_refused_and_says_why(self):
        self.goto('/ai-sdr/outreach')
        self.button('New Campaign')
        self.see('New Outreach Campaign')
        self.type_into('e.g. Q1 SaaS Founders Outreach', '   ')
        self.button('Create Campaign', dialog=True)
        self.see('Campaign name is required')
        self.assertFalse(SDRCampaign.objects.exists())

    def test_a_new_campaign_is_saved_with_its_steps_and_opens(self):
        self.goto('/ai-sdr/outreach')
        self.button('New Campaign')
        self.type_into('e.g. Q1 SaaS Founders Outreach', 'Dentists in Lahore')
        self.button('Create Campaign', dialog=True)
        self.see('Campaign created')
        self.see('Outreach Sequence')
        self.see('Introduction')
        campaign = SDRCampaign.objects.get(name='Dentists in Lahore')
        self.assertEqual(campaign.company_user, self.owner)
        self.assertEqual(campaign.status, 'draft')
        self.assertTrue(campaign.steps.exists())

    def open_step(self):
        campaign = SDRCampaign.objects.create(company_user=self.owner, name='Clinics in Islamabad', status='draft')
        self.step = SDRCampaignStep.objects.create(campaign=campaign, step_order=1, step_type='email', delay_days=1,
                                                   name='Intro email', subject_template='Hello {first_name}',
                                                   body_template='A short note about your clinic.')
        self.goto('/ai-sdr/outreach')
        self.click('text=Clinics in Islamabad')
        self.see('Outreach Sequence')
        self.on_page(lambda: self.page.get_by_text('Intro email', exact=True).first
                     .locator('xpath=ancestor::div[2]/following-sibling::div[1]/button[1]').click())
        self.see('Edit Step 1')

    def test_a_step_with_an_empty_subject_is_refused_and_says_why(self):
        self.open_step()
        self.type_into('e.g. Quick question for {first_name} at {company_name}', '')
        self.button('Save Step', dialog=True)
        self.see('Update failed')
        self.see('The step needs a subject.')
        self.step.refresh_from_db()
        self.assertEqual(self.step.subject_template, 'Hello {first_name}')

    def test_a_step_with_an_empty_body_is_refused_and_says_why(self):
        self.open_step()
        self.on_page(lambda: self.page.get_by_role('dialog').locator('textarea').fill(''))
        self.button('Save Step', dialog=True)
        self.see('Update failed')
        self.see('The step needs a text.')
        self.step.refresh_from_db()
        self.assertEqual(self.step.body_template, 'A short note about your clinic.')

    def test_an_edited_step_is_saved(self):
        self.open_step()
        self.type_into('e.g. Quick question for {first_name} at {company_name}', 'A question for {company_name}')
        self.button('Save Step', dialog=True)
        self.see('Step updated')
        self.step.refresh_from_db()
        self.assertEqual(self.step.subject_template, 'A question for {company_name}')


class MeetingsScreenTests(SdrScreenTestCase):
    """/ai-sdr/meetings: the booked calls and what can be done with them."""

    def setUp(self):
        super().setUp()
        ayesha = self.lead('Dr Ayesha Khan', 'ayesha@clinic.test', company_name='Smile Clinic')
        imran = self.lead('Imran Qureshi', 'imran@bright.test', company_name='Bright Dental')
        self.meeting = SDRMeeting.objects.create(company_user=self.owner, lead=ayesha, status='scheduled',
                                                 scheduled_at=timezone.now() - timedelta(hours=2), is_manual=True)
        SDRMeeting.objects.create(company_user=self.owner, lead=imran, status='pending', is_manual=True)
        self.signed_in()
        self.goto('/ai-sdr/meetings')

    def test_the_meetings_are_listed_with_their_status(self):
        self.row('Dr Ayesha Khan')
        self.row('Imran Qureshi')
        self.on_page(lambda: self.page.locator('tr', has_text='Dr Ayesha Khan').get_by_text('Scheduled').wait_for())
        self.on_page(lambda: self.page.locator('tr', has_text='Imran Qureshi').get_by_text('Not confirmed').wait_for())

    def test_searching_narrows_the_list(self):
        self.row('Imran Qureshi')
        self.type_into('Search all fields', 'Bright', exact=False)
        self.row_gone('Dr Ayesha Khan')
        self.row('Imran Qureshi')

    def test_a_past_call_can_be_marked_completed(self):
        self.click('text=Dr Ayesha Khan')
        self.button('Mark Completed')
        self.see('Marked as Completed')
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.status, 'completed')


class SettingsScreenTests(SdrScreenTestCase):
    """/ai-sdr/settings and the company's do-not-email list."""

    def setUp(self):
        super().setUp()
        self.signed_in()

    def test_the_settings_screen_loads_and_saves_a_lead_source_key(self):
        self.goto('/ai-sdr/settings')
        self.see('No lead sources configured')
        self.type_into('Enter your Apollo.io API key', 'apollo-test-key-123')
        self.button('Save API Keys')
        self.see('Settings saved')
        self.see('Lead sources configured')
        self.assertEqual(SDRAgentSettings.objects.get(company_user=self.owner).apollo_api_key, 'apollo-test-key-123')

    def test_the_do_not_email_form_will_not_send_something_that_is_not_an_email(self):
        self.goto('/company/settings/do-not-email')
        self.see('Nobody is on the list yet.')
        self.type_into('person@example.com', 'not-an-email')
        self.button('Add')
        self.assertFalse(self.valid('input[type=email]'))
        self.assertFalse(DoNotEmail.objects.exists())

    def test_an_address_the_server_refuses_shows_its_message(self):
        self.goto('/company/settings/do-not-email')
        self.type_into('person@example.com', 'person@nowhere')
        self.button('Add')
        self.see('Not added')
        self.see('Enter one valid email address.')
        self.assertFalse(DoNotEmail.objects.exists())

    def test_a_valid_address_is_added_and_listed(self):
        self.goto('/company/settings/do-not-email')
        self.type_into('person@example.com', 'Patient@Clinic.test')
        self.type_into('e.g. asked by phone', 'asked at reception')
        self.button('Add')
        self.see('will not be emailed.')
        self.see('1 address')
        self.see('patient@clinic.test')
        entry = DoNotEmail.objects.get(company=self.company)
        self.assertEqual(entry.email, 'patient@clinic.test')
        self.assertEqual(entry.note, 'asked at reception')


class DashboardScreenTests(SdrScreenTestCase):
    """/ai-sdr/dashboard: the figures match what is in the database."""

    def test_the_figures_match_the_leads_and_campaigns(self):
        self.lead('A One', 'a@x.test', score=90, temperature='hot')
        self.lead('B Two', 'b@x.test', score=80, temperature='hot')
        self.lead('C Three', 'c@x.test', score=65, temperature='warm')
        self.lead('D Four', 'd@x.test')
        SDRCampaign.objects.create(company_user=self.owner, name='Live one', status='active')
        SDRCampaign.objects.create(company_user=self.owner, name='Draft one', status='draft')
        self.signed_in()
        self.goto('/ai-sdr/dashboard')
        self.see('Total Leads')

        def figure(label):
            return self.page.get_by_text(label, exact=True).first.locator('xpath=preceding-sibling::div[1]').inner_text()
        self.assertEqual(self.on_page(figure, 'Total Leads'), '4')
        self.see('2 hot · 1 warm')
        self.assertEqual(self.on_page(figure, 'Active Campaigns'), '1')
        self.see('2 total')
