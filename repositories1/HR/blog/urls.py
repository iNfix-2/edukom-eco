from django.urls import path
from . import views

urlpatterns = [
    path('', views.post_list, name='blog_list'),
    path('category/<slug:category_slug>/', views.post_list, name='blog_category'),
    path('tag/<slug:tag_slug>/', views.post_list, name='blog_tag'),
    path('categories/', views.category_manage, name='blog_categories'),
    path('categories/delete/<slug:slug>/', views.category_delete, name='blog_category_delete'),
    path('tags/delete/<slug:slug>/', views.tag_delete, name='blog_tag_delete'),
    path('manage/', views.post_manage_list, name='blog_manage'),
    path('new/', views.post_create, name='blog_new'),
    path('edit/<slug:slug>/', views.post_edit, name='blog_edit'),
    path('delete/<slug:slug>/', views.post_delete, name='blog_delete'),
    path('<slug:slug>/', views.post_detail, name='blog_detail'),
]
