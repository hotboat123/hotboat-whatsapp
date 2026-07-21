"""
Transbank Webpay Plus integration for HotBoat.

Creates transactions directly against Transbank (no WooCommerce hop) and
returns the token/url the customer needs to be redirected to. See
app/booking/router.py's `_create_transbank_payment()` for how this is wired
into the booking flow, and app/payment/transbank_confirm.py for how a
completed payment is reconciled back into the booking tables.

Defaults to Transbank's own published integration/testing credentials —
nothing here can charge real money unless TRANSBANK_ENVIRONMENT=production
is set explicitly, at which point TRANSBANK_COMMERCE_CODE and
TRANSBANK_API_KEY (the real ones, same values WooCommerce's Webpay plugin
already uses) are required.
"""
import os

from transbank.webpay.webpay_plus.transaction import Transaction
from transbank.common.options import WebpayOptions
from transbank.common.integration_type import IntegrationType
from transbank.common.integration_commerce_codes import IntegrationCommerceCodes
from transbank.common.integration_api_keys import IntegrationApiKeys


def _transaction() -> Transaction:
    if os.getenv("TRANSBANK_ENVIRONMENT") == "production":
        return Transaction(WebpayOptions(
            os.environ["TRANSBANK_COMMERCE_CODE"],
            os.environ["TRANSBANK_API_KEY"],
            IntegrationType.LIVE,
        ))
    return Transaction(WebpayOptions(
        IntegrationCommerceCodes.WEBPAY_PLUS,
        IntegrationApiKeys.WEBPAY,
        IntegrationType.TEST,
    ))


def create_transaction(buy_order: str, session_id: str, amount: int, return_url: str) -> dict:
    """Starts a Webpay Plus transaction. Returns {'token': ..., 'url': ...} —
    the customer's browser must POST token_ws=<token> to <url> (a plain GET
    redirect isn't enough; see /pagar/tbk in router.py)."""
    return _transaction().create(buy_order[:26], session_id[:61], amount, return_url)


def commit_transaction(token: str) -> dict:
    """Confirms a Webpay Plus transaction after the customer completes (or
    cancels) payment on Transbank's page. Returns Transbank's full response
    dict — response_code == 0 and status == 'AUTHORIZED' means approved."""
    return _transaction().commit(token)
