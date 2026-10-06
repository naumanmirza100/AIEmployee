"""Notice when a logged-in screen calls an API address this server doesn't have.

That is what a frontend newer than the backend looks like from here: the URL
matches nothing and the caller is one of our own logins, not a bot guessing
paths. It is reported through the 'alerts' logger (core/error_alerts.py), once
per part of the API.
"""
import logging

from api.middleware.module_access import ModuleAccessMiddleware

alerts = logging.getLogger('alerts')


class UnknownEndpointMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (response.status_code == 404
                and request.path.startswith('/api/')
                and getattr(request, 'resolver_match', None) is None
                and ModuleAccessMiddleware._resolve_company(request) is not None):
            area = '/'.join(request.path.split('/')[:3])        # '/api/quick-chats'
            alerts.error(
                'A logged-in screen called %s %s, which this server does not have. The frontend is '
                'probably newer than the backend: check that the latest main is deployed, or '
                're-upload the frontend build that matches it.',
                request.method, request.path, extra={'alert_key': 'unknown-endpoint:' + area})
        return response
