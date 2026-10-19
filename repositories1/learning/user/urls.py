from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [

    path('Login/', auth_views.LoginView.as_view(template_name="account/login.html"), name="login" ),
    path('Logout/', auth_views.LogoutView.as_view(), name="logout" ),
    path('list',views.GuardianListView, name="listGuardian"),
    path('detail/<uuid:uid>',views.GuardianDetailView, name="detailGuardian"),
    path('tutor/detail/<uuid:uid>',views.TutorDetailView, name="detailTutor")

]
