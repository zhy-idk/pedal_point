from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import Product


@receiver(post_save, sender=Product)
def update_product_price_on_save(sender, instance, **kwargs):
    if instance.product_listing:
        instance.product_listing.update_price_from_variants()


@receiver(post_delete, sender=Product)
def update_product_price_on_delete(sender, instance, **kwargs):
    if instance.product_listing:
        instance.product_listing.update_price_from_variants()
