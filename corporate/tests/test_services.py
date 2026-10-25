"""
Tests for corporate.services.
"""

import hashlib
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def make_company(legal_name="Acme Corp"):
    from accounts.models import Company

    return Company.objects.create(
        legal_name=legal_name,
        display_name=legal_name,
        country="US",
        status=Company.Status.VERIFIED,
    )


def make_user(email="user@example.com", full_name="Test User"):
    from accounts.models import User

    return User.objects.create_user(email=email, password="pass", full_name=full_name)


def make_member(user=None, company=None, role="buyer"):
    from accounts.models import CompanyMember

    if user is None:
        user = make_user(email=f"member_{timezone.now().timestamp()}@example.com")
    if company is None:
        company = make_company(legal_name=f"Co {timezone.now().timestamp()}")
    return CompanyMember.objects.create(user=user, company=company, role=role)


# ---------------------------------------------------------------------------
# invite_member
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_invite_member_creates_hashed_token():
    """Raw token must not be stored; only the SHA-256 hash is persisted."""
    from corporate.services import invite_member

    company = make_company("Invite Co")
    inviter = make_user("inviter@example.com")

    raw_token, invitation = invite_member(
        company=company,
        email="new@example.com",
        role="buyer",
        invited_by=inviter,
    )

    # Raw token is returned but must not be in the DB
    assert raw_token
    assert invitation.token_hash != raw_token

    # Verify the stored hash matches SHA-256(raw_token)
    expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    assert invitation.token_hash == expected_hash
    assert len(invitation.token_hash) == 64


@pytest.mark.django_db
def test_invite_member_email_lowercased():
    from corporate.services import invite_member

    company = make_company("Case Co")
    inviter = make_user("inviter2@example.com")

    _, invitation = invite_member(
        company=company,
        email="UPPER@EXAMPLE.COM",
        role="buyer",
        invited_by=inviter,
    )
    assert invitation.email == "upper@example.com"


# ---------------------------------------------------------------------------
# accept_invitation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_accept_invitation_creates_company_member():
    from corporate.services import accept_invitation, invite_member

    company = make_company("Accept Co")
    inviter = make_user("accept_inviter@example.com")
    accepter = make_user("accepter@example.com")

    raw_token, invitation = invite_member(
        company=company,
        email=accepter.email,
        role="buyer",
        invited_by=inviter,
    )

    member = accept_invitation(token=raw_token, user=accepter)

    assert member.user == accepter
    assert member.company == company
    assert member.role == "buyer"

    invitation.refresh_from_db()
    assert invitation.accepted_at is not None


@pytest.mark.django_db
def test_accept_invitation_fails_for_expired_token():
    from rest_framework.exceptions import ValidationError

    from corporate.models import Invitation
    from corporate.services import _hash_token, accept_invitation

    import secrets

    company = make_company("Expired Co")
    inviter = make_user("exp_inviter@example.com")
    user = make_user("exp_user@example.com")

    raw_token = secrets.token_urlsafe(32)
    Invitation.objects.create(
        company=company,
        email=user.email,
        role="buyer",
        token_hash=_hash_token(raw_token),
        invited_by=inviter,
        expires_at=timezone.now() - timedelta(days=1),  # expired
    )

    with pytest.raises(ValidationError, match="expired"):
        accept_invitation(token=raw_token, user=user)


@pytest.mark.django_db
def test_accept_invitation_fails_for_invalid_token():
    from rest_framework.exceptions import ValidationError

    from corporate.services import accept_invitation

    user = make_user("invalid_tok@example.com")

    with pytest.raises(ValidationError, match="Invalid"):
        accept_invitation(token="completely-wrong-token", user=user)


# ---------------------------------------------------------------------------
# check_budget
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_check_budget_passes_when_under_limit():
    from corporate.models import Budget, OrderLimit
    from corporate.services import check_budget

    company = make_company("Budget Co Under")
    user = make_user("budget_under@example.com")
    member = make_member(user=user, company=company)

    today = timezone.now().date()
    period_start = today.replace(day=1)

    # Set a generous budget
    Budget.objects.create(
        member=member,
        period_start=period_start,
        period="month",
        amount=Decimal("10000.00"),
    )
    OrderLimit.objects.create(member=member, max_order_amount=Decimal("5000.00"))

    allowed, reason = check_budget(member, Decimal("100.00"))
    assert allowed is True
    assert reason == "OK"


@pytest.mark.django_db
def test_check_budget_fails_closed_when_over_order_limit():
    from corporate.models import OrderLimit
    from corporate.services import check_budget

    company = make_company("Order Limit Co")
    user = make_user("orderlimit@example.com")
    member = make_member(user=user, company=company)

    OrderLimit.objects.create(member=member, max_order_amount=Decimal("50.00"))

    allowed, reason = check_budget(member, Decimal("100.00"))
    assert allowed is False
    assert reason == "Exceeds order limit"


@pytest.mark.django_db
def test_check_budget_fails_closed_when_budget_exceeded():
    from corporate.models import Budget
    from corporate.services import check_budget

    company = make_company("Budget Exceeded Co")
    user = make_user("budgetexceeded@example.com")
    member = make_member(user=user, company=company)

    today = timezone.now().date()
    period_start = today.replace(day=1)

    # Set a tiny budget
    Budget.objects.create(
        member=member,
        period_start=period_start,
        period="month",
        amount=Decimal("10.00"),
    )

    allowed, reason = check_budget(member, Decimal("9999.00"))
    assert allowed is False
    assert reason == "Exceeds monthly budget"


@pytest.mark.django_db
def test_check_budget_no_budget_set_returns_true():
    from corporate.services import check_budget

    company = make_company("No Budget Co")
    user = make_user("nobudget@example.com")
    member = make_member(user=user, company=company)

    allowed, reason = check_budget(member, Decimal("999.00"))
    assert allowed is True
    assert reason == "No budget set"


def test_check_budget_returns_false_on_any_exception():
    """Fail-closed: if an unexpected exception occurs, return (False, 'Budget check failed')."""
    from corporate.services import check_budget

    # Pass a non-member object to trigger an exception path
    fake_member = MagicMock()
    fake_member.user = None
    fake_member.company = None

    with patch("corporate.services.OrderLimit") as MockOrderLimit:
        MockOrderLimit.objects.get.side_effect = RuntimeError("Database exploded")
        allowed, reason = check_budget(fake_member, Decimal("100.00"))

    assert allowed is False
    assert reason == "Budget check failed"


# ---------------------------------------------------------------------------
# request_approval + notify
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_request_approval_notifies_managers():
    from corporate.models import ApprovalRequest
    from corporate.services import request_approval

    company = make_company("Approval Co")
    requester = make_user("requester@example.com")
    manager_user = make_user("manager@example.com")

    make_member(user=requester, company=company, role="buyer")
    make_member(user=manager_user, company=company, role="manager")

    with patch("corporate.services.notify") as mock_notify:
        approval = request_approval(
            company=company,
            requested_by=requester,
            subject_type="checkout",
            amount=Decimal("500.00"),
        )

    assert approval.status == ApprovalRequest.Status.PENDING
    assert approval.company == company
    assert approval.requested_by == requester

    # Should have notified the manager
    mock_notify.assert_called()
    notified_users = [call.args[0] for call in mock_notify.call_args_list]
    assert manager_user in notified_users


# ---------------------------------------------------------------------------
# decide_approval
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_decide_approval_sets_status_and_notifies_requester():
    from corporate.models import ApprovalRequest
    from corporate.services import decide_approval, request_approval

    company = make_company("Decide Co")
    requester = make_user("decide_requester@example.com")
    approver_user = make_user("decide_approver@example.com")

    make_member(user=requester, company=company, role="buyer")
    make_member(user=approver_user, company=company, role="manager")

    with patch("corporate.services.notify"):
        approval = request_approval(
            company=company,
            requested_by=requester,
            subject_type="checkout",
            amount=Decimal("200.00"),
        )

    with patch("corporate.services.notify") as mock_notify:
        result = decide_approval(
            approval_request=approval,
            approver=approver_user,
            approved=True,
            note="Looks good",
        )

    assert result.status == ApprovalRequest.Status.APPROVED
    assert result.approver == approver_user
    assert result.note == "Looks good"
    assert result.decided_at is not None

    # Should have notified the requester
    mock_notify.assert_called_once()
    assert mock_notify.call_args.args[0] == requester


@pytest.mark.django_db
def test_decide_approval_rejected_sets_rejected_status():
    from corporate.models import ApprovalRequest
    from corporate.services import decide_approval, request_approval

    company = make_company("Reject Co")
    requester = make_user("reject_req@example.com")
    approver_user = make_user("reject_apr@example.com")

    make_member(user=requester, company=company, role="buyer")
    make_member(user=approver_user, company=company, role="owner")

    with patch("corporate.services.notify"):
        approval = request_approval(
            company=company,
            requested_by=requester,
            subject_type="listing_publish",
        )

    with patch("corporate.services.notify"):
        result = decide_approval(
            approval_request=approval,
            approver=approver_user,
            approved=False,
            note="Denied",
        )

    assert result.status == ApprovalRequest.Status.REJECTED
