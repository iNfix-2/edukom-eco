from django.urls import path
from . import views

urlpatterns = [
    path('Join', views.become_a_tutor, name="BecomeATutor"),
    path('', views.community, name="community"),
    path('succes_form/<uuid:uid>/', views.succes_form, name="tutor_succes_form")
]