from django.conf import settings
from django.contrib import admin
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import path, include
from marketing_agent import views_email_tracking
from ai_sdr_agent.views_booking import book_meeting


def home(request):
    """The API's own address has nothing to show: send people to the app."""
    if settings.FRONTEND_URL:
        return HttpResponseRedirect(settings.FRONTEND_URL)
    return JsonResponse({'status': 'ok', 'service': 'Pay Per Project API'})


urlpatterns = [
    path('admin/', admin.site.urls),
]

if settings.LEGACY_SITE_ENABLED:
    # The old server-rendered site. See LEGACY_SITE_ENABLED in settings: these
    # pages do not keep one company's data from another's.
    from core.views import (
        signup, dashboard, user_login, user_logout, select_role,
        project_list, project_create, project_detail, project_edit, project_delete,
        task_create, task_edit, my_tasks, update_task_status
    )
    from project_manager_agent.views import view_task_subtasks

    urlpatterns += [
        path('signup/', signup, name='signup'),
        path('login/', user_login, name='login'),
        path('logout/', user_logout, name='logout'),
        path('select-role/', select_role, name='select_role'),
        path('dashboard/', dashboard, name='dashboard'),

        # Project URLs
        path('projects/', project_list, name='project_list'),
        path('projects/create/', project_create, name='project_create'),
        path('projects/<int:project_id>/', project_detail, name='project_detail'),
        path('projects/<int:project_id>/edit/', project_edit, name='project_edit'),
        path('projects/<int:project_id>/delete/', project_delete, name='project_delete'),

        # Task URLs
        path('tasks/create/', task_create, name='task_create'),
        path('tasks/create/<int:project_id>/', task_create, name='task_create_for_project'),
        path('tasks/<int:task_id>/edit/', task_edit, name='task_edit'),
        path('my-tasks/', my_tasks, name='my_tasks'),
        path('tasks/<int:task_id>/update-status/', update_task_status, name='update_task_status'),

        # Subtasks
        path('tasks/<int:task_id>/subtasks/', view_task_subtasks, name='view_task_subtasks'),

        # Old Frontline pages and their session-login APIs
        path('frontline/', include('Frontline_agent.urls')),
        path('api/frontline/', include('core.Frontline_agent.urls')),
    ]

urlpatterns += [
    # Recruitment and Marketing: each file lists only the pages people reach
    # from a link in an email, plus the old session pages when the switch is on.
    path('recruitment/', include('recruitment_agent.urls')),
    path('marketing/', include('marketing_agent.urls')),

    # Note: the legacy `reply-draft/` mount (Django session-auth views) was
    # removed; the only consumer is the SPA, which talks to the DRF surface
    # at `/api/reply-draft/...` (see api/urls.py).

    # Simple token tracking (root level - /token?t=TOKEN for opens, /token?t=TOKEN&url=... for clicks)
    path('token/', views_email_tracking.simple_track_open, name='root_simple_track_open'),
    path('token/<str:tracking_token>/', views_email_tracking.simple_track_click, name='root_simple_track_click'),

    # Public meeting booking page (no auth — token in URL)
    path('book/<uuid:token>/', book_meeting, name='sdr_book_meeting'),

    # API Routes
    path('api/', include('api.urls')),

    # Project Manager API endpoints
    path('api/project-manager/', include('core.api_urls')),
]

if settings.LEGACY_SITE_ENABLED:
    urlpatterns += [path('', user_login, name='home')]  # the old login page
else:
    urlpatterns += [path('', home, name='home')]
