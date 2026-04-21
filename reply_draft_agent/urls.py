from django.urls import path
from . import views

app_name = 'reply_draft_agent'

urlpatterns = [
    path('pending-replies/', views.list_pending_replies, name='list_pending_replies'),
    path('drafts/', views.list_drafts, name='list_drafts'),
    path('drafts/generate/', views.generate_draft, name='generate_draft'),
    path('drafts/<int:draft_id>/regenerate/', views.regenerate_draft, name='regenerate_draft'),
    path('drafts/<int:draft_id>/approve/', views.approve_draft, name='approve_draft'),
    path('drafts/<int:draft_id>/reject/', views.reject_draft, name='reject_draft'),
    path('drafts/<int:draft_id>/send/', views.send_draft, name='send_draft'),
]
