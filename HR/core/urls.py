from django.urls import path
from . import views

urlpatterns = [
    path('', views.gateway_home, name='gateway_home'),
    path('hr/', views.hr_home, name='home'),
    path('contact/', views.contact, name='contact'),
    path('send-email.php', views.contact, name='legacy_contact'),
    path('learning/', views.learning_redirect, name='learning_redirect'),
    path('robots.txt', views.robots_txt, name='robots_txt'),
    path('sitemap.xml', views.sitemap_xml, name='sitemap_xml'),
]
