"""Settings for the automated tests.

    python manage.py test project_manager_agent --settings=project_manager_ai.settings_test

Why a separate settings module rather than the normal one:

  * **A local SQLite database, never Hostinger.** The test runner creates and
    drops its own database; the Hostinger user may not do that, and the
    remote database allows only 500 new connections an hour, shared by the
    whole team (NEW-4 in the audit). A test run must not spend that budget.
  * **No migrations.** Tables are built straight from the models. There are
    ~390 migrations, some of them written for MySQL, and replaying them for
    every run would be slow for no gain — the models are what the code uses.
    Note this means data migrations don't run, so tests create the rows they
    need.
  * **No throttling, no Celery, no real email**, so tests don't depend on
    timing, a broker, or an SMTP server.
"""
import os

os.environ.setdefault('SDR_SCHEDULER_ENABLED', 'false')
os.environ.setdefault('CELERY_AUTOSTART', 'false')
os.environ.setdefault('DJANGO_DEBUG', '0')

from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}


class _SkipMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = _SkipMigrations()

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
WHITENOISE_AUTOREFRESH = True

# Rate limits are a production concern; in tests they would just make a long
# test class fail halfway through. GAP-3 checks that the throttles are wired
# to the views, which is the part that can regress.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    'DEFAULT_THROTTLE_RATES': {
        key: None for key in REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', {})  # noqa: F405
    },
}

CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

# The views log an exception for every deliberate 4xx a test provokes; that
# output would bury the test results.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': True,
    'handlers': {'null': {'class': 'logging.NullHandler'}},
    'root': {'handlers': ['null'], 'level': 'CRITICAL'},
}
