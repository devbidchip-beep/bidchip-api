"""
Accounts URL configuration.
"""

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="register"),
    path("me/", views.MeView.as_view(), name="me"),
    path("companies/", views.CompanyListCreateView.as_view(), name="company-list"),
    path("companies/<uuid:pk>/", views.CompanyDetailView.as_view(), name="company-detail"),
    path(
        "companies/<uuid:company_pk>/members/",
        views.CompanyMemberListView.as_view(),
        name="company-member-list",
    ),
]
