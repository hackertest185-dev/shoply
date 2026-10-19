"""services/payment_service.py"""
import stripe
from app.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


async def create_payment_intent(amount_cents: int, currency: str = "usd") -> dict:
    """
    Create a Stripe PaymentIntent server-side.
    Amount is always calculated server-side — never trusted from client.
    Returns clientSecret for Stripe.js to complete payment.
    """
    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=currency,
            automatic_payment_methods={"enabled": True},
        )
    except stripe.error.AuthenticationError as exc:
        raise ValueError("STRIPE_AUTH_ERROR") from exc
    except stripe.error.StripeError as exc:
        raise ValueError("STRIPE_ERROR") from exc
    return {
        "client_secret":     intent.client_secret,
        "payment_intent_id": intent.id,
        "amount":            intent.amount,
        "currency":          intent.currency,
    }


async def verify_payment_intent(payment_intent_id: str) -> bool:
    """
    Verify payment succeeded server-side via Stripe API.
    NEVER trust client-reported payment status.
    """
    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
    except stripe.error.AuthenticationError as exc:
        raise ValueError("STRIPE_AUTH_ERROR") from exc
    except stripe.error.StripeError as exc:
        raise ValueError("STRIPE_ERROR") from exc
    return intent.status == "succeeded"


async def create_refund(payment_intent_id: str, amount_cents: int) -> dict:
    refund = stripe.Refund.create(
        payment_intent=payment_intent_id,
        amount=amount_cents,
    )
    return {"refund_id": refund.id, "status": refund.status, "amount": refund.amount}


def verify_webhook_signature(payload: bytes, sig_header: str) -> dict:
    """
    Validate Stripe webhook signature before processing any event.
    Raises stripe.error.SignatureVerificationError on failure.
    """
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )
