from django.urls import path
from . import views

urlpatterns = [
    path('Join', views.become_a_tutor, name="become_a_tutor"),
    path('join/', views.become_a_tutor, name="become_a_tutor_join"),
    path('Join/', views.become_a_tutor, name="BecomeATutor_Join"),
    path('', views.community, name="community"),
    path('succes_form/<uuid:uid>/', views.succes_form, name="tutor_succes_form")
]