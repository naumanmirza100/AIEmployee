from django.urls import path
from . import views

urlpatterns = [
    path('', views.marketing_dashboard, name='marketing_dashboard'),
    path('agents/', views.marketing_agents_test, name='marketing_agents_test'),
    path('api/qa/', views.test_marketing_qa, name='test_marketing_qa'),
    path('api/market-research/', views.test_market_research, name='test_market_research'),
]

