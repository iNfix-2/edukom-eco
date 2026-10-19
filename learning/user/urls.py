from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Smart Role-Based Dispatcher
    path('dashboard/', views.dashboard_dispatcher_view, name="dashboard_dispatcher"),

    # Role-Specific LMS Dashboards
    path('dashboard/student/', views.student_dashboard_view, name="dashboard_student"),
    path('dashboard/guardian/', views.guardian_dashboard_view, name="dashboard_guardian"),
    path('dashboard/tutor/', views.tutor_dashboard_view, name="dashboard_tutor"),
    path('dashboard/staff/', views.staff_dashboard_view, name="dashboard_staff"),
    path('dashboard/admin/', views.admin_dashboard_view, name="dashboard_admin"),

    # User Role Management & Profile Settings
    path('users/<int:user_id>/update-role/', views.update_user_role_view, name="update_user_role"),
    path('profile/edit/', views.profile_settings_view, name="profile_settings"),

    # Authentication & Registration (Canonical Lowercase)
    path('login/', auth_views.LoginView.as_view(template_name="account/login.html"), name="login"),
    path('logout/', auth_views.LogoutView.as_view(next_page='/'), name="logout"),
    path('register/', views.register_view, name="register"),

    # Compatibility Aliases (Capitalized)
    path('Login/', auth_views.LoginView.as_view(template_name="account/login.html")),
    path('Logout/', auth_views.LogoutView.as_view(next_page='/')),
    path('Register/', views.register_view),

    # Legacy views
    path('list', views.GuardianListView, name="listGuardian"),
    path('detail/<uuid:uid>', views.GuardianDetailView, name="detailGuardian"),
    path('tutor/detail/<uuid:uid>', views.TutorDetailView, name="detailTutor"),
]
