"""
Payments views: CheckoutView, StripeConnectOnboardView, StripeConnectReturnView.
"""

import logging
from decimal import Decimal

import stripe
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class CheckoutView(APIView):
    """
    POST /api/v1/payments/checkout/

    Body: { listing_id, awards: [award_id, ...], ship_to_id, payment_method,
            card_funding, billing_state, po_number }

    1. Validate all awards belong to the buyer's listing
    2. Call price_order() — server-side only
    3. Create Order via orders.service.create_order_from_awards()
    4. Create Stripe PaymentIntent (card) or return wire instructions
    5. Return { order_id, client_secret (card), grand_total }
    """

    def post(self, request):
        stripe.api_key = settings.STRIPE_SECRET_KEY

        from accounts.models import Address
        from bidding.models import Award
        from listings.models import Listing
        from orders.service import create_order_from_awards
        from payments.models import Payment
        from pricing.service import price_order

        data = request.data
        listing_id = data.get("listing_id")
        award_ids = data.get("awards", [])
        ship_to_id = data.get("ship_to_id")
        payment_method = data.get("payment_method", "card")
        card_funding = data.get("card_funding", "debit")
        billing_state = data.get("billing_state", "")
        po_number = data.get("po_number", "")
        shipping_estimate = Decimal(str(data.get("shipping_estimate", "0.00")))

        # Validate listing
        try:
            listing = Listing.objects.get(id=listing_id, buyer_company=request.user.memberships.filter(status="active").first().company)
        except (Listing.DoesNotExist, AttributeError):
            return Response({"error": "Listing not found."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate awards
        awards = Award.objects.filter(id__in=award_ids, line__listing=listing).select_related(
            "bid__supplier_company", "line"
        )
        if awards.count() != len(award_ids):
            return Response({"error": "Invalid awards."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate ship_to
        try:
            ship_to = Address.objects.get(id=ship_to_id, company=listing.buyer_company)
        except Address.DoesNotExist:
            return Response({"error": "Address not found."}, status=status.HTTP_400_BAD_REQUEST)

        # Create order (all server-side pricing)
        order = create_order_from_awards(
            awards=list(awards),
            buyer_company=listing.buyer_company,
            placed_by=request.user,
            ship_to=ship_to,
            shipping_estimate=shipping_estimate,
            payment_method=payment_method,
            card_funding=card_funding,
            billing_state=billing_state,
            po_number=po_number,
        )

        response_data = {
            "order_id": str(order.id),
            "grand_total": str(order.grand_total),
        }

        if payment_method == "card":
            # Create Stripe PaymentIntent
            intent = stripe.PaymentIntent.create(
                amount=int(order.grand_total * 100),  # cents
                currency=order.currency.lower(),
                metadata={
                    "order_id": str(order.id),
                    "order_number": order.number,
                },
            )
            Payment.objects.create(
                order=order,
                method=Payment.Method.CARD,
                card_funding=card_funding,
                billing_state=billing_state,
                surcharge_amount=order.card_surcharge,
                stripe_payment_intent=intent.id,
                amount=order.grand_total,
                currency=order.currency,
            )
            response_data["client_secret"] = intent.client_secret

        elif payment_method == "wire":
            Payment.objects.create(
                order=order,
                method=Payment.Method.WIRE,
                amount=order.grand_total,
                currency=order.currency,
            )
            response_data["wire_instructions"] = {
                "bank": "Example Bank",
                "account": "123456789",
                "routing": "021000021",
                "reference": order.number,
            }

        return Response(response_data, status=status.HTTP_201_CREATED)


class StripeConnectOnboardView(APIView):
    """
    POST /api/v1/payments/stripe/connect/

    Creates or retrieves Stripe Express account for the supplier's company.
    Returns { account_link_url } for the Express onboarding flow.
    """

    def post(self, request):
        stripe.api_key = settings.STRIPE_SECRET_KEY

        from accounts.models import StripeAccount

        membership = request.user.memberships.filter(status="active").first()
        if not membership:
            return Response({"error": "No active company membership."}, status=status.HTTP_400_BAD_REQUEST)

        company = membership.company

        # Get or create Stripe account
        try:
            sa = StripeAccount.objects.get(company=company)
            stripe_account_id = sa.stripe_account_id
        except StripeAccount.DoesNotExist:
            account = stripe.Account.create(
                type="express",
                country=company.country or "US",
                email=request.user.email,
                metadata={"company_id": str(company.id)},
            )
            sa = StripeAccount.objects.create(
                company=company,
                stripe_account_id=account.id,
                account_type=StripeAccount.AccountType.EXPRESS,
                country=company.country or "US",
            )
            stripe_account_id = account.id

        # Create account link for onboarding
        account_link = stripe.AccountLink.create(
            account=stripe_account_id,
            refresh_url=request.build_absolute_uri("/api/v1/payments/stripe/connect/"),
            return_url=request.build_absolute_uri("/api/v1/payments/stripe/connect/return/"),
            type="account_onboarding",
        )

        return Response({"account_link_url": account_link.url})


class StripeConnectReturnView(APIView):
    """
    GET /api/v1/payments/stripe/connect/return/

    Called after supplier completes onboarding.
    Refreshes StripeAccount from Stripe API.
    """

    def get(self, request):
        stripe.api_key = settings.STRIPE_SECRET_KEY

        from accounts.models import StripeAccount

        membership = request.user.memberships.filter(status="active").first()
        if not membership:
            return Response({"error": "No active company membership."}, status=status.HTTP_400_BAD_REQUEST)

        company = membership.company

        try:
            sa = StripeAccount.objects.get(company=company)
        except StripeAccount.DoesNotExist:
            return Response({"error": "No Stripe account found."}, status=status.HTTP_404_NOT_FOUND)

        # Refresh from Stripe API
        account = stripe.Account.retrieve(sa.stripe_account_id)
        sa.charges_enabled = account.charges_enabled
        sa.payouts_enabled = account.payouts_enabled
        sa.details_submitted = account.details_submitted
        sa.raw_data = dict(account)
        if account.charges_enabled and account.payouts_enabled:
            sa.status = StripeAccount.Status.ACTIVE
        sa.save()

        return Response({
            "charges_enabled": sa.charges_enabled,
            "payouts_enabled": sa.payouts_enabled,
            "details_submitted": sa.details_submitted,
            "status": sa.status,
        })
