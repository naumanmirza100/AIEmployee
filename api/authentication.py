"""
Custom authentication for Company Users
"""
import logging

from rest_framework import authentication
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed
from core.models import CompanyUserToken, UserToken
from core import sign_in

logger = logging.getLogger(__name__)


class EmployeeTokenAuthentication(TokenAuthentication):
    """Token authentication for employee and platform logins (auth.User), one token per sign-in.

    The employee-facing PM API (/api/user/project-manager/) used to rely on
    DEFAULT_AUTHENTICATION_CLASSES without saying so (audit item DATA-3). A
    dashboard login's token (CompanyUserToken) is sent in the same
    "Authorization: Token <key>" header, so it failed with a bare
    "Invalid token." — which looked like an expired session, not a wrong login
    type. This says what actually went wrong.

    It is also the default authentication (settings). Tokens live in UserToken and end when unused
    for SESSION_IDLE_DAYS (CO-270). A token DRF handed out before that (authtoken.Token, one per
    login and good for ever) is turned into a UserToken with the same key the first time it is
    used, so nobody was signed out by the change.
    """

    def authenticate_credentials(self, key):
        token = UserToken.objects.select_related('user').filter(key=key).first()
        if token is None:
            token = self._from_drf_token(key)
        if token is None:
            if CompanyUserToken.objects.filter(key=key).exists():
                raise AuthenticationFailed(
                    'This is a company dashboard login. These endpoints are for employee '
                    'logins; dashboard logins use /api/project-manager/ and /api/company/.'
                )
            raise AuthenticationFailed('Invalid token.')
        if not token.user.is_active:
            raise AuthenticationFailed('User inactive or deleted.')
        if sign_in.is_stale(token):
            token.delete()
            raise AuthenticationFailed(sign_in.SESSION_ENDED_MESSAGE)
        sign_in.touch(token)
        return (token.user, token)

    @staticmethod
    def _from_drf_token(key):
        from django.db import IntegrityError, transaction
        from rest_framework.authtoken.models import Token
        old = Token.objects.select_related('user').filter(key=key).first()
        if old is None:
            return None
        try:
            with transaction.atomic():
                token = UserToken.objects.create(user=old.user, key=old.key)
                old.delete()
        except IntegrityError:          # another request turned it at the same moment
            token = UserToken.objects.select_related('user').filter(key=key).first()
        return token


class CompanyUserTokenAuthentication(authentication.BaseAuthentication):
    """
    Token-based authentication for CompanyUser.
    Clients should authenticate by passing the token key in the "Authorization"
    HTTP header, prepended with the string "Token " or "Bearer ".
    For example: Authorization: Token 401f7ac837da42b97f613d789819ff93537bee6a

    One token per sign-in; a token unused for SESSION_IDLE_DAYS stops working (CO-270).
    """

    keyword = 'Token'

    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')

        if not auth_header:
            return None

        # Support both "Token" and "Bearer" keywords
        keywords = ['Token', 'Bearer']
        token_key = None

        for keyword in keywords:
            if auth_header.startswith(f'{keyword} '):
                token_key = auth_header[len(f'{keyword} '):].strip()
                break

        if not token_key:
            return None

        try:
            token = CompanyUserToken.objects.select_related('company_user').get(key=token_key)
        except CompanyUserToken.DoesNotExist:
            raise AuthenticationFailed('Invalid token')
        except Exception:
            # The reason stays in the log: the caller gets no server text (CO-271).
            logger.exception('Dashboard token lookup failed')
            raise AuthenticationFailed('Authentication failed')

        company_user = token.company_user
        if not company_user.is_active:
            raise AuthenticationFailed('Company user account is inactive')
        if sign_in.is_stale(token):
            token.delete()
            raise AuthenticationFailed(sign_in.SESSION_ENDED_MESSAGE)
        sign_in.touch(token)

        # Return a tuple (user, auth) where user is the company_user
        return (company_user, token)
