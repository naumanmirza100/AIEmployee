"""The secret key, debug mode and accepted hosts, read from the environment once.

settings.py used to set all three twice. The careful version read
DJANGO_SECRET_KEY, DJANGO_DEBUG and DJANGO_ALLOWED_HOSTS; a second copy a few
lines lower overwrote all three from the older names (SECRET_KEY, DEBUG,
ALLOWED_HOSTS) and, when those were missing, fell back to debug mode on, any
host accepted, and the secret key that is published in git. So a new server
set up the way .env.example describes ran in debug mode with the public key.

Now there is one answer for each. Both names are read, and the OLDER name wins
when both are set: it is the one every existing server already runs on, so
nothing changes for them (a different secret key would make every stored API
key unreadable). With neither set, the careful defaults apply.

These are plain functions of the environment so they can be tested without
reloading settings (core/tests_env_security.py).
"""
from urllib.parse import urlparse

#: Public: it is in git. Fine for local development only.
PUBLIC_SECRET_KEY = 'django-insecure-9hce6%w7!*)lb#$^6)gb8!h01#6t6y_85nn=exz82l4dj=6q45'

_ON = ('1', 'true', 'yes', 'on')
_OFF = ('0', 'false', 'no', 'off')


def _value(env, name) -> str:
    return (env.get(name) or '').strip()


def _flag(env, name):
    """True / False, or None when unset or unrecognised."""
    value = _value(env, name).lower()
    return True if value in _ON else False if value in _OFF else None


def _host(url) -> str:
    try:
        return urlparse(url or '').hostname or ''
    except ValueError:
        return ''


def secret_key(env) -> str:
    return _value(env, 'SECRET_KEY') or _value(env, 'DJANGO_SECRET_KEY') or PUBLIC_SECRET_KEY


def debug(env, argv) -> bool:
    """DEBUG, then DJANGO_DEBUG, decide when set. With neither, debug is on
    only for the local dev server (`manage.py runserver`) and off everywhere
    else: a deployed server, Celery, management commands.

    The older DEBUG used to mean "on unless it says exactly False", so
    DEBUG=0 left debug on. It now reads like any other switch; a value it does
    not recognise still means on, as it did.
    """
    old = _value(env, 'DEBUG')
    if old:
        return _flag(env, 'DEBUG') is not False
    new = _flag(env, 'DJANGO_DEBUG')
    if new is not None:
        return new
    return any(arg.startswith('runserver') for arg in argv[1:2])


def allowed_hosts(env, debug_on) -> list:
    """Comma-separated ALLOWED_HOSTS, then DJANGO_ALLOWED_HOSTS. With neither:
    any host while debugging (localhost, tunnels); otherwise localhost plus the
    host of SITE_URL / BACKEND_URL, so a deployment that sets those keeps
    working. It used to be "any host" whenever the old name was missing."""
    raw = _value(env, 'ALLOWED_HOSTS') or _value(env, 'DJANGO_ALLOWED_HOSTS')
    hosts = [h.strip() for h in raw.split(',') if h.strip()]
    if not hosts:
        hosts = ['*'] if debug_on else ['localhost', '127.0.0.1'] + [
            h for h in (_host(env.get('SITE_URL')), _host(env.get('BACKEND_URL'))) if h]
    return list(dict.fromkeys(hosts))
