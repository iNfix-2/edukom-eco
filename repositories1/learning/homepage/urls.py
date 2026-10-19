from django.urls import path
from . import views

urlpatterns = [
    path('', views.homepage, name="homepage"),
    path('about/', views.about, name="about"),
    path('contact/', views.contact, name="contact"),
    path('Get_a_tutor', views.get_a_tutor, name="GetATutor"),
    path('FAQs', views.faq, name="faq"),
    path('guardians/', views.ViewGuardians, name="guardians"),
    path('guardian/<uuid:uid>', views.ViewGuardian, name="guardian"),
    path('succes_form/<uuid:uid>/', views.succes_form, name="succes_form"),
    path('blog/', views.blog_list, name="blog_list"),
    path('blog/create/', views.create_blog, name="create_blog"),
    path('blog/<slug:slug>/edit/', views.edit_blog, name="edit_blog"),
    path('blog/<slug:slug>/', views.blog_detail, name="blog_detail"),
    path('dashboard/', views.admin_dashboard, name="admin_dashboard"),
    path('blog/<slug:slug>/delete/', views.delete_blog, name="delete_blog"),
    path('blog/<slug:slug>/comment/', views.add_comment, name="add_comment"),
    path('blog/<slug:slug>/like/', views.toggle_like, name="toggle_like"),
    path('testimonial/add/', views.add_testimonial, name="add_testimonial"),
    ]
