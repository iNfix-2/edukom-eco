from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    # Public Client Facing
    path('invoice/<uuid:invoice_id>/', views.invoice_checkout_view, name='checkout'),
    path('invoice/<uuid:invoice_id>/pay/', views.initialize_payment_view, name='initialize_payment'),
    path('callback/', views.payment_callback_view, name='payment_callback'),
    
    # Webhooks (CSRF Exempt, HMAC-SHA512 Verified)
    path('webhook/paystack/', views.paystack_webhook, name='paystack_webhook'),
    path('webhook/flutterwave/', views.flutterwave_webhook, name='flutterwave_webhook'),
]
