from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('contact/', views.contact, name='contact'),
    # Keep legacy form action working without changing HTML
    path('send-email.php', views.contact, name='legacy_contact'),
]
