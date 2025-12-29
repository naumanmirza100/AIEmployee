"""
URL Configuration for Frontline Agent APIs
"""
from django.urls import path
from . import views

app_name = 'frontline_agent'

urlpatterns = [
    # Knowledge base APIs
    path('api/knowledge/', views.knowledge_api, name='knowledge_api'),
    path('api/knowledge/search/', views.search_knowledge_api, name='search_knowledge_api'),
    
    # Ticket APIs
    path('api/ticket/', views.create_ticket_api, name='create_ticket_api'),
    path('api/ticket/classify/', views.ticket_classification_api, name='ticket_classification_api'),
]

