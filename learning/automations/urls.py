from django.urls import path
from . import views

app_name = 'automations'

urlpatterns = [
    # Inbound Webhook for Twilio / Meta WhatsApp Business
    path('webhook/whatsapp/inbound/', views.whatsapp_inbound_webhook_view, name='whatsapp_inbound'),

    # NDPR Notification & Privacy Preferences
    path('preferences/', views.notification_preferences_view, name='preferences'),
]
