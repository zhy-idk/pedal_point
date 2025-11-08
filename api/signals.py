from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.contrib.auth.models import User
from allauth.account.signals import email_confirmed
from .models import Product
from .serializer import ProductSerializer
from .realtime_utils import send_inventory_update
from .utils import send_out_of_stock_alert


@receiver(post_save, sender=Product)
def update_product_price_on_save(sender, instance, **kwargs):
    try:
        if instance.product_listing:
            instance.product_listing.update_price_from_variants()
    except Exception:
        # Product listing might be deleted or doesn't exist
        pass


@receiver(post_delete, sender=Product)
def update_product_price_on_delete(sender, instance, **kwargs):
    try:
        if instance.product_listing:
            instance.product_listing.update_price_from_variants()
    except Exception:
        # Product listing might be deleted or doesn't exist
        pass


@receiver(post_save, sender=Product)
def send_inventory_update_on_save(sender, instance, created, **kwargs):
    """Send real-time inventory update when Product is saved (created or updated)."""
    print(f"DEBUG: Product {instance.id} saved (created={created}), sending WebSocket update")
    
    try:
        serializer = ProductSerializer(instance)
        send_inventory_update(serializer.data)
        print(f"DEBUG: WebSocket update sent for product {instance.id}")
    except Exception as e:
        print(f"ERROR: Failed to send WebSocket update for product {instance.id}: {e}")


@receiver(pre_save, sender=Product)
def send_out_of_stock_email(sender, instance, **kwargs):
    """
    Trigger an alert email when product stock transitions from a positive value to zero or below.
    """
    if not instance.pk:
        return

    try:
        previous = Product.objects.get(pk=instance.pk)
    except Product.DoesNotExist:
        return

    previous_stock = previous.stock if previous.stock is not None else 0
    new_stock = instance.stock if instance.stock is not None else 0

    if previous_stock > 0 and new_stock <= 0:
        send_out_of_stock_alert(instance)


@receiver(post_delete, sender=Product)
def send_inventory_update_on_delete(sender, instance, **kwargs):
    """Send real-time inventory update when Product is deleted."""
    print(f"DEBUG: Product {instance.id} deleted, sending WebSocket update")
    
    try:
        # Send deletion notification
        send_inventory_update({
            'action': 'deleted',
            'product_id': instance.id,
            'data': {
                'id': instance.id,
                'name': instance.name,
                'variant_attribute': instance.variant_attribute,
                'brand': str(instance.brand) if instance.brand else '',
                'price': float(instance.price),
                'stock': instance.stock,
                'sku': instance.sku,
                'available': instance.available
            }
        })
        print(f"DEBUG: WebSocket deletion update sent for product {instance.id}")
    except Exception as e:
        print(f"ERROR: Failed to send WebSocket deletion update for product {instance.id}: {e}")


@receiver(email_confirmed)
def send_welcome_email(sender, request, email_address, **kwargs):
    """Send welcome email after email confirmation."""
    try:
        user = email_address.user
        site_url = getattr(settings, 'SITE_URL', 'http://localhost:3000')
        
        # Render the welcome email template
        subject = 'Welcome to Pedal Point - Your Account is Ready!'
        message = render_to_string('account/email/welcome_message.txt', {
            'user_display': user.get_full_name() or user.username,
            'user': user,
            'site_url': site_url,
        })
        
        # Send the email
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.EMAIL_HOST_USER,
            recipient_list=[user.email],
            fail_silently=False,
        )
        
        print(f"Welcome email sent to {user.email}")
        
    except Exception as e:
        print(f"ERROR: Failed to send welcome email to {email_address.email}: {e}")
