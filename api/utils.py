"""
Utility functions for the API app.
"""
from datetime import timedelta
from typing import Any, Mapping, Optional

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

import logging

logger = logging.getLogger(__name__)


def _get_client_ip(request) -> Optional[str]:
    if not request:
        return None

    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def create_audit_log(
    *,
    actor=None,
    action: str,
    module: str = "",
    description: str = "",
    severity: str = "info",
    metadata: Optional[Mapping[str, Any]] = None,
    target_object=None,
    target_object_id: Optional[str] = None,
    target_object_repr: Optional[str] = None,
    request=None,
    user_agent: Optional[str] = None,
):
    """Persist an audit log entry. Failures are swallowed but logged."""

    if not action:
        raise ValueError("Audit log action is required")

    try:
        from .models import AuditLog

        # Resolve target metadata
        resolved_target_id = target_object_id
        resolved_target_repr = target_object_repr

        if target_object is not None:
            resolved_target_id = getattr(target_object, "pk", None) or resolved_target_id
            resolved_target_repr = str(target_object)

        # Ensure metadata is JSON-serialisable
        safe_metadata: Mapping[str, Any]
        if metadata is None:
            safe_metadata = {}
        elif isinstance(metadata, Mapping):
            try:
                # Convert values that are not JSON serialisable to strings
                safe_metadata = {
                    key: (value if isinstance(value, (str, int, float, bool, type(None), list, dict)) else str(value))
                    for key, value in metadata.items()
                }
            except Exception:  # pragma: no cover - fallback safety
                safe_metadata = {"data": str(metadata)}
        else:
            safe_metadata = {"data": str(metadata)}

        AuditLog.objects.create(
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            action=action,
            module=module,
            description=description,
            severity=severity,
            metadata=safe_metadata,
            target_object_id=str(resolved_target_id) if resolved_target_id is not None else None,
            target_object_repr=resolved_target_repr or "",
            ip_address=_get_client_ip(request),
            user_agent=user_agent or (request.META.get("HTTP_USER_AGENT") if request else ""),
        )
    except Exception as exc:  # pragma: no cover - logging should not break flow
        logger.warning("Failed to write audit log for action '%s': %s", action, exc)


def send_reservation_notification(reservation, notification_type):
    """
    Send notification to user about their reservation status.
    notification_type: 'activated', 'expired', 'moved_up'
    """
    # TODO: Implement email/push notification system
    # For now, we'll just log it
    messages = {
        'activated': f"Your reservation for {reservation.product.name} is now active! You have 3 days to complete your purchase.",
        'expired': f"Your reservation for {reservation.product.name} has expired. The product has been assigned to the next person in queue.",
        'moved_up': f"Good news! You moved up in the reservation queue for {reservation.product.name}. You are now #{reservation.queue_position}.",
    }
    
    message = messages.get(notification_type, '')
    print(f"NOTIFICATION to {reservation.user.email}: {message}")
    
    # Here you would integrate with:
    # - Email service (Django's send_mail)
    # - Push notification service
    # - In-app notification system
    # - SMS service


def process_product_reservations(product):
    """
    Process reservations for a product when it's restocked.
    Activates the first waiting reservation and updates queue positions.
    """
    from .models import ReservedProduct
    
    # Get all active and waiting reservations for this product
    reservations = ReservedProduct.objects.filter(
        product=product,
        status__in=['waiting', 'active']
    ).order_by('queue_position')
    
    # Check for expired active reservations
    for reservation in reservations.filter(status='active'):
        if reservation.is_expired():
            reservation.status = 'expired'
            reservation.save()
            send_reservation_notification(reservation, 'expired')
    
    # Refresh the queryset after expiring old ones
    reservations = ReservedProduct.objects.filter(
        product=product,
        status__in=['waiting', 'active']
    ).order_by('queue_position')
    
    # If product is in stock and there are waiting reservations
    if product.stock > 0:
        # Check if there's already an active reservation
        active_reservation = reservations.filter(status='active').first()
        
        if not active_reservation:
            # Activate the first waiting reservation
            first_waiting = reservations.filter(status='waiting').first()
            if first_waiting:
                first_waiting.activate_reservation()
                send_reservation_notification(first_waiting, 'activated')
                print(f"Activated reservation for {first_waiting.user.username} - Product: {product.name}")
    
    # Update queue positions for all waiting reservations
    waiting_reservations = reservations.filter(status='waiting').order_by('created_at')
    for idx, reservation in enumerate(waiting_reservations, start=1):
        # Skip active reservations in position counting
        active_count = reservations.filter(status='active').count()
        old_position = reservation.queue_position
        reservation.queue_position = active_count + idx
        reservation.save(update_fields=['queue_position'])
        
        # Notify if position changed (moved up)
        if old_position > reservation.queue_position:
            send_reservation_notification(reservation, 'moved_up')


def process_expired_reservations():
    """
    Process all expired reservations across all products.
    Called by a scheduled task (cron job or management command).
    """
    from .models import ReservedProduct, Product
    
    # Find all active reservations that have expired
    expired_reservations = ReservedProduct.objects.filter(
        status='active',
        expires_at__lt=timezone.now()
    )
    
    # Group by product
    products_to_reprocess = set()
    
    for reservation in expired_reservations:
        reservation.status = 'expired'
        reservation.save()
        products_to_reprocess.add(reservation.product)
        print(f"Expired reservation for {reservation.user.username} - Product: {reservation.product.name}")
    
    # Reprocess each affected product
    for product in products_to_reprocess:
        process_product_reservations(product)


def check_reservation_access(product, user):
    """
    Check if a user can purchase a product based on reservation status.
    Returns (can_purchase: bool, reason: str)
    """
    from .models import ReservedProduct
    
    if not user or not user.is_authenticated:
        # Check if product has active reservations
        has_active = ReservedProduct.objects.filter(
            product=product,
            status='active'
        ).exists()
        
        if has_active:
            return False, "This product is currently reserved for another customer"
        return True, ""
    
    # Get user's reservation if any
    user_reservation = ReservedProduct.objects.filter(
        product=product,
        user=user,
        status__in=['waiting', 'active']
    ).first()
    
    # Check for other users' active reservations
    other_active = ReservedProduct.objects.filter(
        product=product,
        status='active'
    ).exclude(user=user).exists()
    
    if other_active:
        if user_reservation and user_reservation.status == 'waiting':
            return False, f"This product is reserved. You are #{user_reservation.queue_position} in queue."
        return False, "This product is currently reserved for another customer"
    
    # No active reservations from others
    if user_reservation and user_reservation.status == 'active':
        # User has active reservation
        return True, ""
    
    # Product is available (no active reservations)
    return True, ""


def send_order_completion_email(order):
    """
    Send email notification when an order is completed.
    Only sends if user has email_order_updates enabled.
    """
    try:
        from .models import UserProfile
        
        # Get user profile and check preference
        try:
            user_profile = UserProfile.objects.get(user=order.user)
            if not user_profile.email_order_updates:
                logger.info(f"Order completion email skipped for user {order.user.username} (preference disabled)")
                return
        except UserProfile.DoesNotExist:
            # Default to True if profile doesn't exist
            pass
        
        # Build email content
        subject = f"Order #{order.id} Completed - PedalPoint"
        
        items_list = "\n".join([
            f"- {item.product.name} ({item.product.variant_attribute or 'N/A'}) x {item.quantity}"
            for item in order.items.select_related('product').all()
        ])
        
        sale = getattr(order, "sale", None)
        payment_method_display = (
            sale.get_payment_method_display() if sale else "N/A"
        )

        message = f"""Hello {order.user.get_full_name() or order.user.username},

Your order #{order.id} has been completed!

Order Details:
{items_list}

Order Date: {order.created_at.strftime('%B %d, %Y at %I:%M %p')}
Status: {order.get_status_display()}
Payment Method: {payment_method_display}

Thank you for shopping with PedalPoint!

Best regards,
PedalPoint Team
"""
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.user.email],
            fail_silently=False,
        )
        logger.info(f"Order completion email sent to {order.user.email} for order #{order.id}")
    except Exception as e:
        logger.error(f"Failed to send order completion email for order #{order.id}: {str(e)}")


def send_out_of_stock_alert(product):
    """
    Notify inventory team when a product's stock reaches zero.
    Sends a simple email containing product details.
    """
    try:
        recipients = getattr(settings, "INVENTORY_ALERT_RECIPIENTS", None)
        if not recipients:
            logger.info(
                "Out-of-stock alert skipped for product %s (no recipients configured)",
                product.id,
            )
            return

        if isinstance(recipients, str):
            recipients = [recipients]

        subject = f"[Inventory Alert] {product.name} is out of stock"
        message_lines = [
            "Hello PedalPoint team,",
            "",
            "The following product has just gone out of stock:",
            f"- Product ID: {product.id}",
            f"- Name: {product.name or 'N/A'}",
            f"- Variant: {product.variant_attribute or 'N/A'}",
            f"- SKU: {product.sku or 'N/A'}",
            f"- Remaining Stock: {product.stock}",
        ]

        if product.brand:
            message_lines.append(f"- Brand: {product.brand.name}")
        if product.product_listing:
            message_lines.append(
                f"- Listing: {product.product_listing.name or product.product_listing.id}"
            )

        message_lines.extend(
            [
                "",
                "Consider reordering or updating availability as needed.",
                "",
                "This is an automated notification.",
            ]
        )

        send_mail(
            subject=subject,
            message="\n".join(message_lines),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=list(recipients),
            fail_silently=False,
        )
        logger.info("Out-of-stock alert sent for product %s", product.id)
    except Exception as exc:
        logger.error(
            "Failed to send out-of-stock alert for product %s: %s",
            product.id,
            exc,
        )


def send_reservation_fulfillment_email(reservation):
    """
    Send email notification when a reservation is fulfilled (purchased).
    Only sends if user has email_reservation_updates enabled.
    """
    try:
        from .models import UserProfile
        
        # Get user profile and check preference
        try:
            user_profile = UserProfile.objects.get(user=reservation.user)
            if not user_profile.email_reservation_updates:
                logger.info(f"Reservation fulfillment email skipped for user {reservation.user.username} (preference disabled)")
                return
        except UserProfile.DoesNotExist:
            # Default to True if profile doesn't exist
            pass
        
        # Build email content
        subject = f"Reservation Fulfilled - {reservation.product.name} - PedalPoint"
        
        message = f"""Hello {reservation.user.get_full_name() or reservation.user.username},

Great news! Your reservation for {reservation.product.name} {reservation.product.variant_attribute or ''} has been fulfilled.

Product Details:
- Product: {reservation.product.name}
- Variant: {reservation.product.variant_attribute or 'N/A'}
- Brand: {reservation.product.brand.name if reservation.product.brand else 'N/A'}
- Price: ₱{reservation.product.price:,.2f}

Reservation Details:
- Reserved: {reservation.created_at.strftime('%B %d, %Y')}
- Fulfilled: {reservation.fulfilled_at.strftime('%B %d, %Y at %I:%M %p') if reservation.fulfilled_at else 'N/A'}

Thank you for your patience!

Best regards,
PedalPoint Team
"""
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[reservation.user.email],
            fail_silently=False,
        )
        logger.info(f"Reservation fulfillment email sent to {reservation.user.email} for reservation #{reservation.id}")
    except Exception as e:
        logger.error(f"Failed to send reservation fulfillment email for reservation #{reservation.id}: {str(e)}")


def send_service_completion_email(service_queue):
    """
    Send email notification when a service appointment is completed.
    Only sends if user has email_service_updates enabled.
    """
    try:
        from .models import UserProfile
        
        if not service_queue.user:
            logger.warning(f"Service completion email skipped - no user assigned to service #{service_queue.id}")
            return
        
        # Get user profile and check preference
        try:
            user_profile = UserProfile.objects.get(user=service_queue.user)
            if not user_profile.email_service_updates:
                logger.info(f"Service completion email skipped for user {service_queue.user.username} (preference disabled)")
                return
        except UserProfile.DoesNotExist:
            # Default to True if profile doesn't exist
            pass
        
        # Build email content
        subject = f"Service Appointment Completed - PedalPoint"
        
        message = f"""Hello {service_queue.user.get_full_name() or service_queue.user.username},

Your service appointment has been completed!

Service Details:
- Service Date: {service_queue.queue_date.strftime('%B %d, %Y')}
- Service Info: {service_queue.info}
- Status: {service_queue.get_status_display()}

Thank you for choosing PedalPoint for your bike service needs!

Best regards,
PedalPoint Team
"""
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[service_queue.user.email],
            fail_silently=False,
        )
        logger.info(f"Service completion email sent to {service_queue.user.email} for service #{service_queue.id}")
    except Exception as e:
        logger.error(f"Failed to send service completion email for service #{service_queue.id}: {str(e)}")

