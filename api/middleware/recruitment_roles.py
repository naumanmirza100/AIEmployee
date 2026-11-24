"""What a Recruitment role may change (24 Nov 2026, models.RecruitmentRole).

What each role sees is decided in recruitment_agent/sharing.py, which every Recruitment view reads through. What each
may change is decided here, by path, as module_access.py decides who may use an agent at all: there are some 50
Recruitment endpoints, and a rule written once here can't be forgotten on the next one.

  * recruiter: anything, as before.
  * hiring manager: anything on their own jobs and candidates (the views find only those), except the company-wide
    automation (workflows) and who has which role.
  * interviewer: only their interview feedback, their own Q&A chats and saved graphs, and reading.
"""
import re

from django.http import JsonResponse

SAFE = ('GET', 'HEAD', 'OPTIONS')

#: What an interviewer may change.
INTERVIEWER_MAY = re.compile(
    r'^recruitment/(interviews/\d+/feedback|qa(/stream)?|qa/chats(/create|/\d+/(update|delete))?|'
    r'ai/generate-graph|ai/graph-prompts(/save|/\d+/(delete|favorite|dashboard))?|ai/suggest-interview-questions)/?$')
#: What a hiring manager may not change.
HIRING_MANAGER_MAY_NOT = re.compile(r'^recruitment/(workflows|roles)(/|$)')
#: Who has which role: owners and admins only (checked in the view too).
ROLES_PATH = re.compile(r'^recruitment/roles(/|$)')

MESSAGES = {
    'interviewer': ("As an interviewer in Recruitment you can see your interviews and give feedback on them. Ask a "
                    "recruiter for anything else."),
    'hiring_manager': ("As a hiring manager in Recruitment you work on your own jobs and their candidates. Workflows "
                       "and roles are set by a recruiter or an admin."),
}


class RecruitmentRoleMiddleware:
    """Refuse a change a login's Recruitment role does not allow."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method not in SAFE and request.path.startswith('/api/'):
            rest = re.sub(r'^v\d+/', '', request.path[len('/api/'):])
            if rest.startswith('recruitment/'):
                refused = self._refused(request, rest)
                if refused:
                    return refused
        return self.get_response(request)

    @staticmethod
    def _refused(request, rest):
        from recruitment_agent import sharing
        company_user = _company_user(request)
        if company_user is None:
            return None
        who = sharing.role(company_user)
        if who == sharing.INTERVIEWER and not INTERVIEWER_MAY.match(rest):
            return JsonResponse({'status': 'error', 'code': 'recruitment_role', 'role': who,
                                 'message': MESSAGES[who]}, status=403)
        if who == sharing.HIRING_MANAGER and HIRING_MANAGER_MAY_NOT.match(rest):
            return JsonResponse({'status': 'error', 'code': 'recruitment_role', 'role': who,
                                 'message': MESSAGES[who]}, status=403)
        return None


def _company_user(request):
    """The dashboard login behind the request's token, or None (middleware runs before DRF authenticates)."""
    from core.models import CompanyUserToken
    header = request.META.get('HTTP_AUTHORIZATION', '')
    for keyword in ('Token ', 'Bearer '):
        if header.startswith(keyword):
            token = (CompanyUserToken.objects.select_related('company_user')
                     .filter(key=header[len(keyword):].strip()).first())
            if token is not None and token.company_user.is_active:
                return token.company_user
    return None
