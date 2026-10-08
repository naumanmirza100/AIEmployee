"""An employee stays signed in when they reload the page.

GET auth/me answered 500 for everybody: its serializer listed a `phone` field
that was never declared and that User does not have. The screens ask it on
every page load and sign the person out when it fails, so every reload, and
every link opened in a new tab, signed an employee or platform admin out.
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from rest_framework.authtoken.models import Token

from core.models import Company, CompanyUser, UserProfile


class SessionCheckTests(TestCase):

    def setUp(self):
        company = Company.objects.create(name='Acme', email='acme@test.local')
        creator = CompanyUser.objects.create(company=company, email='dana@test.local', full_name='Dana',
                                             role='admin', password_hash='x', is_active=True)
        self.pat = get_user_model().objects.create_user(username='pat', email='pat@test.local',
                                                        password='a-synthetic-password', first_name='Pat')
        UserProfile.objects.update_or_create(user=self.pat, defaults={
            'company': company, 'created_by_company_user': creator, 'role': 'project_manager'})
        self.admin = get_user_model().objects.create_user(username='root', email='root@test.local',
                                                          password='a-synthetic-password', is_staff=True)

    def me(self, user):
        token = Token.objects.get_or_create(user=user)[0].key
        return Client(HTTP_AUTHORIZATION=f'Token {token}').get('/api/auth/me')

    def test_the_session_check_answers(self):
        response = self.me(self.pat)
        self.assertEqual(response.status_code, 200, response.content[:300])
        user = response.json()['data']['user']
        self.assertEqual((user['email'], user['firstName'], user['phone']), ('pat@test.local', 'Pat', None))

    def test_it_says_what_sign_in_says_so_a_reload_changes_nothing(self):
        signed_in = Client().post('/api/auth/login', {'email': 'pat@test.local', 'password': 'a-synthetic-password'},
                                  content_type='application/json').json()['data']['user']
        checked = self.me(self.pat).json()['data']['user']
        for field, value in signed_in.items():
            self.assertEqual(checked[field], value, field)
        self.assertEqual((checked['role'], checked['createdByCompanyUser']), ('project_manager', True))

    def test_the_phone_on_their_profile_reaches_their_own_screens(self):
        # It always answered "none", so the home page told every employee their profile had no phone.
        UserProfile.objects.filter(user=self.pat).update(phone_number='+92 300 0000000')
        signed_in = Client().post('/api/auth/login', {'email': 'pat@test.local', 'password': 'a-synthetic-password'},
                                  content_type='application/json').json()['data']['user']
        self.assertEqual((signed_in['phone'], self.me(self.pat).json()['data']['user']['phone']),
                         ('+92 300 0000000', '+92 300 0000000'))
        self.assertIsNone(self.me(self.admin).json()['data']['user']['phone'])        # no profile, no phone, no error

    def test_a_platform_admin_is_still_an_admin_after_a_reload(self):
        user = self.me(self.admin).json()['data']['user']
        self.assertEqual((user['userType'], user['createdByCompanyUser']), ('admin', False))

    def test_without_a_token_it_is_refused_not_broken(self):
        self.assertIn(Client().get('/api/auth/me').status_code, (401, 403))
