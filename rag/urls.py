from django.urls import path
from . import views

urlpatterns = [
    # ------------------------------------------------------------------
    # Authentification
    # ------------------------------------------------------------------
    path('login/',    views.login_view,    name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/',   views.logout_view,   name='logout'),

    # ------------------------------------------------------------------
    # Pages principales
    # ------------------------------------------------------------------
    path('',           views.chat_view,      name='chat'),
    path('documents/', views.documents_view, name='documents'),

    # ------------------------------------------------------------------
    # Actions sur documents
    # ------------------------------------------------------------------
    path('documents/<int:pk>/delete/', views.document_delete_view, name='document_delete'),

    # ------------------------------------------------------------------
    # API AJAX (appelée par le JavaScript du front)
    # ------------------------------------------------------------------
    path('api/chat/send/',                    views.chat_send_view,    name='chat_send'),
    path('api/upload/status/<str:task_id>/',  views.upload_status_view, name='upload_status'),

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------
    path('health/', views.health_check, name='health_check'),
]
