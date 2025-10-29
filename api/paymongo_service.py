"""
PayMongo integration service for handling payments
"""

import requests
import base64
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class PayMongoService:
    def __init__(self):
        self.base_url = settings.PAYMONGO_BASE_URL
        self.secret_key = settings.PAYMONGO_SECRET_KEY
        self.public_key = settings.PAYMONGO_PUBLIC_KEY

    def _get_auth_header(self):
        """Get basic authentication header for PayMongo API"""
        auth_string = f"{self.secret_key}:"
        auth_bytes = auth_string.encode("ascii")
        auth_b64 = base64.b64encode(auth_bytes).decode("ascii")
        return f"Basic {auth_b64}"

    def _make_request(self, method, endpoint, data=None):
        """Make HTTP request to PayMongo API"""
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": self._get_auth_header(),
            "Content-Type": "application/json",
        }

        try:
            if method.upper() == "POST":
                response = requests.post(url, json=data, headers=headers)
            elif method.upper() == "GET":
                response = requests.get(url, headers=headers)
            elif method.upper() == "PUT":
                response = requests.put(url, json=data, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"PayMongo API request failed: {e}")
            if hasattr(e.response, "json"):
                try:
                    error_data = e.response.json()
                    logger.error(f"PayMongo error response: {error_data}")
                    return {"error": error_data}
                except:
                    pass
            raise e

    def get_checkout_session(self, session_id):
        """
        Retrieve checkout session by ID

        Args:
            session_id: PayMongo checkout session ID

        Returns:
            Checkout session data
        """
        return self._make_request("GET", f"/checkout_sessions/{session_id}")

    def create_checkout_session(
        self,
        line_items,
        success_url,
        cancel_url,
        description="Order Payment",
        metadata=None,
    ):
        """
        Create a checkout session for hosted payment

        Args:
            line_items: List of items with name, amount, currency, quantity
            success_url: URL to redirect on successful payment
            cancel_url: URL to redirect on cancelled payment
            description: Session description
            metadata: Additional metadata to attach to the session

        Returns:
            Checkout session data
        """
        payload = {
            "data": {
                "attributes": {
                    "send_email_receipt": True,
                    "show_description": True,
                    "show_line_items": True,
                    "description": description,
                    "line_items": line_items,
                    "payment_method_types": ["card", "gcash", "paymaya", "dob"],
                    "success_url": success_url,
                    "cancel_url": cancel_url,
                }
            }
        }

        # Add metadata if provided
        if metadata:
            payload["data"]["attributes"]["metadata"] = metadata

        return self._make_request("POST", "/checkout_sessions", payload)

    def create_qr_ph(self, amount, currency="PHP", description="QR Payment"):
        """
        Create a static QR Ph code for payment

        Args:
            amount: Amount in centavos
            currency: Currency code (default: PHP)
            description: Payment description

        Returns:
            QR Ph data from PayMongo
        """
        if isinstance(amount, (float, Decimal)):
            amount = int(amount * 100)

        payload = {
            "data": {
                "attributes": {
                    "amount": amount,
                    "currency": currency,
                    "description": description,
                }
            }
        }

        return self._make_request("POST", "/qr_ph", payload)

    def create_customer(self, email, first_name=None, last_name=None, phone=None):
        """
        Create a customer for recurring payments

        Args:
            email: Customer email
            first_name: Customer first name
            last_name: Customer last name
            phone: Customer phone number

        Returns:
            Customer data from PayMongo
        """
        payload = {
            "data": {
                "attributes": {
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone": phone,
                }
            }
        }

        return self._make_request("POST", "/customers", payload)

    def create_refund(self, payment_id, amount, reason="requested_by_customer"):
        """
        Create a refund for a payment

        Args:
            payment_id: PayMongo payment ID
            amount: Refund amount in centavos
            reason: Refund reason

        Returns:
            Refund data from PayMongo
        """
        if isinstance(amount, (float, Decimal)):
            amount = int(amount * 100)

        payload = {
            "data": {
                "attributes": {
                    "amount": amount,
                    "payment": payment_id,
                    "reason": reason,
                }
            }
        }

        return self._make_request("POST", "/refunds", payload)


def update_order_payment_status(order, payment_intent_data):
    """
    Update order payment status based on PayMongo payment intent

    Args:
        order: Order instance
        payment_intent_data: Payment intent data from PayMongo
    """
    from .models import Order

    payment_status = (
        payment_intent_data.get("data", {}).get("attributes", {}).get("status")
    )

    if payment_status == "succeeded":
        order.payment_status = "paid"
        order.paid_at = timezone.now()
        if order.status == "to_pay":
            order.status = "to_ship"
    elif payment_status == "processing":
        order.payment_status = "pending"
    elif payment_status in ["failed", "cancelled"]:
        order.payment_status = "failed"

    order.save()
    return order
