"""The secret key, debug mode and accepted hosts have one answer each.

settings.py set them twice and the second copy won: a server set up with the
names .env.example describes (DJANGO_SECRET_KEY, DJANGO_DEBUG,
DJANGO_ALLOWED_HOSTS) ran in debug mode, accepting any host, on the secret key
that is published in git.
"""
from pathlib import Path

from django.conf import settings
from django.core.checks import Error
from django.test import SimpleTestCase, override_settings

from core import checks
from project_manager_ai import env_security
from project_manager_ai.env_security import PUBLIC_SECRET_KEY, allowed_hosts, debug, secret_key

SERVER = ['gunicorn']
DEV = ['manage.py', 'runserver']


class OneAnswerTests(SimpleTestCase):

    def test_a_server_set_up_the_way_the_example_file_says_is_locked_down(self):
        env = {'DJANGO_SECRET_KEY': 'synthetic-private-key', 'DJANGO_DEBUG': '0',
               'DJANGO_ALLOWED_HOSTS': 'api.example.com, www.example.com'}
        self.assertEqual(secret_key(env), 'synthetic-private-key')
        self.assertFalse(debug(env, SERVER))
        self.assertEqual(allowed_hosts(env, False), ['api.example.com', 'www.example.com'])

    def test_a_server_on_the_older_names_keeps_exactly_what_it_has(self):
        env = {'SECRET_KEY': 'synthetic-old-key', 'DEBUG': 'False', 'ALLOWED_HOSTS': '203.0.113.7,api.example.com'}
        self.assertEqual(secret_key(env), 'synthetic-old-key')
        self.assertFalse(debug(env, SERVER))
        self.assertEqual(allowed_hosts(env, False), ['203.0.113.7', 'api.example.com'])

    def test_with_both_names_set_the_older_one_wins(self):
        # Changing the key a server runs on would make its stored API keys unreadable.
        env = {'SECRET_KEY': 'synthetic-old-key', 'DJANGO_SECRET_KEY': 'synthetic-new-key',
               'DEBUG': 'False', 'DJANGO_DEBUG': '1', 'ALLOWED_HOSTS': 'old.example.com',
               'DJANGO_ALLOWED_HOSTS': 'new.example.com'}
        self.assertEqual(secret_key(env), 'synthetic-old-key')
        self.assertFalse(debug(env, SERVER))
        self.assertEqual(allowed_hosts(env, False), ['old.example.com'])

    def test_with_nothing_set_a_server_is_not_in_debug_mode_and_not_open_to_any_host(self):
        env = {'SITE_URL': 'https://app.example.com', 'BACKEND_URL': 'https://api.example.com/'}
        self.assertFalse(debug(env, SERVER))
        self.assertFalse(debug(env, ['manage.py', 'migrate']))
        self.assertEqual(allowed_hosts(env, False), ['localhost', '127.0.0.1', 'app.example.com', 'api.example.com'])
        self.assertEqual(secret_key(env), PUBLIC_SECRET_KEY)            # local development only

    def test_the_local_dev_server_still_just_works(self):
        self.assertTrue(debug({}, DEV))
        self.assertEqual(allowed_hosts({}, True), ['*'])

    def test_debug_reads_like_a_switch(self):
        for off in ('0', 'false', 'False', 'no', 'OFF'):
            self.assertFalse(debug({'DEBUG': off}, DEV), off)           # DEBUG=0 used to leave it on
            self.assertFalse(debug({'DJANGO_DEBUG': off}, DEV), off)
        for on in ('1', 'true', 'True', 'yes'):
            self.assertTrue(debug({'DEBUG': on}, SERVER), on)
            self.assertTrue(debug({'DJANGO_DEBUG': on}, SERVER), on)
        self.assertTrue(debug({'DEBUG': 'sometimes'}, SERVER))           # unrecognised: on, as before
        self.assertFalse(debug({'DJANGO_DEBUG': 'sometimes'}, SERVER))   # the newer name falls to the default

    def test_blank_values_count_as_unset(self):
        env = {'SECRET_KEY': '  ', 'DEBUG': '', 'ALLOWED_HOSTS': ' , '}
        self.assertEqual(secret_key(env), PUBLIC_SECRET_KEY)
        self.assertFalse(debug(env, SERVER))
        self.assertEqual(allowed_hosts(env, False), ['localhost', '127.0.0.1'])

    def test_settings_asks_these_functions_and_nothing_sets_them_again(self):
        source = (Path(settings.BASE_DIR) / 'project_manager_ai' / 'settings.py').read_text(encoding='utf-8')
        for name in ('SECRET_KEY', 'DEBUG', 'ALLOWED_HOSTS'):
            assignments = [line for line in source.splitlines() if line.startswith(f'{name} =')]
            self.assertEqual(len(assignments), 1, name)
            self.assertIn('_env_security.', assignments[0], name)
        self.assertIs(env_security.secret_key, secret_key)


class DeployCheckTests(SimpleTestCase):

    def problems(self):
        return {issue.id for issue in checks.check_not_running_on_the_defaults(None)
                if isinstance(issue, Error)}

    def test_the_public_key_or_debug_mode_fails_the_deploy_check(self):
        with override_settings(SECRET_KEY=PUBLIC_SECRET_KEY, DEBUG=True):
            self.assertEqual(self.problems(), {'security.E101', 'security.E102'})

    def test_a_locked_down_server_passes(self):
        with override_settings(SECRET_KEY='synthetic-private-key', DEBUG=False):
            self.assertEqual(self.problems(), set())
