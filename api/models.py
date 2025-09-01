from django.db import models
from django.urls import reverse

from autoslug import AutoSlugField
from tinymce.models import HTMLField

import os


def upload_to_listing_folder(instance, filename):
    return os.path.join("products", str(instance.id), filename)


def upload_to_product_folder(instance, filename):
    return os.path.join("products", str(instance.product.id), filename)


class Brands(models.Model):
    name = models.CharField(max_length=255)
    slug = AutoSlugField(populate_from="name", unique=True, verbose_name="Slug")

    class Meta:
        ordering = ["name"]
        verbose_name = "Brand"
        verbose_name_plural = "Brands"

    def __str__(self):
        return self.name


class CompatibilityGroup(models.Model):
    """Groups for organizing compatibility attributes (e.g., 'Frame', 'Wheels', 'Drivetrain')"""

    name = models.CharField(max_length=255, verbose_name="Group Name")
    slug = AutoSlugField(populate_from="name", unique=True, verbose_name="Slug")
    description = models.TextField(blank=True, null=True, verbose_name="Description")

    class Meta:
        ordering = ["name"]
        verbose_name = "Compatibility Group"
        verbose_name_plural = "Compatibility Groups"

    def __str__(self):
        return self.name


class CompatibilityAttribute(models.Model):
    """Individual attributes within a group (e.g., 'Material', 'Size', 'Suspension Type')"""

    name = models.CharField(max_length=255, verbose_name="Attribute Name")
    group = models.ForeignKey(
        CompatibilityGroup,
        on_delete=models.CASCADE,
        related_name="attributes",
        verbose_name="Compatibility Group",
    )
    attribute_type = models.CharField(
        max_length=50,
        choices=[
            ("text", "Text"),
            ("number", "Number"),
            ("boolean", "Yes/No"),
            ("choice", "Multiple Choice"),
        ],
        default="text",
        verbose_name="Attribute Type",
    )
    is_required = models.BooleanField(default=False, verbose_name="Required")

    class Meta:
        ordering = ["group__name", "name"]
        verbose_name = "Compatibility Attribute"
        verbose_name_plural = "Compatibility Attributes"
        unique_together = [
            "group",
            "name",
        ]  # Prevent duplicate attributes in same group

    def __str__(self):
        return f"{self.group.name} - {self.name}"


class CompatibilityAttributeValue(models.Model):
    """Predefined values for attributes that can be selected for compatibility"""

    attribute = models.ForeignKey(
        CompatibilityAttribute,
        on_delete=models.CASCADE,
        related_name="values",
        verbose_name="Attribute",
    )
    value = models.CharField(max_length=255, verbose_name="Value")
    display_name = models.CharField(max_length=255, verbose_name="Display Name")
    description = models.TextField(blank=True, null=True, verbose_name="Description")

    class Meta:
        ordering = ["attribute", "display_name"]
        verbose_name = "Compatibility Attribute Value"
        verbose_name_plural = "Compatibility Attribute Values"
        unique_together = ["attribute", "value"]

    def __str__(self):
        return f"{self.attribute} - {self.display_name}"


class ProductListing(models.Model):
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        blank=True,
        null=True,
        verbose_name="Lowest Variant Price",
    )
    category = models.ForeignKey(
        "ProductCategory", on_delete=models.SET_NULL, null=True, verbose_name="Category"
    )
    description = HTMLField(verbose_name="Product Description", blank=True, null=True)
    image = models.ImageField(
        upload_to=upload_to_listing_folder,
        blank=True,
        null=True,
        verbose_name="Product Card Image",
    )
    slug = AutoSlugField(populate_from="name", unique=True)
    available = models.BooleanField(default=True, verbose_name="Available")

    # Direct compatibility attributes - what this product IS
    compatibility_attributes = models.ManyToManyField(
        CompatibilityAttributeValue,
        blank=True,
        related_name="products_with_attribute",
        verbose_name="Product Attributes",
        help_text="What attributes this product HAS (e.g., this frame IS Carbon, Large)",
    )

    # Compatible with attributes - what this product works WITH
    compatible_with = models.ManyToManyField(
        CompatibilityAttributeValue,
        blank=True,
        related_name="compatible_products",
        verbose_name="Compatible With",
        help_text="What attributes this product is COMPATIBLE with (e.g., this component works with Carbon frames)",
    )

    def update_price_from_variants(self):
        lowest_price = self.products.filter(available=True).order_by("price").first()
        self.price = lowest_price.price if lowest_price else 0
        self.save(update_fields=["price"])

    def update_brand_from_products(self):
        first_variant_with_brand = self.products.filter(brand__isnull=False).first()
        if first_variant_with_brand:
            self._brand = first_variant_with_brand.brand  # internal use
        else:
            self._brand = None

    def get_name_from_products(self):
        if not self.pk:  # instance not saved yet
            return None
        product_name = self.products.filter(name__isnull=False).first()
        return product_name.name if product_name else None

    @property
    def brand(self):
        self.update_brand_from_products()
        return self._brand

    @property
    def name(self):
        if not hasattr(self, "_name"):  # safe check
            self._name = self.get_name_from_products()
        return self._name

    def get_attributes_by_group(self):
        """Returns product attributes organized by group"""
        attributes = self.compatibility_attributes.select_related(
            "attribute", "attribute__group"
        ).all()

        grouped = {}
        for attr_value in attributes:
            group_name = attr_value.attribute.group.name
            if group_name not in grouped:
                grouped[group_name] = []
            grouped[group_name].append(attr_value)

        return grouped

    def get_compatibility_by_group(self):
        """Returns compatibility requirements organized by group"""
        compatible = self.compatible_with.select_related(
            "attribute", "attribute__group"
        ).all()

        grouped = {}
        for attr_value in compatible:
            group_name = attr_value.attribute.group.name
            if group_name not in grouped:
                grouped[group_name] = []
            grouped[group_name].append(attr_value)

        return grouped

    def find_compatible_products(self):
        """Find products that are compatible with this product's attributes"""
        if not self.compatibility_attributes.exists():
            return ProductListing.objects.none()

        # Find products whose 'compatible_with' includes any of this product's attributes
        return (
            ProductListing.objects.filter(
                compatible_with__in=self.compatibility_attributes.all()
            )
            .exclude(id=self.id)
            .distinct()
        )

    def find_products_this_is_compatible_with(self):
        """Find products this product is compatible with"""
        if not self.compatible_with.exists():
            return ProductListing.objects.none()

        # Find products that have the attributes this product is compatible with
        return (
            ProductListing.objects.filter(
                compatibility_attributes__in=self.compatible_with.all()
            )
            .exclude(id=self.id)
            .distinct()
        )

    def is_compatible_with(self, other_product):
        """Check if this product is compatible with another product"""
        # Check if this product's compatible_with matches other product's attributes
        my_compatibility = set(self.compatible_with.all())
        other_attributes = set(other_product.compatibility_attributes.all())

        # Check if other product's compatible_with matches this product's attributes
        other_compatibility = set(other_product.compatible_with.all())
        my_attributes = set(self.compatibility_attributes.all())

        # Compatible if either direction has a match
        return bool(my_compatibility & other_attributes) or bool(
            other_compatibility & my_attributes
        )

    class Meta:
        verbose_name = "Product Listing"
        verbose_name_plural = "Product Listings"

    def __str__(self):
        return self.name or f"Product Listing {self.id}"


class Product(models.Model):
    product_listing = models.ForeignKey(
        ProductListing,
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name="Product Listing",
        null=True,
        blank=True,
    )
    name = models.CharField(
        max_length=255, verbose_name="Variant Name", blank=True, null=True
    )
    variant_attribute = models.CharField(
        verbose_name="Color",
        blank=True,
        null=True,
        default="None",
    )
    brand = models.ForeignKey(
        Brands,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Brand",
    )
    sku = models.CharField(blank=True, null=True, verbose_name="SKU")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Price")
    stock = models.IntegerField(default=0, verbose_name="Stock Quantity")
    available = models.BooleanField(default=True, verbose_name="Available")

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"

    def __str__(self):
        return f"{self.name} QTY:{self.stock}"


class ProductImage(models.Model):
    product_listing = models.ForeignKey(
        ProductListing, related_name="images", on_delete=models.CASCADE
    )
    image = models.ImageField(upload_to=upload_to_product_folder)
    alt_text = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Product Listing Image"
        verbose_name_plural = "Product Listing Images"

    def __str__(self):
        return f"Image for {self.product_listing.name}"


class ProductVariantImage(models.Model):
    product = models.ForeignKey(
        Product,
        related_name="product_images",
        on_delete=models.CASCADE,
        null=True,
    )
    listing = models.ForeignKey(
        ProductListing,
        related_name="variant_images",
        on_delete=models.CASCADE,
        null=True,
    )
    image = models.ImageField(upload_to=upload_to_product_folder)
    alt_text = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "Product Variant Image"
        verbose_name_plural = "Product Variant Images"

    def __str__(self):
        return f"Image for {self.product.name}"


class ProductCategory(models.Model):
    name = models.CharField(max_length=255, verbose_name="Category Name")
    slug = AutoSlugField(populate_from="name", unique=True)

    class Meta:
        verbose_name = "Product Category"
        verbose_name_plural = "Product Categories"

    def __str__(self):
        return self.name


class ProductReview(models.Model):
    product_listing = models.ForeignKey(
        ProductListing, related_name="reviews", on_delete=models.CASCADE
    )
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, verbose_name="User")
    review = HTMLField(verbose_name="Product Review", blank=True, null=True)
    star_choices = {
        1: "1 star",
        2: "2 star",
        3: "3 star",
        4: "4 star",
        5: "5 star",
    }
    star = models.IntegerField(choices=star_choices)
    date = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        verbose_name = "Review"
        verbose_name_plural = "Reviews"

    def __str__(self):
        return f"{self.user.username}'s Review: {self.star}"


class Cart(models.Model):
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, verbose_name="User")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        verbose_name = "Cart"
        verbose_name_plural = "Carts"

    def __str__(self):
        return f"{self.user.username}'s Cart"


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name="items", verbose_name="Cart"
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        verbose_name="Product",
        blank=True,
        null=True,
    )
    quantity = models.IntegerField(default=1, verbose_name="Quantity")

    class Meta:
        verbose_name = "Cart Item"
        verbose_name_plural = "Cart Items"

    def __str__(self):
        return f"{self.cart.user.username}'s item: "


class Order(models.Model):
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, verbose_name="User")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Order Date")
    status = models.CharField(
        max_length=50,
        choices=[
            ("pending", "Pending"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
            ("returned", "Returned"),
        ],
        default="pending",
        verbose_name="Order Status",
    )

    class Meta:
        verbose_name = "Order"
        verbose_name_plural = "Orders"

    def __str__(self):
        return f"Order {self.id} by {self.user.username}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="items", verbose_name="Order"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, verbose_name="Item", null=True
    )
    quantity = models.IntegerField(default=1, verbose_name="Quantity")

    class Meta:
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"

    def __str__(self):
        return f"Order Item {self.id} for Order {self.order.id}"


class OrderHistory(models.Model):
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, verbose_name="User")
    order = models.ForeignKey(Order, on_delete=models.CASCADE, verbose_name="Order")
    action = models.CharField(
        max_length=50,
        choices=[
            ("created", "Created"),
            ("updated", "Updated"),
            ("deleted", "Deleted"),
        ],
        verbose_name="Action",
    )
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Timestamp")

    class Meta:
        verbose_name = "Order History"
        verbose_name_plural = "Order Histories"

    def __str__(self):
        return f"{self.user.username} - {self.action} - {self.order.id}"


class Sales(models.Model):
    product_listing = models.ForeignKey(
        ProductListing, on_delete=models.CASCADE, verbose_name="Product Listing"
    )
    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, verbose_name="User", null=True
    )
    quantity_sold = models.IntegerField(verbose_name="Quantity Sold")
    sale_date = models.DateTimeField(auto_now_add=True, verbose_name="Sale Date")

    class Meta:
        verbose_name = "Sale"
        verbose_name_plural = "Sales"

    def __str__(self):
        return f"{self.product_listing.name} - {self.quantity_sold} sold on {self.sale_date}"


class ServiceQueue(models.Model):
    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, verbose_name="User", null=True
    )
    queue_date = models.DateField(verbose_name="Queue Date")
    info = models.CharField(verbose_name="Queue info")
    status = models.CharField(
        max_length=50,
        choices=[
            ("pending", "Pending"),
            ("completed", "Completed"),
        ],
        default="pending",
        verbose_name="Queue Status",
    )

    def __str__(self):
        return f"Service for {self.user} on {self.queue_date}"
