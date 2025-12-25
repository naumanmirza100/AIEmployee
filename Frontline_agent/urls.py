from django.urls import path
from . import views

urlpatterns = [
    path('', views.frontline_dashboard, name='frontline_dashboard'),
    
    # Knowledge Q&A Agent
    path('api/knowledge-qa/', views.knowledge_qa, name='frontline_knowledge_qa'),
    
    # Ticket Triage & Auto-resolution Agent
    path('api/tickets/', views.list_tickets, name='frontline_list_tickets'),
    path('api/tickets/create/', views.create_ticket, name='frontline_create_ticket'),
    path('api/tickets/<int:ticket_id>/auto-resolve/', views.auto_resolve_ticket, name='frontline_auto_resolve_ticket'),
    
    # Proactive Notification & Follow-up Agent
    path('api/notifications/', views.list_notifications, name='frontline_list_notifications'),
    path('api/notifications/<int:notification_id>/read/', views.mark_notification_read, name='frontline_mark_notification_read'),
    
    # Workflow / SOP Runner Agent
    path('api/workflows/execute/', views.execute_workflow, name='frontline_execute_workflow'),
    
    # Meeting Scheduling Agent
    path('api/meetings/schedule/', views.schedule_meeting, name='frontline_schedule_meeting'),
    
    # Document Processing Agent
    path('api/documents/upload/', views.upload_document, name='frontline_upload_document'),
    
    # Analytics & Dashboard Agent
    path('api/analytics/', views.get_analytics, name='frontline_get_analytics'),
]

