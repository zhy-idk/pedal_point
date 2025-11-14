from rest_framework.decorators import (
    api_view,
    permission_classes,
    parser_classes,
    renderer_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.renderers import BaseRenderer, JSONRenderer, BrowsableAPIRenderer
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.db import transaction
from django.db.models import Count, Max, Q
from django.core.paginator import Paginator
from datetime import datetime
from .models import *
from .serializer import *
from django.shortcuts import get_object_or_404
from .realtime_utils import (
    send_cart_update,
    send_order_update,
    send_inventory_update,
    send_notification,
)
from .utils import create_audit_log
import random
from django.conf import settings
from django.utils import timezone
import logging
import csv
import json
from typing import Any, Dict, List, Tuple
import requests
from decimal import Decimal
from .paymongo_service import PayMongoService

logger = logging.getLogger(__name__)

class CSVAttachmentRenderer(BaseRenderer):
    media_type = "text/csv"
    format = "csv"
    charset = "utf-8"
    render_style = "binary"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


SALE_PAYMENT_METHOD_MAP = {
    "cash_on_delivery": "cod",
    "cod": "cod",
    "cash": "cash",
    "card": "card",
    "gcash": "gcash",
    "paymaya": "paymaya",
    "bank_transfer": "bank_transfer",
    "dob": "paymongo",
    "grab_pay": "paymongo",
    "shopeepay": "paymongo",
    "qr_ph": "paymongo",
    "qrph": "paymongo",
    "paymongo": "paymongo",
}


def _map_payment_method(requested_method: str) -> str:
    normalized = (requested_method or "").lower()
    return SALE_PAYMENT_METHOD_MAP.get(normalized, "paymongo")


def _default_sale_type(mapped_method: str) -> str:
    if mapped_method == "cod":
        return "online_cod"
    if mapped_method == "cash":
        return "pos"
    return "online"


def _initial_payment_status(mapped_method: str) -> str:
    if mapped_method == "cod":
        return "cod_pending"
    if mapped_method == "cash":
        return "paid"
    return "pending"


def _decimal_amount(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _ensure_sale_for_order(order: Order) -> Sales:
    """
    Ensure an order has an associated Sales record populated with its items.
    """
    if getattr(order, "sale", None):
        return order.sale

    mapped_method = "cod" if getattr(order, "is_cod", False) else "paymongo"
    sale_type = _default_sale_type(mapped_method)
    payment_status = _initial_payment_status(mapped_method)
    notes = (order.notes or "").strip()

    sale = Sales.objects.create(
        user=order.user,
        total_amount=Decimal("0"),
        sale_type=sale_type,
        payment_status=payment_status,
        payment_method=mapped_method,
        notes=notes,
    )

    total_amount = Decimal("0")
    for item in order.items.select_related("product"):
        product = item.product
        product_price = _decimal_amount(product.price if product else 0)
        item_amount = product_price * item.quantity
        supplier_price = (
            _decimal_amount(product.supplier_price)
            if product and product.supplier_price is not None
            else None
        )

        SalesItem.objects.create(
            sales=sale,
            product=product,
            quantity_sold=item.quantity,
            amount=item_amount,
            supplier_price=supplier_price,
        )

        total_amount += item_amount

    sale.total_amount = total_amount
    sale.save(update_fields=["total_amount"])

    order.sale = sale
    order.save(update_fields=["sale"])
    return sale

BASIC_FALLBACK_PARTS: Dict[str, List[str]] = {
    "flat": ["tube", "inner tube", "patch kit"],
    "puncture": ["tube", "patch kit"],
    "brake": ["brake pad", "rotor"],
    "chain": ["chain", "quick link"],
}

KEYWORD_CATEGORY_MAP: Dict[str, List[str]] = {
    "tire": ["tires", "inner tubes", "tubes", "wheelset", "wheels"],
    "tube": ["tires", "inner tubes", "tubes"],
    "flat": ["tires", "inner tubes", "tubes"],
    "puncture": ["tires", "inner tubes", "tubes"],
    "brake": ["brakes", "rotors", "pads"],
    "chain": ["drivetrain", "chain", "cassette"],
    "gear": ["drivetrain", "derailleur"],
    "shift": ["drivetrain", "derailleur"],
    "noisy": ["brakes", "drivetrain"],
}

BASIC_ISSUE_PART_KEYWORDS: Dict[str, List[str]] = {
    "flat": ["tube", "inner tube", "patch", "sealant", "tire"],
    "puncture": ["tube", "patch", "tire"],
    "leak": ["tube", "sealant"],
    "soft": ["tube", "inner tube", "sealant"],
}

BIKE_TYPE_PREFERENCE_MAP: Dict[str, List[str]] = {
    "mountain": ["29", "27.5", "26", "31.6", "31.8", "35", "mtb", "trail"],
    "road": ["700", "700c", "25c", "27.2", "31.8", "road"],
    "hybrid": ["700", "700c", "28", "27.2", "31.8", "hybrid"],
    "bmx": ["20", "bmx", "25t"],
    "gravel": ["700", "650b", "27.2", "gravel"],
    "folding": ["20", "16", "28.6", "folding"],
    "kids": ["16", "14", "12", "kids"],
}

def _normalize_listing_price(listing: ProductListing) -> float:
    """Return the lowest available price for a listing."""
    if listing.price:
        try:
            return float(listing.price)
        except (TypeError, ValueError):
            pass

    variant_prices: List[float] = []
    for product in listing.products.all():
        try:
            variant_prices.append(float(product.price))
        except (TypeError, ValueError):
            continue

    return min(variant_prices) if variant_prices else 0.0


def _tokenize(text: str) -> List[str]:
    return [
        token
        for token in (
            "".join(ch if ch.isalnum() or ch == " " else " " for ch in text.lower())
        ).split()
        if len(token) > 2
    ]


def _score_listing(listing: ProductListing, query_tokens: List[str]) -> int:
    haystack_tokens = set(_tokenize(listing.name or ""))
    if listing.category and listing.category.name:
        haystack_tokens.update(_tokenize(listing.category.name))
    if listing.description:
        haystack_tokens.update(_tokenize(listing.description))

    score = 0
    for token in query_tokens:
        if token in haystack_tokens:
            score += 2
        else:
            if any(value.startswith(token[:4]) for value in haystack_tokens):
                score += 1

    return score


def _listing_search_text(listing: ProductListing) -> str:
    parts: List[str] = [
        listing.name or "",
        listing.description or "",
        listing.category.name if listing.category else "",
    ]
    for product in listing.products.all():
        parts.append(product.name or "")
        if product.variant_attribute:
            parts.append(product.variant_attribute)
    if hasattr(listing, "compatibility_attributes"):
        try:
            for attr in listing.compatibility_attributes.all():
                parts.append(getattr(attr, "display_name", "") or "")
                parts.append(getattr(attr, "value", "") or "")
        except Exception:
            pass
    return " ".join(parts).lower()


def _select_candidate_listings(issue: str, bike_type: str, limit: int = 12) -> List[Tuple[ProductListing, int]]:
    """Pick the most relevant listings for a repair issue using textual matches."""
    query_tokens = _tokenize(issue)
    normalized_bike_type = (bike_type or "").lower()

    primary_keywords: List[str] = []
    for token in query_tokens:
        primary_keywords.extend(KEYWORD_CATEGORY_MAP.get(token, []))
    primary_keywords = list(dict.fromkeys(primary_keywords))

    basic_part_keywords: List[str] = []
    for token in query_tokens:
        basic_part_keywords.extend(BASIC_ISSUE_PART_KEYWORDS.get(token, []))
    basic_part_keywords = list(dict.fromkeys(basic_part_keywords))

    fallback_basic: List[str] = []
    for token in query_tokens:
        fallback_basic.extend(BASIC_FALLBACK_PARTS.get(token, []))
    fallback_basic = list(dict.fromkeys(fallback_basic))

    size_tokens = [token for token in query_tokens if any(ch.isdigit() for ch in token)]
    size_tokens = list(dict.fromkeys(size_tokens))

    generic_keywords = [
        token for token in query_tokens if len(token) > 2 and token not in size_tokens
    ]
    generic_keywords = list(dict.fromkeys(generic_keywords))

    bike_keywords = BIKE_TYPE_PREFERENCE_MAP.get(normalized_bike_type, [])

    keyword_priority: List[Tuple[int, List[str]]] = []
    if basic_part_keywords:
        keyword_priority.append((0, basic_part_keywords))
    elif fallback_basic:
        keyword_priority.append((0, fallback_basic))

    if size_tokens:
        keyword_priority.append((1, size_tokens))

    if primary_keywords:
        keyword_priority.append((2, primary_keywords))

    if generic_keywords:
        keyword_priority.append((3, generic_keywords))

    if bike_keywords:
        keyword_priority.append((4, bike_keywords))

    listings_qs = (
        ProductListing.objects.filter(available=True)
        .select_related("category")
        .prefetch_related("products")
    )

    listing_texts: Dict[int, str] = {}
    for listing in listings_qs:
        listing_texts[listing.id] = _listing_search_text(listing)

    matched: List[Tuple[ProductListing, int]] = []
    seen_ids: set[int] = set()

    for weight, keywords in keyword_priority:
        for keyword in keywords:
            keyword = keyword.lower()
            if not keyword:
                continue
            for listing in listings_qs:
                if listing.id in seen_ids:
                    continue
                if keyword in listing_texts[listing.id]:
                    matched.append((listing, weight))
                    seen_ids.add(listing.id)
                    if len(matched) >= limit:
                        break
            if len(matched) >= limit:
                break
        if len(matched) >= limit:
            break

    if not matched:
        # Fallback: return most relevant categories or first listings
        for listing in listings_qs[:limit]:
            matched.append((listing, 99))

    matched.sort(key=lambda item: (item[1], _normalize_listing_price(item[0])))
    return matched[:limit]


def _format_inventory_for_prompt(
    candidates: List[Tuple[ProductListing, int]]
) -> Tuple[str, List[Dict[str, Any]]]:
    parts = []
    structured_entries: List[Dict[str, Any]] = []
    for idx, (listing, score) in enumerate(candidates, start=1):
        price = _normalize_listing_price(listing)
        entry = {
            "inventory_id": idx,
            "id": listing.id,
            "name": listing.name,
            "category": listing.category.name if listing.category else "General",
            "category_slug": listing.category.slug if listing.category else "products",
            "slug": listing.slug,
            "price": price,
            "product_url": f"{listing.category.slug if listing.category else 'products'}/{listing.slug}",
        }
        structured_entries.append(entry)
        parts.append(
            f"{idx}. {listing.name} | Category: {entry['category']} | "
            f"Price: ₱{price:,.0f} | Product URL: {entry['product_url']}"
        )
    context = (
        "\n".join(parts)
        if parts
        else "No closely matching inventory items were found."
    )
    return context, structured_entries


def _build_ai_prompt(
    issue: str,
    bike_type: str,
    inventory_context: str,
    preferred_sizes: List[str],
    initial_diagnosis: str,
    requested_parts: List[Dict[str, Any]],
) -> str:
    size_hint = ", ".join(preferred_sizes) if preferred_sizes else ""
    requested_json = json.dumps(requested_parts, ensure_ascii=False, indent=2)
    labor_reference = """
Recommended labor fee guide (choose the closest match):
- Bike Tuning ₱20 - ₱50
- Bolt Tightening & Minor Adjustments ₱20 - ₱50
- Brake Bleeding ₱50 - ₱80
- Wheel Alignment ₱50 - ₱100
- Parts Installation ₱50 - ₱150
- Rimset Alignment ₱150 - ₱200
- Fork Adjustment / Suspension Setup ₱250 - ₱350
- Full Bike Assembly ₱150 - ₱50
""".strip()
    return f"""
You are a PedalPoint bike shop staff member preparing a repair estimate. Act like a real mechanic: assume the most basic, likely problem unless the customer explicitly states otherwise, and keep the tone professional and friendly.

Customer details:
- Bike type: {bike_type}
- Reported issue: {issue}
{"- Common component sizes to prioritize: " + size_hint if size_hint else ""}

Available inventory (reference by inventory_id only):
{inventory_context}

Labor fee reference:
{labor_reference}

Earlier analysis suggested:
- Likely diagnosis: {initial_diagnosis or "Not provided"}
- Requested parts: {requested_json}

Return **valid JSON with no extra text** using exactly this structure:
{{
  "diagnosis": "2-3 sentence explanation of the likely issue using everyday language.",
  "recommended_parts": [
    {{
      "inventory_id": <number from the list above>,
      "notes": "Why this specific part is recommended and any quick install advice."
    }}
  ],
  "estimated_cost": {{
    "parts_subtotal": "Exact PHP price or range derived from the recommended parts",
    "labor": "Pick the most appropriate labor fee range from the reference list above",
    "total": "Estimated overall cost range"
  }},
  "next_steps": "Tell the rider to speak with a human PedalPoint staff member if they need clarification or scheduling help."
}}

Important rules:
- Only reference catalog items provided in the inventory list. Never invent a product or its size.
- Recommend at most 4 parts. Prioritize the simplest, most common fixes first (e.g., tubes for flat tires).
- If the customer explicitly wants a product that is NOT listed, set recommended_parts to [] and mention that we do not stock it yet.
- If nothing matches, keep recommended_parts empty but still provide a helpful diagnosis and next_steps.
"""


@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
def repair_estimator(request):
    """AI-backed repair estimator endpoint."""
    if request.method == "GET":
        try:
            estimate = RepairEstimate.objects.get(user=request.user)
            try:
                stored_sections = json.loads(estimate.ai_summary)
                if isinstance(stored_sections, str):
                    stored_sections = {"diagnosis": stored_sections}
            except (TypeError, json.JSONDecodeError):
                stored_sections = {"diagnosis": estimate.ai_summary or ""}

            return Response(
                {
                    "issue": estimate.issue,
                    "bike_type": estimate.bike_type,
                    "ai_sections": stored_sections,
                    "recommended_parts": estimate.recommendations or [],
                    "updated_at": estimate.updated_at,
                }
            )
        except RepairEstimate.DoesNotExist:
            return Response({"error": "No saved estimate found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        deleted, _ = RepairEstimate.objects.filter(user=request.user).delete()
        if deleted:
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({"error": "No saved estimate found."}, status=status.HTTP_404_NOT_FOUND)

    payload = request.data or {}
    issue = (payload.get("issue") or "").strip()
    bike_type = (payload.get("bike_type") or "").strip() or "Unknown"
    try:
        limit = int(payload.get("limit", 12))
    except (TypeError, ValueError):
        limit = 12
    limit = max(1, min(limit, 25))

    if len(issue) < 20:
        return Response(
            {"error": "Issue description must be at least 20 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    api_key = getattr(settings, "OPENROUTER_API_KEY", None)
    model = getattr(settings, "OPENROUTER_MODEL", "anthropic/claude-3-haiku")
    base_url = getattr(settings, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    if not api_key:
        return Response(
            {"error": "AI service not configured. Missing OPENROUTER_API_KEY."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        # Step 1: get initial AI proposal (parts requested)
        initial_response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": settings.FRONTEND_URL,
                "X-Title": "PedalPoint Repair Estimator",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a professional bike shop assistant for PedalPoint."},
                    {
                        "role": "user",
                        "content": (
                            "A customer described their bike problem.\n"
                            f"Bike type: {bike_type}\n"
                            f"Issue: {issue}\n"
                            "Identify the most likely specific parts needed (as simple JSON) before doing any pricing.\n"
                            "Your reply MUST be valid JSON with these keys:\n"
                            "{\n"
                            '  "likely_diagnosis": "Short natural language summary",\n'
                            '  "parts_requested": [\n'
                            "    {\n"
                            '      "name": "Desired part name",\n'
                            '      "attributes": "Relevant sizes or specs (if any)"\n'
                            "    }\n"
                            "  ]\n"
                            "}\n"
                        ),
                    },
                ],
                "temperature": 0.4,
            },
            timeout=20,
        )
        initial_response.raise_for_status()
        initial_data = initial_response.json()
        initial_text = (
            initial_data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )

        try:
            initial_json = json.loads(initial_text) if initial_text else {}
        except json.JSONDecodeError:
            logger.warning("Initial AI JSON parsing failed: %s", initial_text)
            initial_json = {}
        logger.info(
            "RepairEstimator initial AI analysis for user %s: %s",
            request.user.id if request.user.is_authenticated else "anonymous",
            json.dumps(initial_json, ensure_ascii=False),
        )

        requested_parts = initial_json.get("parts_requested", [])

        # Step 2: match requested parts via keyword search
        matched_candidates: List[Tuple[ProductListing, int]] = []
        if requested_parts:
            aggregated_keywords: List[str] = []
            for part in requested_parts:
                name = part.get("name", "")
                attrs = part.get("attributes", "")
                aggregated_keywords.extend(_tokenize(name))
                aggregated_keywords.extend(_tokenize(attrs))

            aggregated_keywords = list(dict.fromkeys(aggregated_keywords))
            matched_candidates = _select_candidate_listings(
                " ".join(aggregated_keywords) or issue, bike_type, limit=limit
            )
        else:
            matched_candidates = _select_candidate_listings(issue, bike_type, limit=limit)

        logger.info(
            "RepairEstimator matched catalog items (limit %s) for user %s: %s",
            limit,
            request.user.id if request.user.is_authenticated else "anonymous",
            [
                {
                    "id": listing.id,
                    "name": listing.name,
                    "category": listing.category.name if listing.category else "",
                }
                for listing, _ in matched_candidates
            ],
        )

        inventory_context, inventory_entries = _format_inventory_for_prompt(matched_candidates)
        bike_type_lower = (bike_type or "").lower()
        preferred_sizes = BIKE_TYPE_PREFERENCE_MAP.get(bike_type_lower, [])

        # Step 3: final recommendation prompt
        prompt = _build_ai_prompt(
            issue,
            bike_type,
            inventory_context,
            preferred_sizes,
            initial_json.get("likely_diagnosis", ""),
            requested_parts,
        )

        final_response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": settings.FRONTEND_URL,
                "X-Title": "PedalPoint Repair Estimator",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are a professional bike shop assistant for PedalPoint."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.5,
            },
            timeout=20,
        )
        final_response.raise_for_status()
        final_data = final_response.json()
        text = (
            final_data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )

        logger.info(
            "RepairEstimator final AI payload for user %s: %s",
            request.user.id if request.user.is_authenticated else "anonymous",
            text,
        )

        if not text:
            logger.warning("AI response missing text payload: %s", final_data)
            return Response(
                {"error": "AI did not return a response. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        inventory_map = {entry["inventory_id"]: entry for entry in inventory_entries}

        ai_sections: Dict[str, Any] = {}
        recommended_payload: List[Dict[str, Any]] = []

        if text:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                logger.warning("Failed to parse AI JSON response: %s", text)
                parsed = None
        else:
            parsed = None

        if parsed:
            estimated_cost_raw = parsed.get("estimated_cost")
            if isinstance(estimated_cost_raw, dict):
                estimated_cost_section = estimated_cost_raw
            elif isinstance(estimated_cost_raw, str):
                estimated_cost_section = {"summary": estimated_cost_raw}
            else:
                estimated_cost_section = {}

            ai_sections = {
                "diagnosis": (parsed.get("diagnosis") or "").strip(),
                "estimated_cost": estimated_cost_section,
                "next_steps": (parsed.get("next_steps") or "").strip(),
                "initial_analysis": {
                    "likely_diagnosis": initial_json.get("likely_diagnosis", ""),
                    "parts_requested": requested_parts,
                },
            }

            for item in parsed.get("recommended_parts", []):
                inv_id = item.get("inventory_id")
                entry = inventory_map.get(inv_id)
                if entry:
                    recommended_payload.append(
                        {
                            "id": entry["id"],
                            "name": entry["name"],
                            "price": entry["price"],
                            "category": entry["category"],
                            "category_slug": entry["category_slug"],
                            "slug": entry["slug"],
                            "product_url": entry["product_url"],
                            "notes": (item.get("notes") or "").strip(),
                        }
                    )
        else:
            ai_sections = {
                "diagnosis": text.strip() if text else "",
                "estimated_cost": {},
                "next_steps": "",
                "initial_analysis": {
                    "likely_diagnosis": initial_json.get("likely_diagnosis", ""),
                    "parts_requested": requested_parts,
                },
            }
            for entry in inventory_entries[:4]:
                recommended_payload.append(
                    {
                        "id": entry["id"],
                        "name": entry["name"],
                        "price": entry["price"],
                        "category": entry["category"],
                        "category_slug": entry["category_slug"],
                        "slug": entry["slug"],
                        "product_url": entry["product_url"],
                        "notes": "",
                    }
                )

        estimate, _ = RepairEstimate.objects.update_or_create(
            user=request.user,
            defaults={
                "issue": issue,
                "bike_type": bike_type,
                "ai_summary": json.dumps(ai_sections, ensure_ascii=False),
                "recommendations": recommended_payload,
            },
        )

        return Response(
            {
                "issue": estimate.issue,
                "bike_type": estimate.bike_type,
                "ai_sections": ai_sections,
                "recommended_parts": recommended_payload,
                "initial_analysis": ai_sections.get("initial_analysis", {}),
                "updated_at": estimate.updated_at,
            }
        )
    except requests.RequestException as exc:
        logger.error("Gemini API request failed: %s", exc, exc_info=True)
        return Response(
            {"error": "Failed to contact AI service. Please try again soon."},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except Exception as exc:
        logger.error("Repair estimator failed: %s", exc, exc_info=True)
        return Response(
            {"error": "Unexpected error generating estimate."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def _parse_iso_datetime(value: str, *, end_of_day: bool = False):
    if not value:
        return None

    parsed = None

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None

    if parsed and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)

    if parsed and end_of_day:
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)

    return parsed


def deduct_inventory_for_order(order):
    """Deduct inventory for a confirmed order and fulfill any reservations"""
    try:
        for item in order.items.all():
            product = item.product
            if product.stock >= item.quantity:
                product.stock -= item.quantity
                product.save()

                # Check if user has an active reservation for this product and fulfill it
                user_reservation = ReservedProduct.objects.filter(
                    product=product, user=order.user, status="active"
                ).first()

                if user_reservation:
                    user_reservation.fulfill_reservation()
                    logger.info(
                        f"Fulfilled reservation {user_reservation.id} for user {order.user.username}"
                    )

                    # Process next in queue if product still has stock
                    if product.stock > 0:
                        from .utils import process_product_reservations

                        process_product_reservations(product)

                # Send inventory update
                send_inventory_update(
                    {
                        "type": "stock_update",
                        "product_id": product.id,
                        "new_stock": product.stock,
                        "product_name": product.name,
                    }
                )
            else:
                logger.warning(
                    f"Insufficient stock for product {product.id} in order {order.id}"
                )
    except Exception as e:
        logger.error(f"Error deducting inventory for order {order.id}: {str(e)}")


def clear_reserved_cart(user_id, order_id):
    """Clear cart that was reserved for an order"""
    try:
        cart = Cart.objects.get(
            user_id=user_id, notes=f"Reserved for Order #{order_id}"
        )
        cart.delete()
    except Cart.DoesNotExist:
        pass


def map_paymongo_source_to_payment_method(source_type):
    """Map PayMongo source type to our payment method"""
    mapping = {
        "card": "card",
        "gcash": "gcash",
        "paymaya": "paymaya",
    }
    return mapping.get(source_type, "paymongo")


# CSRF & Auth
@ensure_csrf_cookie
@require_http_methods(["GET"])
def get_csrf_token(request):
    # Return the token in the response body so frontend can read it
    # The cookie is still set by @ensure_csrf_cookie decorator
    csrf_token = request.META.get('CSRF_COOKIE', '')
    if not csrf_token:
        # Generate new token if not exists
        from django.middleware.csrf import get_token
        csrf_token = get_token(request)
    
    return JsonResponse({
        "csrfToken": csrf_token,
        "message": "CSRF cookie and token ready"
    })


@api_view(["GET"])
def test_user(request):
    return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)


# User Management API
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_all_users(request):
    """Get all users for staff management. Only accessible by staff."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    users = User.objects.all().order_by("-date_joined")
    
    # Search functionality
    search_query = request.GET.get('search', '').strip()
    if search_query:
        from django.db.models import Q
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )
    
    serializer = StaffUserSerializer(users, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user(request, user_id):
    """Get a specific user by ID. Only accessible by staff."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        user = User.objects.get(id=user_id)
        serializer = StaffUserSerializer(user)
        return Response(serializer.data)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_user(request, user_id):
    """Update user information. Only accessible by staff."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        user = User.objects.get(id=user_id)
        serializer = StaffUserSerializer(user, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_user(request, user_id):
    """Delete a user. Only accessible by superusers."""
    if not request.user.is_superuser:
        return Response(
            {"error": "Superuser access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        user = User.objects.get(id=user_id)
        # Prevent deleting superusers
        if user.is_superuser:
            return Response(
                {"error": "Cannot delete superuser"}, status=status.HTTP_400_BAD_REQUEST
            )
        user.delete()
        return Response({"message": "User deleted successfully"})
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_staff_permissions(request, user_id):
    """Update staff permissions. Only accessible by superusers."""
    if not request.user.is_superuser:
        return Response(
            {"error": "Superuser access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        user = User.objects.get(id=user_id)
        
        # Only allow updating permissions for staff members (not superusers)
        if not user.is_staff:
            return Response(
                {"error": "User is not a staff member"}, status=status.HTTP_400_BAD_REQUEST
            )
            
        if user.is_superuser:
            return Response(
                {"error": "Cannot modify superuser permissions"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Get or create staff permissions
        permissions, created = StaffPermissions.objects.get_or_create(user=user)
        
        # Update permissions
        serializer = StaffPermissionsSerializer(permissions, data=request.data, partial=True)
        
        if serializer.is_valid():
            updated_permissions = serializer.save()

            create_audit_log(
                actor=request.user,
                action="update_staff_permissions",
                module="user_management",
                description=f"Updated staff permissions for {user.username}",
                metadata={
                    "user_id": user.id,
                    "changes": serializer.validated_data,
                },
                target_object=updated_permissions,
                request=request,
            )
            return Response(serializer.data)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_audit_logs(request):
    """Retrieve audit log entries for administrative review."""
    if not request.user.is_superuser:
        return Response(
            {"error": "Superuser access required"}, status=status.HTTP_403_FORBIDDEN
        )

    logs = AuditLog.objects.select_related("actor").all()

    module = request.query_params.get("module")
    if module:
        logs = logs.filter(module__iexact=module)

    severity = request.query_params.get("severity")
    if severity:
        logs = logs.filter(severity__iexact=severity)

    action = request.query_params.get("action")
    if action:
        logs = logs.filter(action__icontains=action)

    actor_id = request.query_params.get("actor_id")
    actor_query = request.query_params.get("actor")
    if actor_id and actor_id.isdigit():
        logs = logs.filter(actor_id=int(actor_id))
    elif actor_query:
        logs = logs.filter(
            Q(actor__username__icontains=actor_query)
            | Q(actor__first_name__icontains=actor_query)
            | Q(actor__last_name__icontains=actor_query)
        )

    search = request.query_params.get("search")
    if search:
        logs = logs.filter(
            Q(description__icontains=search)
            | Q(action__icontains=search)
            | Q(module__icontains=search)
            | Q(target_object_repr__icontains=search)
        )

    start_date = _parse_iso_datetime(request.query_params.get("start_date"))
    if start_date:
        logs = logs.filter(created_at__gte=start_date)

    end_date = _parse_iso_datetime(
        request.query_params.get("end_date"), end_of_day=True
    )
    if end_date:
        logs = logs.filter(created_at__lte=end_date)

    page = request.query_params.get("page", "1")
    page_size = request.query_params.get("page_size", "50")

    try:
        page_number = max(int(page), 1)
    except ValueError:
        page_number = 1

    try:
        per_page = min(max(int(page_size), 1), 200)
    except ValueError:
        per_page = 50

    paginator = Paginator(logs, per_page)
    current_page = paginator.get_page(page_number)

    serializer = AuditLogSerializer(current_page.object_list, many=True)

    available_modules = [
        value
        for value in AuditLog.objects.exclude(module="")
        .order_by()
        .values_list("module", flat=True)
        .distinct()
    ]
    available_actions = [
        value
        for value in AuditLog.objects.order_by()
        .values_list("action", flat=True)
        .distinct()
    ]

    response_payload = {
        "results": serializer.data,
        "page": current_page.number,
        "page_size": per_page,
        "total_pages": paginator.num_pages,
        "total_records": paginator.count,
        "has_next": current_page.has_next(),
        "has_previous": current_page.has_previous(),
        "available_modules": available_modules,
        "available_actions": available_actions,
    }

    return Response(response_payload, status=status.HTTP_200_OK)


# Categories
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_category(request):
    """Create a new product category. Only accessible by staff."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        name = request.data.get('name')
        parent_id = request.data.get('parent')
        is_component = request.data.get('is_component', False)
        
        if not name:
            return Response(
                {"error": "Category name is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create category
        category_data = {
            'name': name,
            'is_component': is_component,
        }
        
        if parent_id:
            try:
                parent = ProductCategory.objects.get(id=parent_id)
                category_data['parent'] = parent
            except ProductCategory.DoesNotExist:
                return Response(
                    {"error": "Parent category not found"}, 
                    status=status.HTTP_404_NOT_FOUND
                )
        
        category = ProductCategory.objects.create(**category_data)
        serializer = ProductCategorySerializer(category)
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {"error": str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# Brands
@api_view(["GET"])
def get_brands(request):
    brands = Brands.objects.all()
    serializer = BrandsSerializer(brands, many=True)
    return Response(serializer.data)


@api_view(["POST"])
def create_brand(request):
    """Create a new brand"""
    try:
        name = request.data.get("name")

        if not name:
            return Response(
                {"error": "Brand name is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Check if brand already exists
        if Brands.objects.filter(name=name).exists():
            return Response(
                {"error": "Brand with this name already exists"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create the brand
        brand = Brands.objects.create(name=name)
        serializer = BrandsSerializer(brand)

        return Response(serializer.data, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Categories
@api_view(["GET"])
def get_product_categories(request):
    categories = ProductCategory.objects.all()
    serializer = ProductCategorySerializer(categories, many=True)
    return Response(serializer.data)


# Listings
@api_view(["GET"])
def get_product_listings(request):
    """Get product listings with optional pagination"""
    from django.core.paginator import Paginator, EmptyPage
    
    # Get pagination parameters
    page = request.GET.get('page', None)
    page_size = request.GET.get('page_size', None)
    
    listings = ProductListing.objects.filter(available=True).distinct().order_by('-id')
    
    # If pagination parameters provided, paginate
    if page and page_size:
        try:
            paginator = Paginator(listings, int(page_size))
            page_obj = paginator.get_page(int(page))
            
            serializer = ProductListingSerializer(page_obj.object_list, many=True)
            
            return Response({
                'results': serializer.data,
                'count': paginator.count,
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
            })
        except (EmptyPage, ValueError):
            return Response({
                'results': [],
                'count': 0,
                'total_pages': 0,
                'current_page': 1,
                'has_next': False,
                'has_previous': False,
            })
    
    # If no pagination, return all
    serializer = ProductListingSerializer(listings, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def get_product_listing(request, pk):
    try:
        listing = ProductListing.objects.get(pk=pk)
        serializer = ProductListingSerializer(listing)
        return Response(serializer.data)
    except ProductListing.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
def get_product_listing_by_slug(request, slug):
    try:
        listing = (
            ProductListing.objects.filter(slug=slug, available=True)
            .annotate(variant_count=Count("products"))
            .first()
        )
        if listing:
            serializer = ProductListingSerializer(listing)
            return Response(serializer.data)
        return Response(status=status.HTTP_404_NOT_FOUND)
    except ProductListing.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


# Listing Images
@api_view(["GET"])
def get_listing_images(request, product_listing_id):
    images = ProductImage.objects.filter(product_listing_id=product_listing_id)
    serializer = ProductImageSerializer(images, many=True)
    return Response(serializer.data)


# All Product Variants
@api_view(["GET"])
def get_all_products(request):
    variants = Product.objects.all()
    serializer = ProductSerializer(variants, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def listings_by_category(request, category_slug):
    """
    Get 7 random product listings from a specific category for recommendations
    """
    try:
        # Get the category or return 404 if not found
        category = get_object_or_404(ProductCategory, slug=category_slug)

        # Get all available listings in this category
        all_listings = list(
            ProductListing.objects.filter(category=category, available=True)
            .select_related("category")
            .prefetch_related("products")
        )

        # Get random 7 items (or all if less than 7 available)
        random_count = min(7, len(all_listings))
        random_listings = random.sample(all_listings, random_count)

        # Serialize the data
        serializer = ProductListingSerializer(random_listings, many=True)

        return Response(
            {
                "category": category.name,
                "count": len(random_listings),
                "total_available": len(all_listings),
                "listings": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"error": "Failed to fetch listings", "detail": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# Products in a Listing
@api_view(["GET"])
def get_listing_products(request, product_listing_id):
    products = Product.objects.filter(product_listing_id=product_listing_id)
    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)


# Variant Images
@api_view(["GET"])
def get_product_images(request, product_id):
    images = ProductVariantImage.objects.filter(product_variant_id=product_id)
    serializer = ProductVariantImageSerializer(images, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def get_cart(request):
    # Debug logging
    print(f"DEBUG: request.user = {request.user}")
    print(f"DEBUG: request.user type = {type(request.user)}")
    print(f"DEBUG: request.user.id = {getattr(request.user, 'id', 'NO_ID')}")
    print(
        f"DEBUG: request.user.is_authenticated = {getattr(request.user, 'is_authenticated', 'NO_ATTR')}"
    )

    # For allauth, check if user has a valid ID and is not AnonymousUser
    if (
        not request.user
        or not hasattr(request.user, "id")
        or request.user.id is None
        or str(request.user) == "AnonymousUser"
    ):
        print(f"DEBUG: User not authenticated (allauth check), returning 401")
        return Response(
            {"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED
        )

    print(f"DEBUG: User authenticated, proceeding with cart operations")
    user = request.user

    try:
        cart, created = Cart.objects.get_or_create(user=user)
        serializer = CartSerializer(cart)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        print(f"DEBUG: Error creating/getting cart: {e}")
        return Response(
            {"error": "Failed to access cart"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def add_to_cart(request):
    # For allauth, check if user has a valid ID and is not AnonymousUser
    if (
        not request.user
        or not hasattr(request.user, "id")
        or request.user.id is None
        or str(request.user) == "AnonymousUser"
    ):
        return Response(
            {"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED
        )

    user = request.user
    product_id = request.data.get("product")  # Changed from "id" to "product"
    quantity = request.data.get("quantity", 1)

    if not product_id:
        return Response(
            {"error": "Product ID is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        cart = Cart.objects.get(user=user)
        product = Product.objects.get(pk=product_id)

        # Check if item already exists in cart
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart, product=product, defaults={"quantity": quantity}
        )

        if not created:
            # Update quantity if item already exists
            cart_item.quantity += quantity
            cart_item.save()

        # Send realtime cart update
        cart_serializer = CartSerializer(cart)
        send_cart_update(user.id, cart_serializer.data)

        serializer = CartItemSerializer(cart_item)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    except Cart.DoesNotExist:
        return Response({"error": "Cart not found"}, status=status.HTTP_404_NOT_FOUND)
    except Product.DoesNotExist:
        return Response(
            {"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["DELETE"])
def remove_from_cart(request, product_id):
    # For allauth, check if user has a valid ID and is not AnonymousUser
    if (
        not request.user
        or not hasattr(request.user, "id")
        or request.user.id is None
        or str(request.user) == "AnonymousUser"
    ):
        return Response(
            {"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED
        )

    user = request.user
    try:
        cart = Cart.objects.get(user=user)
        cart_item = CartItem.objects.get(cart=cart, product__id=product_id)
        cart_item.delete()

        # Send realtime cart update
        cart_serializer = CartSerializer(cart)
        send_cart_update(user.id, cart_serializer.data)

        return Response(status=status.HTTP_204_NO_CONTENT)
    except (Cart.DoesNotExist, CartItem.DoesNotExist):
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(["PUT"])
def update_cart_item_quantity(request, product_id):
    # For allauth, check if user has a valid ID and is not AnonymousUser
    if (
        not request.user
        or not hasattr(request.user, "id")
        or request.user.id is None
        or str(request.user) == "AnonymousUser"
    ):
        return Response(
            {"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED
        )

    user = request.user
    quantity = request.data.get("quantity")

    if quantity is None or quantity < 1:
        return Response(
            {"error": "Valid quantity is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        cart = Cart.objects.get(user=user)
        cart_item = CartItem.objects.get(cart=cart, product__id=product_id)
        cart_item.quantity = quantity
        cart_item.save()

        # Send realtime cart update
        cart_serializer = CartSerializer(cart)
        send_cart_update(user.id, cart_serializer.data)

        serializer = CartItemSerializer(cart_item)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except (Cart.DoesNotExist, CartItem.DoesNotExist):
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(["DELETE"])
def clear_cart(request):
    # For allauth, check if user has a valid ID and is not AnonymousUser
    if (
        not request.user
        or not hasattr(request.user, "id")
        or request.user.id is None
        or str(request.user) == "AnonymousUser"
    ):
        return Response(
            {"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED
        )

    user = request.user
    try:
        cart = Cart.objects.get(user=user)
        cart.items.all().delete()

        # Send realtime cart update
        cart_serializer = CartSerializer(cart)
        send_cart_update(user.id, cart_serializer.data)

        return Response(status=status.HTTP_204_NO_CONTENT)
    except Cart.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
def buy_now_checkout(request):
    """Direct checkout for Buy Now (bypasses cart)."""
    user = request.user
    try:
        product_id = request.data.get("product_id")
        quantity = int(request.data.get("quantity", 1))

        if not product_id:
            return Response(
                {"error": "Product ID is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        product = Product.objects.get(id=product_id)

        # Check stock availability
        if product.stock < quantity:
            return Response(
                {
                    "error": f"Insufficient stock. Available: {product.stock}, Requested: {quantity}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check reservation access
        from .utils import check_reservation_access

        can_purchase, reason = check_reservation_access(product, user)
        if not can_purchase:
            return Response({"error": reason}, status=status.HTTP_400_BAD_REQUEST)

        # Get shipping information from request
        shipping_address = request.data.get("shipping_address", "")
        contact_number = request.data.get("contact_number", "")
        notes = request.data.get("notes", "")
        payment_method = request.data.get("payment_method", "cash_on_delivery")

        mapped_payment_method = _map_payment_method(payment_method)
        sale_type = _default_sale_type(mapped_payment_method)
        payment_status = _initial_payment_status(mapped_payment_method)
        normalized_notes = (notes or "").strip()

        with transaction.atomic():
            sale = Sales.objects.create(
                user=user if user.is_authenticated else None,
                total_amount=Decimal("0"),
                sale_type=sale_type,
                payment_status=payment_status,
                payment_method=mapped_payment_method,
                notes=normalized_notes,
            )

            order = Order.objects.create(
                user=user,
                sale=sale,
                shipping_address=shipping_address,
                contact_number=contact_number,
                notes=notes,
                is_cod=mapped_payment_method == "cod",
            )

            order_item = OrderItem.objects.create(
                order=order, product=product, quantity=quantity
            )

            item_price = _decimal_amount(product.price)
            item_amount = item_price * quantity
            supplier_price = (
                _decimal_amount(product.supplier_price)
                if product and product.supplier_price is not None
                else None
            )

            SalesItem.objects.create(
                sales=sale,
                product=product,
                quantity_sold=quantity,
                amount=item_amount,
                supplier_price=supplier_price,
            )

            sale.total_amount = item_amount
            if payment_status == "paid":
                sale.payment_date = timezone.now()
            sale.save(update_fields=["total_amount", "payment_date"])

        # For COD, deduct inventory immediately after transaction commits
        if mapped_payment_method == "cod":
            deduct_inventory_for_order(order)

        # Send realtime updates
        order_serializer = OrderSerializer(order)
        send_order_update(user.id, order_serializer.data)

        # Send notification
        send_notification(
            user.id,
            {
                "type": "order_created",
                "message": f"Order #{order.id} has been created successfully",
                "order_id": order.id,
            },
        )

        return Response(order_serializer.data, status=status.HTTP_201_CREATED)

    except Product.DoesNotExist:
        return Response(
            {"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Checkout error: {str(e)}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
def checkout(request):
    user = request.user
    try:
        cart = Cart.objects.get(user=user)

        # Check stock availability before creating order
        for item in cart.items.all():
            if item.product.stock < item.quantity:
                return Response(
                    {
                        "error": f"Insufficient stock for {item.product.name}. Available: {item.product.stock}, Requested: {item.quantity}"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Get shipping information from request
        shipping_address = request.data.get("shipping_address", "")
        contact_number = request.data.get("contact_number", "")
        notes = request.data.get("notes", "")
        payment_method = request.data.get("payment_method", "cash_on_delivery")

        mapped_payment_method = _map_payment_method(payment_method)
        sale_type = _default_sale_type(mapped_payment_method)
        payment_status = _initial_payment_status(mapped_payment_method)
        normalized_notes = (notes or "").strip()

        with transaction.atomic():
            sale = Sales.objects.create(
                user=user if user.is_authenticated else None,
                total_amount=Decimal("0"),
                sale_type=sale_type,
                payment_status=payment_status,
                payment_method=mapped_payment_method,
                notes=normalized_notes,
            )

            order = Order.objects.create(
                user=user,
                sale=sale,
                shipping_address=shipping_address,
                contact_number=contact_number,
                notes=notes,
                is_cod=mapped_payment_method == "cod",
            )

            total_amount = Decimal("0")
            for item in cart.items.select_related("product"):
                order_item = OrderItem.objects.create(
                    order=order, product=item.product, quantity=item.quantity
                )

                product_price = _decimal_amount(item.product.price)
                item_amount = product_price * item.quantity
                supplier_price = (
                    _decimal_amount(item.product.supplier_price)
                    if item.product and item.product.supplier_price is not None
                    else None
                )

                SalesItem.objects.create(
                    sales=sale,
                    product=item.product,
                    quantity_sold=item.quantity,
                    amount=item_amount,
                    supplier_price=supplier_price,
                )

                total_amount += item_amount

            sale.total_amount = total_amount
            if payment_status == "paid":
                sale.payment_date = timezone.now()
            sale.save(update_fields=["total_amount", "payment_date"])

        # Only clear cart for cash on delivery (immediate payment)
        # For other payment methods, keep cart until payment is confirmed
        if mapped_payment_method == "cod":
            cart.delete()
            # Deduct inventory for COD orders
            deduct_inventory_for_order(order)
        else:
            # For digital payments, mark cart as "reserved" for this order
            cart.notes = f"Reserved for Order #{order.id}"
            cart.save()

        # Send realtime updates
        order_serializer = OrderSerializer(order)
        send_order_update(user.id, order_serializer.data)

        # Send notification
        send_notification(
            user.id,
            {
                "type": "order_created",
                "message": f"Order #{order.id} has been created successfully",
                "order_id": order.id,
            },
        )

        serializer = OrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    except Cart.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
def pos_sale(request):
    """Process a POS sale - record directly to Sales without creating an order"""
    user = request.user

    # Check if user is staff
    if not user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        # Get cart items from request
        cart_items = request.data.get("items", [])
        payment_method = request.data.get("payment_method", "cash")
        customer_name = request.data.get("customer_name", "Walk-in Customer")
        customer_contact = request.data.get("customer_contact", "")

        if not cart_items:
            return Response(
                {"error": "No items in cart"}, status=status.HTTP_400_BAD_REQUEST
            )

        normalized_requested_method = (payment_method or "").lower()
        is_qrph_payment = normalized_requested_method in {"qrph", "qr_ph"}
        mapped_payment_method = _map_payment_method(payment_method)
        if mapped_payment_method == "cod":
            mapped_payment_method = "cash"

        sale_notes_parts = [
            part.strip()
            for part in [customer_name, customer_contact]
            if isinstance(part, str) and part.strip()
        ]

        payment_status = "pending" if is_qrph_payment else "paid"
        payment_date = None if is_qrph_payment else timezone.now()
        qrph_payload = None

        with transaction.atomic():
            sale = Sales.objects.create(
                user=None,
                total_amount=Decimal("0"),
                sale_type="pos",
                payment_status=payment_status,
                payment_method=mapped_payment_method,
                payment_date=payment_date,
                notes=" | ".join(sale_notes_parts),
                salesperson=request.user,  # Staff member who processed this POS sale
            )

            total_amount = Decimal("0")
            for item in cart_items:
                try:
                    product = Product.objects.get(id=item["product_id"])
                    quantity = int(item["quantity"])
                    item_amount = _decimal_amount(product.price) * quantity

                    supplier_price = (
                        _decimal_amount(product.supplier_price)
                        if product.supplier_price is not None
                        else None
                    )
                    SalesItem.objects.create(
                        sales=sale,
                        product=product,
                        quantity_sold=quantity,
                        amount=item_amount,
                        supplier_price=supplier_price,
                    )

                    if hasattr(product, "stock") and product.stock is not None:
                        product.stock = max(0, product.stock - quantity)
                        product.save()

                    total_amount += item_amount

                except Product.DoesNotExist:
                    raise

            sale.total_amount = total_amount
            sale.save(update_fields=["total_amount", "payment_date"])

            if is_qrph_payment:
                paymongo_service = PayMongoService()
                qrph_payload = paymongo_service.create_qr_ph(
                    amount=total_amount,
                    description=f"POS Sale #{sale.id} - QR Ph Payment",
                )
                sale.payment_status = "pending"
                sale.paymongo_payment_id = (
                    qrph_payload.get("data", {}).get("id")
                    if isinstance(qrph_payload, dict)
                    else None
                )
                sale.save(update_fields=["payment_status", "paymongo_payment_id"])
    except Product.DoesNotExist as e:
        return Response(
            {"error": f"Product not found: {str(e)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        logger.exception("Failed to process POS sale")
        return Response(
            {"error": f"Failed to process sale: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    else:
        # Send notification
        notification_message = (
            f"POS Sale #{sale.id} pending QR Ph payment - ₱{sale.total_amount:.2f}"
            if is_qrph_payment
            else f"POS Sale #{sale.id} completed - ₱{sale.total_amount:.2f}"
        )

        send_notification(
            user.id,
            {
                "type": "pos_sale_completed",
                "message": notification_message,
                "sale_id": sale.id,
                "total_amount": float(sale.total_amount),
            },
        )

        create_audit_log(
            actor=user,
            action="pos_sale",
            module="sales",
            description=f"Processed POS sale #{sale.id} ({payment_method})",
            metadata={
                "sale_id": sale.id,
                "total_amount": float(sale.total_amount),
                "payment_method": payment_method,
                "customer_name": customer_name,
                "customer_contact": customer_contact,
                "items": [
                    {
                        "product_id": item.get("product_id"),
                        "quantity": int(item.get("quantity", 0)),
                    }
                    for item in cart_items
                ],
            },
            target_object=sale,
            request=request,
        )

        response_payload = {
            "success": True,
            "sale_id": sale.id,
            "total_amount": float(sale.total_amount),
            "message": (
                "QR Ph payment generated. Ask the customer to scan the code."
                if is_qrph_payment
                else f"Sale completed successfully! Sale #{sale.id}"
            ),
        }

        if qrph_payload:
            response_payload["qrph"] = qrph_payload

        return Response(response_payload, status=status.HTTP_201_CREATED)

@api_view(["GET"])
def get_order(request, order_id):
    user = request.user
    try:
        order = Order.objects.get(pk=order_id, user=user)
        serializer = OrderSerializer(order)
        return Response(serializer.data)
    except Order.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
def get_all_order(request):
    # Exclude POS sales from orders list (they're tracked in Sales model)
    orders = Order.objects.exclude(shipping_address__icontains="POS Sale").all()
    serializer = OrderSerializer(orders, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def get_customer_orders(request):
    """Get orders for the authenticated customer"""
    user = request.user

    # Check if user is authenticated
    if not user.is_authenticated:
        return Response(
            {"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED
        )

    # Get orders for this customer only, excluding POS sales
    orders = (
        Order.objects.filter(user=user)
        .exclude(shipping_address__icontains="POS Sale")
        .order_by("-created_at")
    )
    serializer = OrderSerializer(orders, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def get_order_items(request, order_id):
    user = request.user
    try:
        order = Order.objects.get(pk=order_id, user=user)
        items = order.items.all()
        serializer = OrderItemSerializer(items, many=True)
        return Response(serializer.data)
    except Order.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(["PATCH"])
def update_order_status(request, order_id):
    """Update order status - staff only, or order owner for specific fields"""
    # For PayMongo checkout session ID, allow order owner
    checkout_session_id = request.data.get("paymongo_checkout_session_id")
    payment_id = request.data.get("paymongo_payment_id")
    if checkout_session_id or payment_id:
        try:
            order = (
                Order.objects.select_related("sale")
                .get(pk=order_id, user=request.user)
            )
            sale = _ensure_sale_for_order(order)
            fields_to_update = []
            if checkout_session_id:
                sale.paymongo_checkout_session_id = checkout_session_id
                fields_to_update.append("paymongo_checkout_session_id")
            if payment_id:
                sale.paymongo_payment_id = payment_id
                fields_to_update.append("paymongo_payment_id")
            if fields_to_update:
                sale.save(update_fields=fields_to_update)
            return Response(
                {"message": "Payment metadata stored"}, status=status.HTTP_200_OK
            )
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND
            )

    # For status updates, require staff access
    if not request.user.is_authenticated or not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        order = Order.objects.select_related("sale").get(pk=order_id)
        sale = _ensure_sale_for_order(order)
        new_status = request.data.get("status")
        payment_status = request.data.get("payment_status")
        reason = request.data.get("reason", "")
        sale_updates: List[str] = []

        # Update order status if provided
        if new_status:
            if new_status not in [
                "to_pay",
                "to_ship",
                "to_deliver",
                "completed",
                "cancelled",
                "returned",
            ]:
                return Response(
                    {"error": "Invalid status"}, status=status.HTTP_400_BAD_REQUEST
                )

            was_completed = order.status == "completed"
            order.status = new_status

            # Handle cancellation reason
            if new_status == "cancelled":
                if reason:
                    order.cancel_reason = reason
                else:
                    # Default reason for staff cancellations
                    order.cancel_reason = (
                        f"Order cancelled by staff: {request.user.username}"
                    )

            # Handle return reason
            if new_status == "returned":
                if reason:
                    order.return_reason = reason
                else:
                    # Staff override for returned status
                    order.return_reason = (
                        f"Order status override by staff: {request.user.username}"
                    )
        else:
            was_completed = order.status == "completed"

        # Update payment status if provided
        if payment_status:
            valid_statuses = {choice[0] for choice in Sales.PAYMENT_STATUS_CHOICES}
            if payment_status not in valid_statuses:
                return Response(
                    {"error": "Invalid payment status"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            sale.payment_status = payment_status
            sale_updates.append("payment_status")
            if payment_status == "paid":
                sale.payment_date = timezone.now()
                sale_updates.append("payment_date")

        order.save()

        # If newly completed, record a Sales record and lines
        if new_status == "completed" and not was_completed:
            try:
                if sale.payment_status != "paid":
                    sale.payment_status = "paid"
                    sale.payment_date = timezone.now()
                    sale_updates.extend(["payment_status", "payment_date"])

                # Send order completion email
                from .utils import send_order_completion_email
                send_order_completion_email(order)
            except Exception as e:
                logger.error(f"Failed to record sale for order {order.id}: {str(e)}")
        elif new_status == "cancelled" and sale.payment_status not in ["failed", "refunded"]:
            sale.payment_status = "failed"
            sale.payment_date = None
            sale_updates.extend(["payment_status", "payment_date"])

        if sale_updates:
            sale.save(update_fields=list(set(sale_updates)))

        # Send realtime updates
        order_serializer = OrderSerializer(order)
        send_order_update(order.user.id, order_serializer.data)

        return Response(order_serializer.data, status=status.HTTP_200_OK)

    except Order.DoesNotExist:
        return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_order_received(request, order_id):
    """Allow customers to mark their order as received/completed."""
    try:
        order = (
            Order.objects.select_related("sale")
            .get(pk=order_id, user=request.user)
        )
    except Order.DoesNotExist:
        return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)

    if order.status != "to_deliver":
        return Response(
            {"error": "Only orders marked 'To Deliver' can be completed."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    sale = _ensure_sale_for_order(order)

    order.status = "completed"
    order.save(update_fields=["status"])

    sale_updates: List[str] = []
    if sale.payment_status != "paid":
        sale.payment_status = "paid"
        sale.payment_date = timezone.now()
        sale_updates.extend(["payment_status", "payment_date"])

    if sale_updates:
        sale.save(update_fields=list(set(sale_updates)))

    order_serializer = OrderSerializer(order)
    send_order_update(order.user.id, order_serializer.data)

    return Response(order_serializer.data, status=status.HTTP_200_OK)


# Sales
@api_view(["GET"])
def get_sales(request):
    sales = Sales.objects.prefetch_related(
        "sales_item__product__product_listing", "sales_item__product__brand", "user"
    ).select_related("salesperson").order_by("-sale_date")
    serializer = SalesSerializer(sales, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@renderer_classes([CSVAttachmentRenderer, JSONRenderer, BrowsableAPIRenderer])
def export_sales(request):
    """Export sales data as a CSV file (staff only)."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    sales = (
        Sales.objects.prefetch_related(
            "sales_item__product__product_listing",
            "sales_item__product__brand",
        )
        .select_related("user", "salesperson", "order")
        .order_by("-sale_date")
    )

    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    response = HttpResponse(content_type="text/csv")
    response[
        "Content-Disposition"
    ] = f'attachment; filename="sales_export_{timestamp}.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "Sale ID",
            "Sale Date",
            "Customer",
            "Salesperson",
            "Payment Method",
            "Order ID",
            "Product",
            "Variant",
            "Brand",
            "Quantity Sold",
            "Refunded Quantity",
            "Item Amount",
            "Supplier Price",
            "Sale Total",
            "Capital",
            "Net Revenue",
        ]
    )

    for sale in sales:
        items = list(sale.sales_item.all())

        sale_total = 0
        sale_capital = 0
        for item in items:
            item_amount = (
                float(item.amount)
                if item.amount is not None
                else (
                    float(item.product.price) * item.quantity_sold
                    if item.product and item.product.price is not None
                    else 0
                )
            )
            sale_total += item_amount
            if item.supplier_price is not None:
                non_refunded_qty = item.quantity_sold - item.refunded_quantity
                sale_capital += float(item.supplier_price) * max(non_refunded_qty, 0)

        sale_net_revenue = sale_total - sale_capital
        base_row = [
            sale.id,
            timezone.localtime(sale.sale_date).strftime("%Y-%m-%d %H:%M:%S")
            if sale.sale_date
            else "",
            sale.user.username if sale.user else "Walk-in Customer",
            sale.salesperson.username if sale.salesperson else "",
            sale.payment_method,
            sale.order.id if sale.order else "",
        ]

        if not items:
            writer.writerow(
                base_row
                + ["", "", "", "", "", "", f"{sale_total:.2f}", f"{sale_capital:.2f}", f"{sale_net_revenue:.2f}"]
            )
            continue

        for item in items:
            item_amount = (
                float(item.amount)
                if item.amount is not None
                else (
                    float(item.product.price) * item.quantity_sold
                    if item.product and item.product.price is not None
                    else 0
                )
            )
            writer.writerow(
                base_row
                + [
                    item.product.product_listing.name
                    if item.product
                    and item.product.product_listing
                    and item.product.product_listing.name
                    else item.product.name
                    if item.product and item.product.name
                    else "",
                    item.product.variant_attribute
                    if item.product and item.product.variant_attribute
                    else "",
                    item.product.brand.name
                    if item.product and item.product.brand
                    else "",
                    item.quantity_sold,
                    item.refunded_quantity,
                    f"{item_amount:.2f}",
                    f"{float(item.supplier_price):.2f}"
                    if item.supplier_price is not None
                    else "",
                    f"{sale_total:.2f}",
                    f"{sale_capital:.2f}",
                    f"{sale_net_revenue:.2f}",
                ]
            )

    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_product_review(request):
    """Allow customers to submit a product review once an order is completed or refunded."""
    order_id = request.data.get("order_id")
    product_listing_id = request.data.get("product_listing_id")
    star = request.data.get("star")
    review_text = (request.data.get("review") or "").strip()

    if not order_id or not product_listing_id or star is None:
        return Response(
            {"error": "order_id, product_listing_id, and star are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        order_id = int(order_id)
        product_listing_id = int(product_listing_id)
        star = int(star)
    except (TypeError, ValueError):
        return Response(
            {"error": "Invalid data. IDs and star rating must be integers."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if star < 1 or star > 5:
        return Response(
            {"error": "Star rating must be between 1 and 5."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if review_text and len(review_text) < 10:
        return Response(
            {"error": "Review text must be at least 10 characters long."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        order = (
            Order.objects.prefetch_related("items__product__product_listing")
            .select_related("user")
            .get(id=order_id, user=request.user)
        )
    except Order.DoesNotExist:
        return Response(
            {"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND
        )

    sale_status = order.sale.payment_status if order.sale else None
    if (
        order.status not in ["completed", "returned"]
        and sale_status != "refunded"
    ):
        return Response(
            {"error": "Reviews are only allowed for completed or refunded orders."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    matching_listing = None
    for item in order.items.all():
        listing = getattr(item.product, "product_listing", None)
        if listing and listing.id == product_listing_id:
            matching_listing = listing
            break

    if not matching_listing:
        return Response(
            {"error": "The specified product was not part of this order."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if ProductReview.objects.filter(
        user=request.user, product_listing_id=product_listing_id
    ).exists():
        return Response(
            {"error": "You have already reviewed this product."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    review = ProductReview.objects.create(
        product_listing=matching_listing,
        user=request.user,
        star=star,
        review=review_text or None,
    )

    serializer = ProductReviewSerializer(review)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def get_top_selling_products(request):
    """Get top selling products based on sales data"""
    try:
        from django.db.models import Sum, Count, F, DecimalField
        from django.db.models.functions import Coalesce

        # Aggregate sales by product
        top_products = (
            SalesItem.objects.values(
                "product__id", "product__name", "product__product_listing__name"
            )
            .annotate(
                total_quantity=Sum("quantity_sold"),
                total_revenue=Sum("amount"),
                sales_count=Count("id"),
            )
            .filter(total_quantity__gt=0)  # Only positive sales (exclude pure refunds)
            .order_by("-total_quantity")[:10]  # Top 10
        )

        # Format the response
        result = [
            {
                "product_id": item["product__id"],
                "product_name": item["product__product_listing__name"]
                or item["product__name"]
                or "Unknown Product",
                "quantity_sold": item["total_quantity"],
                "revenue": float(item["total_revenue"]) if item["total_revenue"] else 0,
                "sales_count": item["sales_count"],
            }
            for item in top_products
        ]

        return Response(result, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Failed to get top selling products: {str(e)}")
        return Response(
            {"error": f"Failed to fetch top selling products: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def refund_full_sale(request, sale_id):
    """Refund an entire sale - all items will be marked as refunded"""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        sale = Sales.objects.prefetch_related("sales_item__product", "order").get(id=sale_id)
        reason = request.data.get("reason", "")
        notes = request.data.get("notes", "")

        # Check if already fully refunded
        all_refunded = all(item.refunded for item in sale.sales_item.all())
        if all_refunded:
            return Response(
                {"error": "All items in this sale have already been refunded"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Calculate total refund amount for non-refunded items only
        total_refund_amount = 0
        for item in sale.sales_item.all():
            if not item.refunded:
                remaining_qty = item.quantity_sold - item.refunded_quantity
                if remaining_qty > 0:
                    item_price = float(item.amount) / item.quantity_sold if item.quantity_sold > 0 else float(item.product.price)
                    total_refund_amount += item_price * remaining_qty

        # Process PayMongo refund if payment is not cash
        if sale.payment_method not in ["cash", "cod"] and sale.paymongo_payment_id:
            try:
                from .paymongo_service import PayMongoService
                paymongo_service = PayMongoService()
                refund_result = paymongo_service.create_refund(
                    payment_id=sale.paymongo_payment_id,
                    amount=total_refund_amount,
                    reason=reason or "requested_by_customer"
                )
                if "error" in refund_result:
                    return Response(
                        {"error": f"PayMongo refund failed: {refund_result.get('error')}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except Exception as e:
                logger.error(f"PayMongo refund error: {str(e)}")
                return Response(
                    {"error": f"Failed to process PayMongo refund: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        # Update all non-refunded items
        refunded_items = []
        for item in sale.sales_item.all():
            if not item.refunded:
                remaining_qty = item.quantity_sold - item.refunded_quantity
                if remaining_qty > 0:
                    item.refunded_quantity = item.quantity_sold
                    item.refunded = True
                    item.save()
                    refunded_items.append(item)

        # Update sale's last_modified timestamp
        sale.save()

        create_audit_log(
            actor=request.user,
            action="refund_full_sale",
            module="sales",
            description=f"Processed full refund for sale #{sale.id}",
            metadata={
                "sale_id": sale.id,
                "refunded_items": [
                    {
                        "item_id": item.id,
                        "product_id": item.product_id,
                        "quantity_sold": item.quantity_sold,
                    }
                    for item in refunded_items
                ],
                "reason": reason,
                "notes": notes,
                "total_refund_amount": round(total_refund_amount, 2),
            },
            target_object=sale,
            request=request,
        )

        return Response(
            {
                "success": True,
                "sale_id": sale.id,
                "message": f"Full refund processed for sale #{sale.id}",
                "refunded_items": len(refunded_items),
            },
            status=status.HTTP_200_OK,
        )

    except Sales.DoesNotExist:
        return Response(
            {"error": "Sale not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Refund full sale error: {str(e)}")
        return Response(
            {"error": f"Failed to process refund: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def refund_sale_item(request, sale_id, item_id):
    """Refund a specific quantity of a sale item"""
    if not request.user.is_staff:
                return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        sale = Sales.objects.prefetch_related("sales_item__product", "order").get(id=sale_id)
        sale_item = sale.sales_item.get(id=item_id)
        refund_quantity = int(request.data.get("quantity", 0))
        reason = request.data.get("reason", "")
        notes = request.data.get("notes", "")

        # Validate refund quantity
        if refund_quantity <= 0:
            return Response(
                {"error": "Refund quantity must be greater than 0"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Check if item is already fully refunded
        if sale_item.refunded:
            return Response(
                {"error": "This item has already been fully refunded"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check available quantity to refund
        available_qty = sale_item.quantity_sold - sale_item.refunded_quantity
        if refund_quantity > available_qty:
            return Response(
                {"error": f"Cannot refund {refund_quantity} units. Only {available_qty} units remaining."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Calculate refund amount
        item_price = float(sale_item.amount) / sale_item.quantity_sold if sale_item.quantity_sold > 0 else float(sale_item.product.price)
        refund_amount = item_price * refund_quantity

        # Process PayMongo refund if payment is not cash
        if sale.payment_method not in ["cash", "cod"] and sale.paymongo_payment_id:
            try:
                from .paymongo_service import PayMongoService
                paymongo_service = PayMongoService()
                refund_result = paymongo_service.create_refund(
                    payment_id=sale.paymongo_payment_id,
                    amount=refund_amount,
                    reason=reason or "requested_by_customer"
                )
                if "error" in refund_result:
                    return Response(
                        {"error": f"PayMongo refund failed: {refund_result.get('error')}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except Exception as e:
                logger.error(f"PayMongo refund error: {str(e)}")
                return Response(
                    {"error": f"Failed to process PayMongo refund: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        # Update sale item
        sale_item.refunded_quantity += refund_quantity
        if sale_item.refunded_quantity >= sale_item.quantity_sold:
            sale_item.refunded = True
        sale_item.save()

        # Update sale's last_modified timestamp
        sale.save()

        create_audit_log(
            actor=request.user,
            action="refund_sale_item",
            module="sales",
            description=f"Refunded {refund_quantity} unit(s) from sale #{sale.id}",
            metadata={
                "sale_id": sale.id,
                "sale_item_id": sale_item.id,
                "product_id": sale_item.product_id,
                "refund_quantity": refund_quantity,
                "refund_amount": round(refund_amount, 2),
                "reason": reason,
                "notes": notes,
            },
            target_object=sale_item,
            request=request,
        )

        return Response(
            {
                "success": True,
                "sale_id": sale.id,
                "item_id": item_id,
                "refund_quantity": refund_quantity,
                "refund_amount": refund_amount,
                "message": f"Refunded {refund_quantity} unit(s) for item",
            },
            status=status.HTTP_200_OK,
        )

    except Sales.DoesNotExist:
        return Response(
            {"error": "Sale not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except SalesItem.DoesNotExist:
        return Response(
            {"error": "Sale item not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Refund sale item error: {str(e)}")
        return Response(
            {"error": f"Failed to process refund: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# Repair Queue
@api_view(["GET"])
def get_all_schedule(request):
    queue = (
        ServiceQueue.objects.all().select_related("user").order_by("queue_date", "id")
    )
    serializer = QueueSerializer(queue, many=True)
    return Response(serializer.data)


# Product Listing Management API
@api_view(["GET"])
def get_all_listings(request):
    """Get all product listings for staff management."""
    listings = (
        ProductListing.objects.all()
        .select_related("category", "brand")
        .prefetch_related("products", "compatibility_tags")
    )
    serializer = ProductListingSerializer(listings, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def get_listing(request, listing_id):
    """Get a specific product listing by ID."""
    try:
        listing = ProductListing.objects.get(id=listing_id)
        serializer = ProductListingSerializer(listing)
        return Response(serializer.data)
    except ProductListing.DoesNotExist:
        return Response(
            {"error": "Product listing not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_listing(request):
    """Create a new product listing. Only accessible by staff."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    # Parse JSON arrays from FormData if they exist
    # Convert QueryDict to regular dict for easier handling
    if hasattr(request.data, 'dict'):
        data = request.data.dict()
    else:
        data = dict(request.data)
    
    # Handle compatibility_tag_ids - it might come as JSON string or already parsed
    if "compatibility_tag_ids" in data:
        compatibility_tag_ids = data["compatibility_tag_ids"]
        
        # QueryDict might return a list even for single values, so get the first item if it's a list
        if isinstance(compatibility_tag_ids, list):
            if len(compatibility_tag_ids) > 0:
                compatibility_tag_ids = compatibility_tag_ids[0]
            else:
                compatibility_tag_ids = None
        
        # If it's a string, try to parse as JSON
        if isinstance(compatibility_tag_ids, str):
            import json
            try:
                parsed = json.loads(compatibility_tag_ids)
                # Ensure it's a list, not a dict or other type
                if isinstance(parsed, list):
                    data["compatibility_tag_ids"] = parsed
                elif isinstance(parsed, dict):
                    return Response(
                        {"compatibility_tag_ids": ["Expected a list of items but got type 'dict'."]},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                else:
                    data["compatibility_tag_ids"] = [parsed] if parsed is not None else []
            except json.JSONDecodeError as e:
                return Response(
                    {"compatibility_tag_ids": [f"Invalid JSON: {str(e)}"]},
                    status=status.HTTP_400_BAD_REQUEST
                )
        # If it's already a list, ensure all items are integers
        elif isinstance(compatibility_tag_ids, list):
            try:
                data["compatibility_tag_ids"] = [int(x) for x in compatibility_tag_ids]
            except (ValueError, TypeError):
                return Response(
                    {"compatibility_tag_ids": ["All items must be integers"]},
                    status=status.HTTP_400_BAD_REQUEST
                )
        # If it's a dict, that's an error
        elif isinstance(compatibility_tag_ids, dict):
            return Response(
                {"compatibility_tag_ids": ["Expected a list of items but got type 'dict'."]},
                status=status.HTTP_400_BAD_REQUEST
            )
        # If it's None or empty, convert to empty list
        elif compatibility_tag_ids is None:
            data["compatibility_tag_ids"] = []

    serializer = ProductListingSerializer(data=data)
    if serializer.is_valid():
        listing = serializer.save()

        # Handle product images
        for key in request.FILES.keys():
            if key.startswith("product_image_"):
                try:
                    image_file = request.FILES[key]
                    print(f"DEBUG create_listing: Saving image {key}: {image_file.name} ({image_file.size} bytes)")
                    product_image = ProductImage.objects.create(
                        product_listing=listing,
                        image=image_file,
                        alt_text=listing.name or "Product image",
                    )
                    print(f"DEBUG create_listing: Image saved successfully. URL: {product_image.image.url}")
                except Exception as e:
                    print(f"ERROR create_listing: Failed to save image {key}: {str(e)}")
                    import traceback
                    traceback.print_exc()

        return Response(
            ProductListingSerializer(listing).data, status=status.HTTP_201_CREATED
        )
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_listing(request, listing_id):
    """Update a product listing. Only accessible by staff."""
    print(f"DEBUG update_listing: user={request.user}, is_authenticated={request.user.is_authenticated}, is_staff={request.user.is_staff}")
    
    if not request.user.is_staff:
        print(f"DEBUG update_listing: PERMISSION DENIED - User {request.user.id} is not staff")
        return Response(
            {"error": "Staff access required. Please ensure your account has staff permissions."}, 
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        listing = ProductListing.objects.get(id=listing_id)

        # Parse JSON arrays from FormData if they exist
        # Convert QueryDict to regular dict for easier handling
        if hasattr(request.data, 'dict'):
            data = request.data.dict()
        else:
            data = dict(request.data)
        
        print(f"DEBUG update_listing: Raw data keys: {list(data.keys())}")
        print(f"DEBUG update_listing: Raw compatibility_tag_ids: {data.get('compatibility_tag_ids')} (type: {type(data.get('compatibility_tag_ids'))})")
        
        # Handle compatibility_tag_ids - it might come as JSON string or already parsed
        if "compatibility_tag_ids" in data:
            compatibility_tag_ids = data["compatibility_tag_ids"]
            
            # QueryDict might return a list even for single values, so get the first item if it's a list
            if isinstance(compatibility_tag_ids, list):
                if len(compatibility_tag_ids) > 0:
                    compatibility_tag_ids = compatibility_tag_ids[0]
                else:
                    compatibility_tag_ids = None
            
            # If it's a string, try to parse as JSON
            if isinstance(compatibility_tag_ids, str):
                import json
                try:
                    parsed = json.loads(compatibility_tag_ids)
                    # Ensure it's a list, not a dict or other type
                    if isinstance(parsed, list):
                        data["compatibility_tag_ids"] = parsed
                    elif isinstance(parsed, dict):
                        # If it's a dict, that's an error
                        print(f"DEBUG update_listing: compatibility_tag_ids parsed as dict: {parsed}")
                        return Response(
                            {"compatibility_tag_ids": ["Expected a list of items but got type 'dict'."]},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                    else:
                        # If it's not a list, try to convert to list
                        data["compatibility_tag_ids"] = [parsed] if parsed is not None else []
                    print(f"DEBUG update_listing: Parsed compatibility_tag_ids: {data['compatibility_tag_ids']} (type: {type(data['compatibility_tag_ids'])})")
                except json.JSONDecodeError as e:
                    print(f"DEBUG update_listing: JSON parse error: {e}")
                    return Response(
                        {"compatibility_tag_ids": [f"Invalid JSON: {str(e)}"]},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            # If it's already a list, ensure all items are integers
            elif isinstance(compatibility_tag_ids, list):
                # Ensure all items are integers
                try:
                    data["compatibility_tag_ids"] = [int(x) for x in compatibility_tag_ids]
                except (ValueError, TypeError) as e:
                    return Response(
                        {"compatibility_tag_ids": ["All items must be integers"]},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            # If it's a dict, that's an error
            elif isinstance(compatibility_tag_ids, dict):
                print(f"DEBUG update_listing: compatibility_tag_ids is a dict: {compatibility_tag_ids}")
                return Response(
                    {"compatibility_tag_ids": ["Expected a list of items but got type 'dict'."]},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # If it's None or empty, convert to empty list
            elif compatibility_tag_ids is None:
                data["compatibility_tag_ids"] = []

        # Check if thumbnail/image is being uploaded
        if 'image' in request.FILES:
            print(f"DEBUG update_listing: Found thumbnail/image file: {request.FILES['image'].name} ({request.FILES['image'].size} bytes)")
            data['image'] = request.FILES['image']
        
        serializer = ProductListingSerializer(listing, data=data, partial=True)

        if serializer.is_valid():
            print(f"DEBUG update_listing: Serializer is valid, saving listing {listing.id}")
            listing = serializer.save()
            print(f"DEBUG update_listing: Listing saved. Thumbnail URL: {listing.image.url if listing.image else 'None'}")

            # Handle new product images
            for key in request.FILES.keys():
                if key.startswith("product_image_"):
                    try:
                        image_file = request.FILES[key]
                        print(f"DEBUG update_listing: Saving image {key}: {image_file.name} ({image_file.size} bytes)")
                        product_image = ProductImage.objects.create(
                            product_listing=listing,
                            image=image_file,
                            alt_text=listing.name or "Product image",
                        )
                        print(f"DEBUG update_listing: Image saved successfully. URL: {product_image.image.url}")
                    except Exception as e:
                        print(f"ERROR update_listing: Failed to save image {key}: {str(e)}")
                        import traceback
                        traceback.print_exc()

            return Response(ProductListingSerializer(listing).data)
        else:
            print(f"DEBUG update_listing: Serializer validation errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except ProductListing.DoesNotExist:
        return Response(
            {"error": "Product listing not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_listing(request, listing_id):
    """Delete a product listing. Only accessible by staff."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        listing = ProductListing.objects.get(id=listing_id)
        listing.delete()
        return Response({"message": "Product listing deleted successfully"})
    except ProductListing.DoesNotExist:
        return Response(
            {"error": "Product listing not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_listing_image(request, image_id):
    """Delete a product listing image. Only accessible by staff."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        image = ProductImage.objects.get(id=image_id)
        image.delete()
        return Response({"message": "Image deleted successfully"})
    except ProductImage.DoesNotExist:
        return Response({"error": "Image not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_unassigned_products(request):
    """Get all products not assigned to any listing."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    products = Product.objects.filter(product_listing__isnull=True).select_related(
        "brand", "supply"
    )
    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def assign_products_to_listing(request, listing_id):
    """Assign products to a listing."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        listing = ProductListing.objects.get(id=listing_id)
        product_ids = request.data.get("product_ids", [])

        if not product_ids:
            return Response(
                {"error": "No product IDs provided"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Update products to be assigned to this listing
        updated_count = Product.objects.filter(
            id__in=product_ids,
            product_listing__isnull=True,  # Only assign unassigned products
        ).update(product_listing=listing)

        return Response(
            {
                "message": f"Successfully assigned {updated_count} product(s) to listing",
                "assigned_count": updated_count,
            }
        )
    except ProductListing.DoesNotExist:
        return Response(
            {"error": "Listing not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def unassign_products_from_listing(request):
    """Unassign products from their current listing."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    product_ids = request.data.get("product_ids", [])

    if not product_ids:
        return Response(
            {"error": "No product IDs provided"}, status=status.HTTP_400_BAD_REQUEST
        )

    # Remove products from their listings
    updated_count = Product.objects.filter(id__in=product_ids).update(
        product_listing=None
    )

    return Response(
        {
            "message": f"Successfully unassigned {updated_count} product(s)",
            "unassigned_count": updated_count,
        }
    )


# Bike Compatibility Tag Management API
@api_view(["GET"])
def get_compatibility_tags(request):
    """Get all bike compatibility tags, optionally filtered by type."""
    tag_type = request.query_params.get("tag_type")
    
    if tag_type:
        tags = BikeCompatibilityTag.objects.filter(tag_type=tag_type)
    else:
        tags = BikeCompatibilityTag.objects.all()
    
    serializer = BikeCompatibilityTagSerializer(tags, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_compatibility_tag(request):
    """Create a new bike compatibility tag. Staff only."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )
    
    tag_type = request.data.get("tag_type")
    value = request.data.get("value")
    display_name = request.data.get("display_name")
    description = request.data.get("description", "")
    display_order = request.data.get("display_order", 0)
    
    if not tag_type or not value or not display_name:
        return Response(
            {"error": "tag_type, value, and display_name are required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if tag_type not in ["use_case", "budget", "physical"]:
        return Response(
            {"error": "tag_type must be 'use_case', 'budget', or 'physical'"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if tag already exists
    if BikeCompatibilityTag.objects.filter(tag_type=tag_type, value=value).exists():
        return Response(
            {"error": f"Tag with type '{tag_type}' and value '{value}' already exists"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    tag = BikeCompatibilityTag.objects.create(
        tag_type=tag_type,
        value=value,
        display_name=display_name,
        description=description,
        display_order=display_order
    )
    serializer = BikeCompatibilityTagSerializer(tag)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_compatibility_tag(request, tag_id):
    """Update a bike compatibility tag. Staff only."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        tag = BikeCompatibilityTag.objects.get(id=tag_id)
        
        if "tag_type" in request.data:
            if request.data["tag_type"] not in ["use_case", "budget", "physical"]:
                return Response(
                    {"error": "tag_type must be 'use_case', 'budget', or 'physical'"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            tag.tag_type = request.data["tag_type"]
        
        if "value" in request.data:
            tag.value = request.data["value"]
        if "display_name" in request.data:
            tag.display_name = request.data["display_name"]
        if "description" in request.data:
            tag.description = request.data["description"]
        if "display_order" in request.data:
            tag.display_order = request.data["display_order"]
        
        tag.save()
        serializer = BikeCompatibilityTagSerializer(tag)
        return Response(serializer.data)
    except BikeCompatibilityTag.DoesNotExist:
        return Response({"error": "Tag not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_compatibility_tag(request, tag_id):
    """Delete a bike compatibility tag. Staff only."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        tag = BikeCompatibilityTag.objects.get(id=tag_id)
        tag.delete()
        return Response({"message": "Tag deleted successfully"})
    except BikeCompatibilityTag.DoesNotExist:
        return Response({"error": "Tag not found"}, status=status.HTTP_404_NOT_FOUND)


# OLD Compatibility Management API (kept for backward compatibility, will be removed)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_compatibility_group(request):
    """Create a new compatibility group."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    name = request.data.get("name")
    description = request.data.get("description", "")

    if not name:
        return Response(
            {"error": "Group name is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    group = CompatibilityGroup.objects.create(name=name, description=description)
    serializer = CompatibilityGroupSerializer(group)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_compatibility_group(request, group_id):
    """Update a compatibility group."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        group = CompatibilityGroup.objects.get(id=group_id)

        if "name" in request.data:
            group.name = request.data["name"]
        if "description" in request.data:
            group.description = request.data["description"]

        group.save()
        serializer = CompatibilityGroupSerializer(group)
        return Response(serializer.data)
    except CompatibilityGroup.DoesNotExist:
        return Response({"error": "Group not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_compatibility_group(request, group_id):
    """Delete a compatibility group."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        group = CompatibilityGroup.objects.get(id=group_id)
        group.delete()
        return Response({"message": "Group deleted successfully"})
    except CompatibilityGroup.DoesNotExist:
        return Response({"error": "Group not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_compatibility_attribute(request):
    """Create a new compatibility attribute."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    group_id = request.data.get("group_id")
    name = request.data.get("name")

    if not group_id or not name:
        return Response(
            {"error": "Group ID and name are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        group = CompatibilityGroup.objects.get(id=group_id)
        attribute = CompatibilityAttribute.objects.create(group=group, name=name)
        serializer = CompatibilityAttributeSerializer(attribute)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    except CompatibilityGroup.DoesNotExist:
        return Response({"error": "Group not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_compatibility_attribute(request, attribute_id):
    """Update a compatibility attribute."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        attribute = CompatibilityAttribute.objects.get(id=attribute_id)

        if "name" in request.data:
            attribute.name = request.data["name"]
        if "group_id" in request.data:
            group = CompatibilityGroup.objects.get(id=request.data["group_id"])
            attribute.group = group

        attribute.save()
        serializer = CompatibilityAttributeSerializer(attribute)
        return Response(serializer.data)
    except CompatibilityAttribute.DoesNotExist:
        return Response(
            {"error": "Attribute not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except CompatibilityGroup.DoesNotExist:
        return Response({"error": "Group not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_compatibility_attribute(request, attribute_id):
    """Delete a compatibility attribute."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        attribute = CompatibilityAttribute.objects.get(id=attribute_id)
        attribute.delete()
        return Response({"message": "Attribute deleted successfully"})
    except CompatibilityAttribute.DoesNotExist:
        return Response(
            {"error": "Attribute not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_compatibility_value(request):
    """Create a new compatibility attribute value."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    attribute_id = request.data.get("attribute_id")
    value = request.data.get("value")
    display_name = request.data.get("display_name")

    if not attribute_id or not value or not display_name:
        return Response(
            {"error": "Attribute ID, value, and display name are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        attribute = CompatibilityAttribute.objects.get(id=attribute_id)
        attr_value = CompatibilityAttributeValue.objects.create(
            attribute=attribute, value=value, display_name=display_name
        )
        serializer = CompatibilityAttributeValueSerializer(attr_value)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    except CompatibilityAttribute.DoesNotExist:
        return Response(
            {"error": "Attribute not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_compatibility_value(request, value_id):
    """Update a compatibility attribute value."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        attr_value = CompatibilityAttributeValue.objects.get(id=value_id)

        if "value" in request.data:
            attr_value.value = request.data["value"]
        if "display_name" in request.data:
            attr_value.display_name = request.data["display_name"]
        if "attribute_id" in request.data:
            attribute = CompatibilityAttribute.objects.get(
                id=request.data["attribute_id"]
            )
            attr_value.attribute = attribute

        attr_value.save()
        serializer = CompatibilityAttributeValueSerializer(attr_value)
        return Response(serializer.data)
    except CompatibilityAttributeValue.DoesNotExist:
        return Response({"error": "Value not found"}, status=status.HTTP_404_NOT_FOUND)
    except CompatibilityAttribute.DoesNotExist:
        return Response(
            {"error": "Attribute not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_compatibility_value(request, value_id):
    """Delete a compatibility attribute value."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        attr_value = CompatibilityAttributeValue.objects.get(id=value_id)
        attr_value.delete()
        return Response({"message": "Value deleted successfully"})
    except CompatibilityAttributeValue.DoesNotExist:
        return Response({"error": "Value not found"}, status=status.HTTP_404_NOT_FOUND)


# Product Reservation API
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_reservation(request):
    """Create a reservation for an out-of-stock product."""
    try:
        product_id = request.data.get("product_id")

        if not product_id:
            return Response(
                {"error": "Product ID is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        product = Product.objects.get(id=product_id)

        # Check if user already has an active/waiting reservation for this product
        existing = ReservedProduct.objects.filter(
            product=product, user=request.user, status__in=["waiting", "active"]
        ).first()

        if existing:
            return Response(
                {
                    "error": "You already have a reservation for this product",
                    "reservation": ReservedProductSerializer(existing).data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Delete any old expired/fulfilled/cancelled reservations for this product by this user
        # This allows users to reserve again after their previous reservation ended
        ReservedProduct.objects.filter(
            product=product,
            user=request.user,
            status__in=["expired", "fulfilled", "cancelled"],
        ).delete()

        # Get the next queue position
        max_position = (
            ReservedProduct.objects.filter(
                product=product, status__in=["waiting", "active"]
            ).aggregate(models.Max("queue_position"))["queue_position__max"]
            or 0
        )

        # Create reservation
        reservation = ReservedProduct.objects.create(
            product=product,
            user=request.user,
            queue_position=max_position + 1,
            status="waiting",
        )

        # If product is in stock, activate the first reservation
        if product.stock > 0:
            from .utils import process_product_reservations

            process_product_reservations(product)
            reservation.refresh_from_db()

        serializer = ReservedProductSerializer(reservation)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    except Product.DoesNotExist:
        return Response(
            {"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Failed to create reservation: {str(e)}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_reservations(request):
    """Get all reservations for the current user."""
    reservations = (
        ReservedProduct.objects.filter(user=request.user)
        .select_related("product", "product__brand", "product__product_listing")
        .order_by("status", "queue_position")
    )

    serializer = ReservedProductSerializer(reservations, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_reservation(request, reservation_id):
    """Cancel a reservation."""
    try:
        reservation = ReservedProduct.objects.get(id=reservation_id, user=request.user)

        if reservation.status in ["fulfilled", "cancelled"]:
            return Response(
                {"error": "Cannot cancel this reservation"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        product = reservation.product
        reservation.cancel_reservation()

        # Reprocess queue to move everyone up and activate next person if needed
        from .utils import process_product_reservations

        process_product_reservations(product)

        return Response({"message": "Reservation cancelled successfully"})

    except ReservedProduct.DoesNotExist:
        return Response(
            {"error": "Reservation not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["GET"])
def check_product_reservation(request, product_id):
    """Check if a product has reservations and if current user is in queue."""
    try:
        product = Product.objects.get(id=product_id)

        # Get all active/waiting reservations for this product
        reservations = ReservedProduct.objects.filter(
            product=product, status__in=["waiting", "active"]
        ).order_by("queue_position")

        user_reservation = None
        if request.user.is_authenticated:
            user_reservation = reservations.filter(user=request.user).first()

        data = {
            "has_reservations": reservations.exists(),
            "total_in_queue": reservations.count(),
            "user_reservation": ReservedProductSerializer(user_reservation).data
            if user_reservation
            else None,
            "product_available": product.stock > 0
            and (
                # Product is available if no active reservations OR user has active reservation
                not reservations.filter(status="active").exists()
                or (user_reservation and user_reservation.status == "active")
            ),
        }

        return Response(data)

    except Product.DoesNotExist:
        return Response(
            {"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_all_reservations(request):
    """Get all reservations (staff only)."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    reservations = (
        ReservedProduct.objects.all()
        .select_related("product", "product__brand", "product__product_listing", "user")
        .order_by("product", "queue_position")
    )

    serializer = ReservedProductSerializer(reservations, many=True)
    return Response(serializer.data)


# Supplier Management API
@api_view(["GET"])
def get_all_suppliers(request):
    """Get all suppliers with their product counts and low stock alerts."""
    suppliers = ProductSupplier.objects.all().prefetch_related("supplier")

    supplier_data = []
    for supplier in suppliers:
        # Get products from this supplier
        products = Product.objects.filter(supply=supplier)

        # Count low stock items (assuming threshold is 10)
        low_stock_count = products.filter(stock__lt=10).count()
        total_products = products.count()

        # Calculate total stock value
        total_stock_value = sum(product.stock * product.price for product in products)

        supplier_data.append(
            {
                "id": supplier.id,
                "name": supplier.name,
                "contact": supplier.contact,
                "total_products": total_products,
                "low_stock_count": low_stock_count,
                "total_stock_value": total_stock_value,
                "has_low_stock": low_stock_count > 0,
            }
        )

    return Response(supplier_data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_supplier(request):
    """Create a new supplier."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        data = request.data
        name = data.get("name", "").strip()
        contact = data.get("contact", "").strip()

        if not name:
            return Response(
                {"error": "Supplier name is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if supplier with same name already exists
        if ProductSupplier.objects.filter(name__iexact=name).exists():
            return Response(
                {"error": "Supplier with this name already exists"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        supplier = ProductSupplier.objects.create(
            name=name, contact=contact if contact else None
        )

        # Return the created supplier data
        supplier_data = {
            "id": supplier.id,
            "name": supplier.name,
            "contact": supplier.contact,
            "total_products": 0,
            "low_stock_count": 0,
            "total_stock_value": 0,
            "has_low_stock": False,
        }

        create_audit_log(
            actor=request.user,
            action="create_supplier",
            module="suppliers",
            description=f"Created supplier '{supplier.name}'",
            metadata={
                "supplier_id": supplier.id,
                "contact": supplier.contact,
            },
            target_object=supplier,
            request=request,
        )

        return Response(supplier_data, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response(
            {"error": f"Failed to create supplier: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_supplier(request, supplier_id):
    """Update an existing supplier."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        data = request.data
        name = data.get("name", "").strip()
        contact = data.get("contact", "").strip()

        if not name:
            return Response(
                {"error": "Supplier name is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            supplier = ProductSupplier.objects.get(id=supplier_id)
        except ProductSupplier.DoesNotExist:
            return Response(
                {"error": "Supplier not found"}, status=status.HTTP_404_NOT_FOUND
            )

        original_data = {
            "name": supplier.name,
            "contact": supplier.contact,
        }

        # Check if another supplier with same name already exists
        existing_supplier = (
            ProductSupplier.objects.filter(name__iexact=name)
            .exclude(id=supplier_id)
            .first()
        )
        if existing_supplier:
            return Response(
                {"error": "Another supplier with this name already exists"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update the supplier
        supplier.name = name
        supplier.contact = contact if contact else None
        supplier.save()

        # Calculate updated stats
        products = Product.objects.filter(supply=supplier)
        total_products = products.count()
        low_stock_count = products.filter(stock__lt=10).count()
        total_stock_value = sum(p.price * p.stock for p in products)

        # Return the updated supplier data
        supplier_data = {
            "id": supplier.id,
            "name": supplier.name,
            "contact": supplier.contact,
            "total_products": total_products,
            "low_stock_count": low_stock_count,
            "total_stock_value": total_stock_value,
            "has_low_stock": low_stock_count > 0,
        }

        create_audit_log(
            actor=request.user,
            action="update_supplier",
            module="suppliers",
            description=f"Updated supplier '{supplier.name}'",
            metadata={
                "supplier_id": supplier.id,
                "original": original_data,
                "updated": {
                    "name": supplier.name,
                    "contact": supplier.contact,
                },
            },
            target_object=supplier,
            request=request,
        )

        return Response(supplier_data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Failed to update supplier: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_supplier(request, supplier_id):
    """Delete a supplier."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        try:
            supplier = ProductSupplier.objects.get(id=supplier_id)
        except ProductSupplier.DoesNotExist:
            return Response(
                {"error": "Supplier not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Check if supplier has products
        products_count = Product.objects.filter(supply=supplier).count()
        if products_count > 0:
            return Response(
                {
                    "error": f"Cannot delete supplier. {products_count} product(s) are still associated with this supplier."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        supplier_snapshot = {
            "id": supplier.id,
            "name": supplier.name,
            "contact": supplier.contact,
        }
        supplier_name = supplier.name
        supplier.delete()

        create_audit_log(
            actor=request.user,
            action="delete_supplier",
            module="suppliers",
            description=f"Deleted supplier '{supplier_name}'",
            severity="warning",
            metadata={"supplier": supplier_snapshot},
            target_object_id=supplier_snapshot["id"],
            target_object_repr=supplier_snapshot["name"],
            request=request,
        )

        return Response(
            {"message": f"Supplier '{supplier_name}' has been deleted successfully"},
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"error": f"Failed to delete supplier: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_supplier_products(request, supplier_id):
    """Get all products from a specific supplier with low stock alerts."""
    try:
        supplier = ProductSupplier.objects.get(id=supplier_id)
        products = Product.objects.filter(supply=supplier).select_related(
            "brand", "product_listing"
        )

        product_data = []
        for product in products:
            is_low_stock = product.stock < 10  # Assuming threshold is 10

            product_data.append(
                {
                    "id": product.id,
                    "name": product.name,
                    "variant_attribute": product.variant_attribute,
                    "brand": product.brand.name if product.brand else "No Brand",
                    "sku": product.sku,
                    "price": product.price,
                    "stock": product.stock,
                    "available": product.available,
                    "is_low_stock": is_low_stock,
                    "product_listing": {
                        "id": product.product_listing.id
                        if product.product_listing
                        else None,
                        "name": product.product_listing.name
                        if product.product_listing
                        else "No Listing",
                        "slug": product.product_listing.slug
                        if product.product_listing
                        else None,
                    }
                    if product.product_listing
                    else None,
                }
            )

        return Response(
            {
                "supplier": {
                    "id": supplier.id,
                    "name": supplier.name,
                    "contact": supplier.contact,
                },
                "products": product_data,
            }
        )
    except ProductSupplier.DoesNotExist:
        return Response(
            {"error": "Supplier not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_queue_item(request, item_id):
    """Update a service queue item status. Only accessible by staff."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        queue_item = ServiceQueue.objects.get(id=item_id)
        old_status = queue_item.status
        
        serializer = QueueSerializer(queue_item, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            
            # Check if status changed to completed
            queue_item.refresh_from_db()
            if queue_item.status == "completed" and old_status != "completed":
                from .utils import send_service_completion_email
                send_service_completion_email(queue_item)
            
            return Response(serializer.data)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except ServiceQueue.DoesNotExist:
        return Response(
            {"error": "Queue item not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_pending_services(request):
    """Return the customer's service queue along with pending status."""
    user_queue = (
        ServiceQueue.objects.filter(user=request.user)
        .select_related("user")
        .order_by("queue_date", "id")
    )

    serializer = QueueSerializer(user_queue, many=True)
    has_pending_services = user_queue.filter(status="pending").exists()

    return Response(
        {
            "has_pending_services": has_pending_services,
            "services": serializer.data,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_queue_item(request, item_id):
    """Allow a customer (or staff) to cancel a pending service queue entry."""
    try:
        queue_item = ServiceQueue.objects.get(id=item_id)
    except ServiceQueue.DoesNotExist:
        return Response(
            {"error": "Queue item not found"}, status=status.HTTP_404_NOT_FOUND
        )

    if queue_item.user != request.user and not request.user.is_staff:
        return Response(
            {"error": "You do not have permission to cancel this service."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if queue_item.status == "completed":
        return Response(
            {"error": "Completed services can no longer be cancelled."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    queue_item.delete()

    return Response({"message": "Service queue entry cancelled."})


@api_view(["GET"])
def get_queue_count(request):
    """Get the number of pending queue items for a specific date."""
    queue_date = request.GET.get("queue_date")
    if not queue_date:
        return Response(
            {"error": "queue_date parameter is required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        from datetime import datetime
        date_obj = datetime.strptime(queue_date, "%Y-%m-%d").date()
    except ValueError:
        return Response(
            {"error": "Invalid date format. Use YYYY-MM-DD"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Count pending items for this date
    count = ServiceQueue.objects.filter(
        queue_date=date_obj,
        status="pending"
    ).count()
    
    return Response({
        "queue_date": queue_date,
        "count": count,
        "max_customer_limit": 10,
        "is_full": count >= 10
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def schedule_service(request):
    # Support both customer self-service and staff adding for customer
    print(f"DEBUG schedule_service: request.user={request.user}, is_authenticated={request.user.is_authenticated}, is_staff={request.user.is_staff}")
    
    user_id = request.data.get("user")  # Staff can specify customer ID
    is_staff_request = bool(user_id and user_id != request.user.id)
    
    # If trying to add service for another user, must be staff
    if is_staff_request and not request.user.is_staff:
        print(f"DEBUG schedule_service: PERMISSION DENIED - User {request.user.id} is not staff")
        return Response(
            {"error": "Only staff members can add services for other users. Please ensure your account has staff permissions."},
            status=status.HTTP_403_FORBIDDEN
        )
    
    if not user_id:
        user_id = request.user.id  # Default to current user (customer self-service)
    
    print(f"DEBUG schedule_service: Received user_id={user_id}, is_staff={is_staff_request}")
    print(f"DEBUG schedule_service: Request data={request.data}")
    
    queue_date_str = request.data.get("queue_date")
    if not queue_date_str:
        return Response(
            {"error": "queue_date is required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check queue limit for customers (not for staff)
    if not is_staff_request:
        from datetime import datetime
        try:
            queue_date_obj = datetime.strptime(queue_date_str, "%Y-%m-%d").date()
            current_count = ServiceQueue.objects.filter(
                queue_date=queue_date_obj,
                status="pending"
            ).count()
            
            if current_count >= 10:
                return Response(
                    {
                        "error": f"This date is fully booked (10 customers). Please choose another date or contact staff for assistance.",
                        "queue_count": current_count,
                        "max_limit": 10
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    data = {
        "queue_date": queue_date_str,
        "info": request.data.get("info"),
        "status": "pending",
        "user_id": user_id,  # Use user_id for the serializer
    }

    serializer = QueueSerializer(data=data)
    if serializer.is_valid():
        queue_item = serializer.save()
        print(f"DEBUG schedule_service: Created queue item {queue_item.id} for user {queue_item.user_id}")
        
        # Re-fetch with user relation to ensure user data is included
        queue_item = ServiceQueue.objects.select_related('user').get(id=queue_item.id)
        serializer = QueueSerializer(queue_item)
        
        print(f"DEBUG schedule_service: Serialized data has user={serializer.data.get('user')}")
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    else:
        print(f"DEBUG schedule_service: Validation errors={serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Inventory Management API
@api_view(["GET"])
def get_inventory(request):
    """Get all products for inventory management."""
    products = Product.objects.all().select_related("brand", "product_listing")
    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def get_inventory_item(request, product_id):
    """Get a specific product for inventory management."""
    try:
        product = Product.objects.get(pk=product_id)
        serializer = ProductSerializer(product)
        return Response(serializer.data)
    except Product.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(["PUT"])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def update_inventory_item(request, product_id):
    """Update product inventory (stock, price, availability)."""
    try:
        product = Product.objects.get(pk=product_id)
        old_stock = product.stock
        change_summary = {}

        simple_fields = [
            "stock",
            "price",
            "available",
            "name",
            "sku",
            "variant_attribute",
            "brand",
            "supplier_id",
        ]

        for field in simple_fields:
            if field in request.data:
                value = request.data.get(field)
                if isinstance(value, list):
                    value = value[0] if value else None

                if field == "available" and isinstance(value, str):
                    change_summary[field] = value.lower() in ["1", "true", "yes", "on"]
                else:
                    change_summary[field] = value

        if request.FILES:
            change_summary["uploaded_images"] = [file.name for file in request.FILES.values()]

        # Update fields if provided
        if "stock" in request.data:
            product.stock = int(request.data["stock"])
        if "price" in request.data:
            product.price = request.data["price"]
        if "available" in request.data:
            # Convert string to boolean (FormData sends '1' or '0')
            available_value = request.data["available"]
            if isinstance(available_value, str):
                product.available = available_value in ["1", "true", "True"]
            else:
                product.available = bool(available_value)
        if "name" in request.data:
            product.name = request.data["name"]
        if "sku" in request.data:
            product.sku = request.data["sku"]
        if "variant_attribute" in request.data:
            product.variant_attribute = request.data["variant_attribute"]
        if "brand" in request.data:
            brand_id = request.data["brand"]
            # Handle potential list values from FormData
            if isinstance(brand_id, list):
                brand_id = brand_id[0] if brand_id else None
            if brand_id:
                try:
                    brand = Brands.objects.get(pk=brand_id)
                    product.brand = brand
                except Brands.DoesNotExist:
                    pass
        if "supplier_id" in request.data:
            supplier_id = request.data["supplier_id"]
            # Handle potential list values from FormData
            if isinstance(supplier_id, list):
                supplier_id = supplier_id[0] if supplier_id else None
            if supplier_id:
                try:
                    supplier = ProductSupplier.objects.get(pk=supplier_id)
                    product.supply = supplier
                except ProductSupplier.DoesNotExist:
                    pass
            else:
                product.supply = None

        product.save()

        # Handle images from request.FILES
        for key in list(request.FILES.keys()):
            if key.startswith("image_"):
                image_file = request.FILES[key]
                ProductVariantImage.objects.create(
                    product=product,
                    image=image_file,
                    alt_text=product.name or "Product image",
                )

        # If stock was increased, process reservations
        if product.stock > old_stock:
            from .utils import process_product_reservations

            process_product_reservations(product)

        # Send realtime inventory update
        serializer = ProductSerializer(product)
        send_inventory_update(serializer.data)

        create_audit_log(
            actor=request.user,
            action="update_inventory_item",
            module="inventory",
            description=f"Updated inventory item #{product.id} - {product.name}",
            metadata={
                "product_id": product.id,
                "changes": change_summary,
            },
            target_object=product,
            request=request,
        )

        return Response(serializer.data, status=status.HTTP_200_OK)
    except Product.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def create_inventory_item(request):
    """Create a new product in inventory."""
    try:
        # Log the incoming data
        logger.info(f"Creating inventory item with data: {request.data}")

        # Extract brand and supplier_id to handle separately
        data = request.data.copy()
        brand_id = data.pop("brand", None)
        supplier_id = data.pop("supplier_id", None)

        # Handle potential list values from FormData
        if isinstance(brand_id, list):
            brand_id = brand_id[0] if brand_id else None
        if isinstance(supplier_id, list):
            supplier_id = supplier_id[0] if supplier_id else None

        # Extract images from request.FILES
        images = []
        for key in list(request.FILES.keys()):
            if key.startswith("image_"):
                images.append(request.FILES[key])

        serializer = ProductSerializer(data=data)
        if serializer.is_valid():
            product = serializer.save()

            # Set brand if provided
            if brand_id:
                try:
                    brand = Brands.objects.get(pk=brand_id)
                    product.brand = brand
                except Brands.DoesNotExist:
                    pass

            # Set supplier if provided
            if supplier_id:
                try:
                    supplier = ProductSupplier.objects.get(pk=supplier_id)
                    product.supply = supplier
                except ProductSupplier.DoesNotExist:
                    pass

            product.save()

            # Create product images
            for image_file in images:
                ProductVariantImage.objects.create(
                    product=product,
                    image=image_file,
                    alt_text=product.name or "Product image",
                )

            # Send realtime inventory update with refreshed data
            updated_serializer = ProductSerializer(product)
            send_inventory_update(updated_serializer.data)

            create_audit_log(
                actor=request.user,
                action="create_inventory_item",
                module="inventory",
                description=f"Created inventory item #{product.id} - {product.name}",
                metadata={
                    "product_id": product.id,
                    "name": product.name,
                    "brand_id": product.brand_id,
                    "supplier_id": product.supply_id,
                    "stock": product.stock,
                    "price": float(product.price) if product.price is not None else None,
                },
                target_object=product,
                request=request,
            )

            return Response(updated_serializer.data, status=status.HTTP_201_CREATED)
        else:
            logger.error(f"Serializer validation failed: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Failed to create inventory item: {str(e)}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_product_image(request, image_id):
    """Delete a product variant image."""
    try:
        image = ProductVariantImage.objects.get(pk=image_id)
        product = image.product
        image_name = image.image.name if image.image else ""
        image.delete()

        # Send realtime inventory update
        if product:
            serializer = ProductSerializer(product)
            send_inventory_update(serializer.data)

        create_audit_log(
            actor=request.user,
            action="delete_inventory_image",
            module="inventory",
            description=f"Deleted product image #{image_id}",
            severity="warning",
            metadata={
                "image_id": image_id,
                "product_id": product.id if product else None,
                "image_name": image_name,
            },
            target_object_id=image_id,
            target_object_repr=image_name,
            request=request,
        )

        return Response(
            {"message": "Image deleted successfully"}, status=status.HTTP_200_OK
        )
    except ProductVariantImage.DoesNotExist:
        return Response({"error": "Image not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_inventory_item(request, product_id):
    """Delete a product from inventory."""
    try:
        product = Product.objects.get(pk=product_id)
        product_data = ProductSerializer(product).data
        product.delete()

        # Send realtime inventory update with deleted item info
        send_inventory_update(
            {"action": "deleted", "product_id": product_id, "data": product_data}
        )

        create_audit_log(
            actor=request.user,
            action="delete_inventory_item",
            module="inventory",
            description=f"Deleted inventory item #{product_id}",
            severity="warning",
            metadata={
                "product_id": product_id,
                "product_snapshot": product_data,
            },
            target_object_id=product_id,
            target_object_repr=product_data.get("name", ""),
            request=request,
        )

        return Response(status=status.HTTP_204_NO_CONTENT)
    except Product.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def bulk_update_inventory(request):
    """Bulk update multiple inventory items."""
    updates = request.data.get("updates", [])
    updated_products = []

    for update in updates:
        try:
            product = Product.objects.get(pk=update["id"])

            if "stock" in update:
                product.stock = update["stock"]
            if "price" in update:
                product.price = update["price"]
            if "available" in update:
                product.available = update["available"]

            product.save()
            updated_products.append(ProductSerializer(product).data)
        except Product.DoesNotExist:
            continue

    # Send realtime inventory update for all changes
    send_inventory_update({"action": "bulk_update", "data": updated_products})

    create_audit_log(
        actor=request.user,
        action="bulk_update_inventory",
        module="inventory",
        description=f"Bulk updated {len(updated_products)} inventory item(s)",
        metadata={
            "requested_updates": updates,
            "updated_product_ids": [item.get("id") for item in updated_products],
            "applied_count": len(updated_products),
        },
        request=request,
    )

    return Response({"updated_count": len(updated_products)}, status=status.HTTP_200_OK)


@api_view(["POST"])
def test_inventory_update(request):
    """Test endpoint to manually trigger inventory WebSocket update."""
    test_data = {
        "id": 999,
        "name": "Test Product",
        "variant_attribute": "Test Variant",
        "brand": "Test Brand",
        "price": 100.00,
        "stock": 5,
        "sku": "TEST123",
        "available": True,
    }

    print(f"DEBUG: Test endpoint called, sending inventory update")
    send_inventory_update(test_data)

    return Response({"message": "Test inventory update sent", "data": test_data})


@api_view(["GET"])
def dashboard_data(request):
    """Get dashboard data for staff users"""
    if not request.user.is_authenticated or not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        from datetime import date, timedelta

        # Get today's date
        today = date.today()

        # Get real data from models
        dashboard_data = {
            "new_chats": 5,  # Mock data for now - would query unread chat messages
            "new_orders": Order.objects.filter(status="pending").count(),
            "service_queue_today": {
                "pending": ServiceQueue.objects.filter(
                    queue_date=today, status="pending"
                ).count(),
                "completed": ServiceQueue.objects.filter(
                    queue_date=today, status="completed"
                ).count(),
            },
        }

        return Response(dashboard_data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Note: Checkout session creation is now handled directly in the frontend
# The frontend calls PayMongo API directly for better performance and reduced backend complexity


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_paymongo_checkout_session(request):
    """Create a PayMongo checkout session (server-side, uses secret key)"""
    try:
        from .paymongo_service import PayMongoService
        from django.conf import settings
        
        order_id = request.data.get("order_id")
        if not order_id:
            return Response(
                {"error": "order_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the order
        try:
            order = Order.objects.get(id=order_id, user=request.user)
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get frontend URL from request or use settings
        frontend_url = request.data.get("frontend_url") or settings.FRONTEND_URL
        
        # Prepare line items
        line_items = []
        for item in order.items.select_related('product').all():
            amount = int(float(item.product.price) * item.quantity * 100)  # Convert to centavos
            line_items.append({
                "currency": "PHP",
                "amount": amount,
                "name": f"{item.product.name} {item.product.variant_attribute or ''}".strip(),
                "quantity": item.quantity,
            })
        
        # Prepare billing info
        billing = {
            "name": f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
            "email": request.user.email,
            "phone": order.contact_number or None,
        }
        
        # Prepare metadata
        metadata = {
            "order_id": str(order.id),
            "customer_name": billing["name"],
            "customer_email": billing["email"],
        }
        
        # Create checkout session using PayMongo service
        paymongo_service = PayMongoService()
        
        # Build success and cancel URLs
        success_url = f"{frontend_url}/payment/success?order_id={order_id}"
        cancel_url = f"{frontend_url}/payment/cancel?order_id={order_id}"
        
        # Create checkout session
        checkout_session = paymongo_service._make_request(
            "POST",
            "/checkout_sessions",
            {
                "data": {
                    "attributes": {
                        "billing": billing,
                        "send_email_receipt": True,
                        "show_description": True,
                        "show_line_items": True,
                        "line_items": line_items,
                        "payment_method_types": ["card", "gcash", "paymaya", "dob", "qrph"],
                        "success_url": success_url,
                        "cancel_url": cancel_url,
                        "description": f"Order #{order_id}",
                        "metadata": metadata,
                    }
                }
            }
        )
        
        return Response(checkout_session, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Failed to create PayMongo checkout session: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response(
            {"error": f"Failed to create checkout session: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
def confirm_payment(request, order_id):
    """
    Get payment status for an order - Read-only endpoint
    Note: Webhook handles actual payment processing (cart clearing, inventory, status updates)
    This endpoint just returns the current order status
    """
    if not request.user.is_authenticated:
        return Response(
            {"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED
        )

    try:
        logger.info(f"=== GET PAYMENT STATUS ===")
        logger.info(f"Order ID: {order_id}")
        logger.info(f"User: {request.user.username}")

        # Get the order - just return current status
        try:
            order = (
                Order.objects.select_related("sale")
                .get(id=order_id, user=request.user)
            )
            payment_status_value = order.sale.payment_status if order.sale else None
            logger.info(
                f"Order found: ID={order.id}, Status={order.status}, Payment Status={payment_status_value}"
            )
        except Order.DoesNotExist:
            logger.error(f"Order {order_id} not found for user {request.user.username}")
            return Response(
                {"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Serialize and return order data
        order_serializer = OrderSerializer(order)

        return Response(
            {
                "order": order_serializer.data,
                "payment_status": payment_status_value,
                "status": order.status,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(f"Error getting payment status: {str(e)}")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_order(request, order_id):
    """Cancel an order - customer only, for to_pay and to_ship orders"""
    try:
        order = Order.objects.get(pk=order_id, user=request.user)

        # Only allow cancellation for to_pay and to_ship orders
        if order.status not in ["to_pay", "to_ship"]:
            return Response(
                {
                    "error": 'Order cannot be cancelled. Only orders with status "To Pay" or "To Ship" can be cancelled.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update order status to cancelled
        order.status = "cancelled"
        order.save()

        # If order was paid, we might want to handle refunds here
        # For now, we'll just mark it as cancelled

        # Send realtime update
        order_serializer = OrderSerializer(order)
        send_order_update(request.user.id, order_serializer.data)

        return Response(
            {"message": "Order cancelled successfully", "order": order_serializer.data}
        )

    except Order.DoesNotExist:
        return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error cancelling order {order_id}: {str(e)}")
        return Response(
            {"error": "Failed to cancel order"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def user_info(request):
    """Get current user information including user_info details"""
    try:
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_profile(request):
    """Get current user's profile information including notification preferences"""
    try:
        user = request.user
        user_profile, created = UserProfile.objects.get_or_create(user=user)
        
        # Return user data with profile info
        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_user_profile(request):
    """Update current user's profile information"""
    try:
        user = request.user
        
        # Update user's basic info
        if 'first_name' in request.data:
            user.first_name = request.data['first_name']
        if 'last_name' in request.data:
            user.last_name = request.data['last_name']
        user.save()
        
        # Get or create user profile
        user_profile, created = UserProfile.objects.get_or_create(user=user)
        
        # Update profile fields
        if 'contact_number' in request.data:
            # Validate phone number format
            phone = request.data['contact_number']
            if phone:
                # Remove spaces and dashes
                clean_phone = phone.replace(' ', '').replace('-', '')
                # Validate format: 11 digits starting with 09
                import re
                if not re.match(r'^09\d{9}$', clean_phone):
                    return Response(
                        {"error": "Phone must be 11 digits starting with 09"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                user_profile.contact_number = clean_phone
            else:
                user_profile.contact_number = ''
                
        if 'address' in request.data:
            user_profile.address = request.data['address']
            
        # Handle image upload
        if 'image' in request.FILES:
            user_profile.image = request.FILES['image']
        
        # Handle notification preferences
        if 'email_order_updates' in request.data:
            user_profile.email_order_updates = request.data['email_order_updates']
        if 'email_reservation_updates' in request.data:
            user_profile.email_reservation_updates = request.data['email_reservation_updates']
        if 'email_service_updates' in request.data:
            user_profile.email_service_updates = request.data['email_service_updates']
            
        user_profile.save()
        
        # Return updated user data
        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {"error": str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_chat_rooms(request):
    """Get all active chat rooms for staff."""
    print(f"\n{'='*80}")
    print(f"GET CHAT ROOMS REQUEST")
    print(f"User: {request.user.username}")
    print(f"Is Staff: {request.user.is_staff}")
    print(f"{'='*80}\n")

    if not request.user.is_staff:
        print("ERROR: User is not staff, returning 403")
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        from django.db.models import Prefetch, Q
        from datetime import timedelta

        # Get all active chat rooms (remove 24 hour filter for now to show all rooms)
        chat_rooms = (
            ChatRoom.objects.filter(is_active=True)
            .select_related("owner")
            .prefetch_related(
                Prefetch(
                    "chat_items",
                    queryset=ChatItem.objects.select_related("sender").order_by("-sent_at"),
                    to_attr="ordered_chat_items"
                )
            )
            .annotate(
                message_count=Count("chat_items"),
                last_message_time=Max("chat_items__sent_at"),
            )
            .distinct()
            .order_by("-last_message_time")
        )

        print(f"Query executed. Found {chat_rooms.count()} active chat rooms")
        logger.info(f"Found {chat_rooms.count()} active chat rooms")

        # Format the response
        chat_rooms_data = []
        for room in chat_rooms:
            print(
                f"Processing room ID={room.id}, owner={room.owner.username}, is_active={room.is_active}"
            )
            logger.info(f"Processing room {room.id} for owner {room.owner.username}")

            # Get the most recent message
            latest_message = room.chat_items.select_related("sender").order_by("-sent_at").first()
            print(
                f"  Latest message: {latest_message.message if latest_message else 'None'}"
            )
            if latest_message and latest_message.sender:
                print(f"  Latest message sender: {latest_message.sender.username} (ID: {latest_message.sender.id})")

            # Get customer info
            customer_name = room.owner.get_full_name() or room.owner.username
            # Default avatar (None - frontend will use placeholder)
            customer_avatar = None

            # Get avatar if user has profile image
            if hasattr(room.owner, "user_info") and room.owner.user_info.exists():
                user_profile = room.owner.user_info.first()
                if user_profile and user_profile.image:
                    customer_avatar = user_profile.image.url

            # Format timestamp for display
            formatted_timestamp = ""
            if latest_message:
                formatted_timestamp = latest_message.sent_at.strftime("%I:%M %p")

            # Compute unread customer messages for staff
            unread_count = (
                room.chat_items.filter(
                    message_type="customer",
                ).count()
                if not room.is_read_staff
                else 0
            )

            # Generate room_id in format expected by frontend (customer_{user_id})
            room_id = f"customer_{room.owner.id}"

            room_data = {
                "id": room_id,  # Use string format for frontend
                "customer_id": room.owner.id,
                "customer_name": customer_name,
                "customer_avatar": customer_avatar,
                "last_message": latest_message.message
                if latest_message
                else "No messages yet",
                "last_message_type": latest_message.message_type if latest_message else None,
                "last_message_sender_id": latest_message.sender.id if latest_message and latest_message.sender else None,
                "formatted_timestamp": formatted_timestamp,
                "timestamp": latest_message.sent_at.strftime("%I:%M %p")
                if latest_message
                else "",
                "message_count": room.message_count,
                "unread_count": unread_count,
                "is_online": True,  # Assume online if there's recent activity
                "is_read_staff": room.is_read_staff,
                "is_read_customer": room.is_read_customer,
            }
            chat_rooms_data.append(room_data)
            print(
                f"  Added room data: id={room_data['id']}, customer={room_data['customer_name']}"
            )
            logger.info(f"Added room data: {room_data}")

        print(f"\nReturning {len(chat_rooms_data)} chat rooms")
        print(
            f"Response: {{'success': True, 'chat_rooms': {len(chat_rooms_data)} rooms}}"
        )
        print(f"{'='*80}\n")

        logger.info(f"Returning {len(chat_rooms_data)} chat rooms")
        return Response({"success": True, "chat_rooms": chat_rooms_data})

    except Exception as e:
        print(f"\nERROR in get_chat_rooms: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        print(f"{'='*80}\n")

        logger.error(f"Error fetching chat rooms: {str(e)}")
        return Response(
            {"error": f"Failed to fetch chat rooms: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@csrf_exempt
@api_view(["POST"])
def paymongo_webhook(request):
    """Handle PayMongo webhooks"""
    try:
        # Print webhook received
        print("\n" + "=" * 80)
        print("🔔 PAYMONGO WEBHOOK RECEIVED")
        print("=" * 80)
        print(f"📅 Timestamp: {timezone.now()}")
        print(f"🌐 Remote Address: {request.META.get('REMOTE_ADDR', 'Unknown')}")
        print(f"📋 Headers:")
        for header, value in request.headers.items():
            if header.lower() in ["content-type", "user-agent", "paymongo-signature"]:
                print(f"   {header}: {value}")
        print("\n📦 Raw Request Body:")
        print(request.body.decode("utf-8") if request.body else "Empty body")
        print("\n" + "-" * 80)

        # Get webhook data
        webhook_data = request.data.get("data", {})
        attributes = webhook_data.get("attributes", {})
        event_type = attributes.get("type")  # Note: event type is in attributes.type

        print(f"📌 Event Type: {event_type}")
        print(f"📊 Webhook Data: {webhook_data}")
        print(f"🔍 Attributes: {attributes}")
        print("-" * 80 + "\n")

        # Handle checkout session payment events
        if event_type == "checkout_session.payment.paid":
            # Handle successful checkout session payment
            checkout_data = attributes.get("data", {})
            checkout_attributes = checkout_data.get("attributes", {})
            metadata = checkout_attributes.get("metadata", {})
            payments = checkout_attributes.get("payments", [])

            order_id = metadata.get("order_id")
            print(f"🔍 Order ID from metadata: {order_id}")
            print(f"💳 Payments array: {payments}")

            # Check payment status from the payments array
            payment_status = None
            payment_source_type = None
            payment_id = None
            if payments and len(payments) > 0:
                # Extract payment ID directly from webhook data
                payment_id = payments[0].get("id")
                payment_attrs = payments[0].get("attributes", {})
                payment_status = payment_attrs.get("status")
                # Extract payment source type
                source = payment_attrs.get("source", {})
                payment_source_type = source.get("type")
                print(f"💰 Payment Status: {payment_status}")
                print(f"💳 Payment Source Type: {payment_source_type}")
                print(f"🔑 Payment ID from webhook: {payment_id}")

            if order_id and payment_status == "paid":
                try:
                    order = (
                        Order.objects.select_related("sale")
                        .get(id=order_id)
                    )
                    sale = _ensure_sale_for_order(order)
                    print(
                        f"📦 Order found: {order.id} - Current status: {order.status}, Sale payment status: {sale.payment_status}"
                    )
                    print(f"🔑 Checkout Session ID: {sale.paymongo_checkout_session_id}")
                    print(f"💳 Current Payment ID: {sale.paymongo_payment_id}")

                    sale_updates: List[str] = []
                    if payment_source_type:
                        mapped_payment_method = map_paymongo_source_to_payment_method(
                            payment_source_type
                        )
                        if sale.payment_method != mapped_payment_method:
                            sale.payment_method = mapped_payment_method
                            sale_updates.append("payment_method")
                        print(
                            f"💳 Sale payment method updated to: {mapped_payment_method} (from source: {payment_source_type})"
                        )

                    sale.payment_status = "paid"
                    sale.payment_date = timezone.now()
                    sale_updates.extend(["payment_status", "payment_date"])

                    if payment_id:
                        sale.paymongo_payment_id = payment_id
                        sale_updates.append("paymongo_payment_id")
                        print(f"✅ Payment ID set from webhook data: {payment_id}")

                    checkout_session_identifier = checkout_data.get("id")
                    if (
                        checkout_session_identifier
                        and not sale.paymongo_checkout_session_id
                    ):
                        sale.paymongo_checkout_session_id = checkout_session_identifier
                        sale_updates.append("paymongo_checkout_session_id")

                    if sale_updates:
                        sale.save(update_fields=list(set(sale_updates)))

                    # Also try to fetch full checkout session data as backup
                    if sale.paymongo_checkout_session_id and not payment_id:
                        try:
                            import requests
                            from django.conf import settings

                            paymongo_secret = settings.PAYMONGO_SECRET_KEY
                            if paymongo_secret:
                                checkout_session_url = f"https://api.paymongo.com/v1/checkout_sessions/{sale.paymongo_checkout_session_id}"

                                print(
                                    f"🔍 Fetching checkout session from: {checkout_session_url}"
                                )

                                # Encode secret key as base64 for Basic auth
                                import base64
                                auth_string = f"{paymongo_secret}:"
                                encoded_auth = base64.b64encode(auth_string.encode()).decode()

                                response = requests.get(
                                    checkout_session_url,
                                    headers={
                                        "accept": "application/json",
                                        "authorization": f"Basic {encoded_auth}"
                                    }
                                )

                                print(f"📡 Response Status: {response.status_code}")

                                if response.status_code == 200:
                                    session_data = response.json()
                                    print(f"📦 Session data keys: {session_data.keys()}")
                                    
                                    session_payments = (
                                        session_data.get("data", {})
                                        .get("attributes", {})
                                        .get("payments", [])
                                    )

                                    print(f"💰 Found {len(session_payments)} payment(s) in session")

                                    if session_payments and len(session_payments) > 0:
                                        payment_id = session_payments[0].get("id")
                                        print(f"🔍 Payment ID from session: {payment_id}")
                                        
                                        if payment_id:
                                            sale.paymongo_payment_id = payment_id
                                            sale.save(update_fields=["paymongo_payment_id"])
                                            print(
                                                f"✅ Payment ID set on sale object: {payment_id}"
                                            )
                                        else:
                                            print(
                                                f"⚠️ No payment ID found in checkout session"
                                            )
                                    else:
                                        print(
                                            f"⚠️ No payments found in checkout session"
                                        )
                                        print(f"Session attributes keys: {session_data.get('data', {}).get('attributes', {}).keys()}")
                                else:
                                    print(
                                        f"⚠️ Failed to fetch checkout session: {response.status_code}"
                                    )
                                    print(f"Response body: {response.text}")
                            else:
                                print(
                                    f"⚠️ PAYMONGO_SECRET_KEY not configured, skipping payment ID fetch"
                                )
                        except Exception as e:
                            print(f"⚠️ Error fetching checkout session: {str(e)}")
                            import traceback
                            traceback.print_exc()
                            # Don't fail the webhook if we can't fetch payment ID

                    order_updates: List[str] = []
                    if order.status == "to_pay":
                        order.status = "to_ship"
                        order_updates.append("status")
                    if order.is_cod:
                        order.is_cod = False
                        order_updates.append("is_cod")

                    if order_updates:
                        order.save(update_fields=list(set(order_updates)))

                    # Refresh from database to confirm it was saved
                    order.refresh_from_db()
                    sale.refresh_from_db()
                    
                    print("\n" + "=" * 80)
                    print("💾 ORDER SAVED - FINAL STATE:")
                    print("=" * 80)
                    print(f"Order ID: {order.id}")
                    print(f"Status: {order.status}")
                    print(f"Sale Payment Status: {sale.payment_status}")
                    print(f"Checkout Session ID: {sale.paymongo_checkout_session_id}")
                    print(f"⭐ PAYMENT ID: {sale.paymongo_payment_id}")
                    print("=" * 80 + "\n")

                    # Deduct inventory and clear cart
                    deduct_inventory_for_order(order)
                    clear_reserved_cart(order.user.id, order.id)

                    print(f"🗑️ Cart cleared for user {order.user.id}")

                    # Send realtime updates
                    order_serializer = OrderSerializer(order)
                    send_order_update(order.user.id, order_serializer.data)

                    # Send realtime cart update (empty cart)
                    try:
                        cart = Cart.objects.get(user=order.user)
                        cart_serializer = CartSerializer(cart)
                        send_cart_update(order.user.id, cart_serializer.data)
                    except Cart.DoesNotExist:
                        # Cart already deleted, send empty cart
                        send_cart_update(order.user.id, {"items": [], "total": 0})

                    # Send notification
                    send_notification(
                        order.user.id,
                        {
                            "type": "payment_success",
                            "message": f"Payment for Order #{order.id} has been confirmed",
                            "order_id": order.id,
                        },
                    )

                    print(
                        f"✅ Payment successful webhook processed for order {order.id}"
                    )

                except Order.DoesNotExist:
                    logger.error(f"Order {order_id} not found for webhook")
                    print(f"❌ ERROR: Order {order_id} not found for webhook")

        elif event_type == "checkout_session.payment.failed":
            # Handle failed checkout session payment
            checkout_data = attributes.get("data", {})
            checkout_attributes = checkout_data.get("attributes", {})
            metadata = checkout_attributes.get("metadata", {})
            order_id = metadata.get("order_id")

            if order_id:
                try:
                    order = (
                        Order.objects.select_related("sale")
                        .get(id=order_id)
                    )
                    sale = _ensure_sale_for_order(order)
                    sale.payment_status = "failed"
                    sale.payment_date = None
                    sale.save(update_fields=["payment_status", "payment_date"])

                    print(
                        f"⚠️ Payment failed for order {order.id} - status remains 'to_pay'"
                    )

                    # Send realtime updates
                    order_serializer = OrderSerializer(order)
                    send_order_update(order.user.id, order_serializer.data)

                    # Send notification
                    send_notification(
                        order.user.id,
                        {
                            "type": "payment_failed",
                            "message": f"Payment for Order #{order.id} has failed. Please try again.",
                            "order_id": order.id,
                        },
                    )

                except Order.DoesNotExist:
                    logger.error(f"Order {order_id} not found for webhook")
                    print(f"❌ ERROR: Order {order_id} not found for webhook")

        # Legacy payment intent events (keep for backward compatibility)
        elif event_type == "payment_intent.succeeded":
            from .paymongo_service import update_order_payment_status

            # Handle successful payment intent
            payment_intent_data = attributes.get("data", {})
            payment_intent_attrs = payment_intent_data.get("attributes", {})
            metadata = payment_intent_attrs.get("metadata", {})
            order_id = metadata.get("order_id")

            if order_id:
                try:
                    order = (
                        Order.objects.select_related("sale")
                        .get(id=order_id)
                    )
                    sale = _ensure_sale_for_order(order)

                    # Extract payment source type from payments array
                    payments = payment_intent_attrs.get("payments", [])
                    if payments and len(payments) > 0:
                        source = payments[0].get("attributes", {}).get("source", {})
                        payment_source_type = source.get("type")
                        if payment_source_type:
                            mapped_payment_method = (
                                map_paymongo_source_to_payment_method(
                                    payment_source_type
                                )
                            )
                            if sale.payment_method != mapped_payment_method:
                                sale.payment_method = mapped_payment_method
                                sale.save(update_fields=["payment_method"])
                            print(
                                f"💳 Payment method updated to: {mapped_payment_method} (from source: {payment_source_type})"
                            )

                    update_order_payment_status(order, {"data": payment_intent_data})

                    # Deduct inventory and clear reserved cart for successful payment
                    deduct_inventory_for_order(order)
                    clear_reserved_cart(order.user.id, order.id)

                    # Send realtime updates
                    order_serializer = OrderSerializer(order)
                    send_order_update(order.user.id, order_serializer.data)

                    # Send notification
                    send_notification(
                        order.user.id,
                        {
                            "type": "payment_success",
                            "message": f"Payment for Order #{order.id} has been confirmed",
                            "order_id": order.id,
                        },
                    )

                except Order.DoesNotExist:
                    logger.error(f"Order {order_id} not found for webhook")

        elif event_type == "payment_intent.payment_failed":
            # Handle failed payment intent
            payment_intent_data = attributes.get("data", {})
            metadata = payment_intent_data.get("attributes", {}).get("metadata", {})
            order_id = metadata.get("order_id")

            if order_id:
                try:
                    order = (
                        Order.objects.select_related("sale")
                        .get(id=order_id)
                    )
                    sale = _ensure_sale_for_order(order)
                    sale.payment_status = "failed"
                    sale.payment_date = None
                    sale.save(update_fields=["payment_status", "payment_date"])

                    # Send realtime updates
                    order_serializer = OrderSerializer(order)
                    send_order_update(order.user.id, order_serializer.data)

                    # Send notification
                    send_notification(
                        order.user.id,
                        {
                            "type": "payment_failed",
                            "message": f"Payment for Order #{order.id} has failed",
                            "order_id": order.id,
                        },
                    )

                except Order.DoesNotExist:
                    logger.error(f"Order {order_id} not found for webhook")
                    print(f"❌ ERROR: Order {order_id} not found for webhook")

        print("=" * 80)
        print("✅ WEBHOOK PROCESSED SUCCESSFULLY")
        print(f"Event Type: {event_type}")
        print("=" * 80 + "\n")

        return Response({"status": "success"}, status=status.HTTP_200_OK)

    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ WEBHOOK ERROR")
        print("=" * 80)
        print(f"Error: {str(e)}")
        print(f"Type: {type(e).__name__}")
        import traceback

        print(f"Traceback:\n{traceback.format_exc()}")
        print("=" * 80 + "\n")

        logger.error(f"Error handling PayMongo webhook: {str(e)}")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# Bike Builder & Compatibility API
@api_view(["GET"])
def get_compatibility_groups(request):
    """Get all compatibility groups with their attributes and values"""
    groups = CompatibilityGroup.objects.prefetch_related("attributes__values").all()
    serializer = CompatibilityGroupSerializer(groups, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
def get_compatibility_attributes(request):
    """Get all compatibility attributes"""
    attributes = CompatibilityAttribute.objects.select_related("group").all()
    serializer = CompatibilityAttributeSerializer(attributes, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
def get_compatibility_attribute_values(request):
    """Get all compatibility attribute values"""
    values = CompatibilityAttributeValue.objects.select_related(
        "attribute", "attribute__group"
    ).all()
    serializer = CompatibilityAttributeValueSerializer(values, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
def get_bike_builder_products(request):
    """
    Get products enabled for bike builder.
    Can filter by:
    - builder_category: frame, wheels, drivetrain, brakes, handlebars, saddle
    - compatibility_tag_ids: comma-separated list of compatibility tag IDs to match
    - use_case: filter by use case value (city, trail, casual)
    - budget: filter by budget value (budget, mid, premium)
    """
    products = (
        ProductListing.objects.filter(bike_builder_enabled=True, available=True)
        .prefetch_related(
            "products",
            "products__brand",
            "compatibility_tags",
            "images",
        )
        .select_related("category")
    )

    # Filter by builder category
    builder_category = request.GET.get("builder_category")
    if builder_category:
        products = products.filter(builder_category=builder_category)

    # Filter by use case
    use_case = request.GET.get("use_case")
    if use_case:
        products = products.filter(
            compatibility_tags__tag_type="use_case",
            compatibility_tags__value=use_case
        ).distinct()
    
    # Filter by budget
    budget = request.GET.get("budget")
    if budget:
        products = products.filter(
            compatibility_tags__tag_type="budget",
            compatibility_tags__value=budget
        ).distinct()

    # Filter by compatibility tags - products that have ANY of the specified tags
    compatibility_tag_ids = request.GET.get("compatibility_tag_ids")
    if compatibility_tag_ids:
        try:
            # Parse comma-separated IDs
            ids = [int(id.strip()) for id in compatibility_tag_ids.split(",") if id.strip()]
            if ids:
                # Find products that have ANY of the specified compatibility tags
                products = products.filter(compatibility_tags__id__in=ids).distinct()
        except ValueError:
            return Response(
                {"error": "Invalid compatibility_tag_ids format"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Order by priority (higher first), then by name
    products = products.order_by("-builder_priority", "name")

    serializer = ProductListingSerializer(products, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
def get_compatible_products(request, listing_id):
    """
    Get products compatible with a specific listing.
    This checks what products can work together with the given product.
    """
    try:
        listing = ProductListing.objects.get(id=listing_id)

        # Get products that are compatible
        compatible_products = listing.find_compatible_products()

        serializer = ProductListingSerializer(compatible_products, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except ProductListing.DoesNotExist:
        return Response(
            {"error": "Product listing not found"}, status=status.HTTP_404_NOT_FOUND
        )
