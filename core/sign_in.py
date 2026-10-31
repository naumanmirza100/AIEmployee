"""Signing in: how many wrong passwords an account may take, and how long a session lasts.

Both kinds of login use this: dashboard logins (CompanyUser, CompanyUserToken) and employee or
platform logins (auth.User, UserToken).

Wrong passwords (CO-100). The per-caller limit on the sign-in addresses counts requests from
one address, which an office shares and which a caller sending a forged forwarding header could
change. What stops someone guessing one person's password is a count kept on the account
itself: after MAX_WRONG_PASSWORDS wrong tries the account refuses every password, the right one
included, for LOCK_MINUTES. The count is kept for any address typed, with or without a login, so
the reply never says whether one exists.

Sessions (CO-270). Signing in used to hand back the one token a login had, the same on every
device and good for ever; signing out on one device signed out all of them. Now each sign-in
makes its own token, signing out ends only that one, and a token not used for
SESSION_IDLE_DAYS (setting, default 30) stops working.
"""
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

MAX_WRONG_PASSWORDS = 10
LOCK_MINUTES = 15
LOCKED_MESSAGE = (f'Too many wrong passwords for this account. Wait {LOCK_MINUTES} minutes and try '
                  'again, or reset the password.')

# A token's last use is written at most this often, not on every request.
TOUCH_EVERY = timedelta(hours=1)
SESSION_ENDED_MESSAGE = 'Your session has ended because it was not used for a while. Please sign in again.'


# ---- wrong passwords ----------------------------------------------------------------------------

def _failures_key(kind, email):
    return f'sign-in-failures:{kind}:{(email or "").strip().lower()}'


def is_locked(kind, email):
    """True while this account refuses every password. `kind` is 'dashboard' or 'user'."""
    return (cache.get(_failures_key(kind, email)) or 0) >= MAX_WRONG_PASSWORDS


def wrong_password(kind, email):
    """Count one wrong password. The one that reaches the limit starts a full lock."""
    key = _failures_key(kind, email)
    window = LOCK_MINUTES * 60
    cache.add(key, 0, window)
    try:
        count = cache.incr(key)
    except ValueError:              # the window ended between the two lines
        cache.set(key, 1, window)
        return
    if count >= MAX_WRONG_PASSWORDS:
        cache.set(key, count, window)


def right_password(kind, email):
    cache.delete(_failures_key(kind, email))


# ---- sessions -------------------------------------------------------------------------------------

def idle_days():
    return int(getattr(settings, 'SESSION_IDLE_DAYS', 30) or 30)


def _cutoff():
    return timezone.now() - timedelta(days=idle_days())


def is_stale(token):
    """True when the token has not been used for SESSION_IDLE_DAYS."""
    last = getattr(token, 'last_used', None) or getattr(token, 'created', None)
    return last is not None and last < _cutoff()


def touch(token):
    """Note that the token was used, at most once an hour (a write on every request would be waste)."""
    now = timezone.now()
    last = getattr(token, 'last_used', None)
    if last is None or now - last >= TOUCH_EVERY:
        type(token).objects.filter(pk=token.pk).update(last_used=now)
        token.last_used = now


def _stale_q():
    cutoff = _cutoff()
    return Q(last_used__lt=cutoff) | Q(last_used__isnull=True, created__lt=cutoff)


def new_dashboard_token(company_user):
    """A token for this sign-in only. The login's tokens that ran out are cleared on the way."""
    from core.models import CompanyUserToken
    CompanyUserToken.objects.filter(company_user=company_user).filter(_stale_q()).delete()
    return CompanyUserToken.objects.create(company_user=company_user, last_used=timezone.now())


def new_user_token(user):
    """A token for this sign-in only, for an employee or platform login (auth.User)."""
    from core.models import UserToken
    UserToken.objects.filter(user=user).filter(_stale_q()).delete()
    return UserToken.objects.create(user=user, key=secrets.token_hex(20), last_used=timezone.now())


def end_user_sessions(user_or_id):
    """Sign an employee or platform login out everywhere (deactivated, offboarded)."""
    from rest_framework.authtoken.models import Token
    from core.models import UserToken
    user_id = getattr(user_or_id, 'pk', user_or_id)
    UserToken.objects.filter(user_id=user_id).delete()
    Token.objects.filter(user_id=user_id).delete()        # tokens from before CO-270
