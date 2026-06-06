from django.urls import path
from .views import *

urlpatterns = [
    path('submit/', create_ticket_view, name='create_ticket'),
    path('dashboard/', ticket_dashboard_view, name='ticket_dashboard'),
    path('<uuid:ticket_id>/', ticket_detail_view, name='ticket_detail'),
    path('dispatch/', dispatch_dashboard_view, name='dispatch_dashboard'),  # Supervisor Console
    path('workspace/', agent_workspace_view, name='agent_workspace'),
]