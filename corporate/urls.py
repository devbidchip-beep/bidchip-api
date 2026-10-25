"""
Corporate URL configuration.
"""

from django.urls import path

from .views import (
    AcceptInvitationView,
    ApprovalDecideView,
    ApprovalRequestListView,
    BudgetListCreateView,
    InviteMemberView,
    MemberListView,
    OrderLimitView,
    ShipToAssignmentDeleteView,
    ShipToAssignmentListCreateView,
    SpendingReportView,
    SuspendMemberView,
)

urlpatterns = [
    path("invite/", InviteMemberView.as_view()),
    path("accept-invitation/", AcceptInvitationView.as_view()),
    path("members/", MemberListView.as_view()),
    path("members/<uuid:pk>/suspend/", SuspendMemberView.as_view()),
    path("budgets/", BudgetListCreateView.as_view()),
    path("limits/<uuid:member_id>/", OrderLimitView.as_view()),
    path("approvals/", ApprovalRequestListView.as_view()),
    path("approvals/<uuid:pk>/decide/", ApprovalDecideView.as_view()),
    path("spending/", SpendingReportView.as_view()),
    path("ship-to/", ShipToAssignmentListCreateView.as_view()),
    path("ship-to/<uuid:pk>/", ShipToAssignmentDeleteView.as_view()),
]
