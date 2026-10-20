from django.urls import path
from . import views

app_name = 'automations'

urlpatterns = [
    # Admin Operations Command Center
    path('dashboard/', views.automations_dashboard_view, name='dashboard'),
    path('trigger/', views.trigger_reminders_now_view, name='trigger_now'),
    path('test-send/', views.test_send_message_view, name='test_send'),

    # Hands-Free Background Cron Trigger Endpoint
    path('cron/run-reminders/', views.cron_run_reminders_view, name='cron_run_reminders'),

    # Inbound Webhook for Twilio / Meta WhatsApp Business
    path('webhook/whatsapp/inbound/', views.whatsapp_inbound_webhook_view, name='whatsapp_inbound'),

    # NDPR Notification & Privacy Preferences
    path('preferences/', views.notification_preferences_view, name='preferences'),
]
