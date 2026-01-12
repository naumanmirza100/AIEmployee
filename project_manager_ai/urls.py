from django.contrib import admin
from django.urls import path, include
from core.views import (
    signup, dashboard, user_login, user_logout, select_role,
    project_list, project_create, project_detail, project_edit, project_delete,
    task_create, task_edit, my_tasks, update_task_status
)
from project_manager_agent.views import (
    ai_agents_test, test_task_prioritization, test_knowledge_qa, test_project_pilot, test_timeline_gantt,
    generate_subtasks, view_task_subtasks
)
from marketing_agent import views_email_tracking

urlpatterns = [
    path('admin/', admin.site.urls),
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
    
    # AI Agents
    path('ai-agents/', ai_agents_test, name='ai_agents_test'),
    path('api/ai/task-prioritization/', test_task_prioritization, name='test_task_prioritization'),
    path('api/ai/knowledge-qa/', test_knowledge_qa, name='test_knowledge_qa'),
    path('api/ai/project-pilot/', test_project_pilot, name='test_project_pilot'),
    path('api/ai/timeline-gantt/', test_timeline_gantt, name='test_timeline_gantt'),
    path('api/ai/generate-subtasks/', generate_subtasks, name='generate_subtasks'),
    
    # Subtasks
    path('tasks/<int:task_id>/subtasks/', view_task_subtasks, name='view_task_subtasks'),
    
    # Recruitment Agent
    path('recruitment/', include('recruitment_agent.urls')),
    
    # Frontline Agent
    path('frontline/', include('Frontline_agent.urls')),
    
    # Frontline Agent Core APIs (from core.Fronline_agent)
    path('api/frontline/', include('core.Fronline_agent.urls')),
    
    # Marketing Agent
    path('marketing/', include('marketing_agent.urls')),
    
    # Simple token tracking (root level - /token?t=TOKEN for opens, /token?t=TOKEN&url=... for clicks)
    path('token/', views_email_tracking.simple_track_open, name='root_simple_track_open'),
    path('token/<str:tracking_token>/', views_email_tracking.simple_track_click, name='root_simple_track_click'),
    
    # API Routes
    path('api/', include('api.urls')),
    
    # Project Manager API endpoints
    path('api/project-manager/', include('core.api_urls')),

    path('', user_login, name='home'),  # Home redirects to login
]