from django.db import models
from django.urls import reverse

from autoslug import AutoSlugField
from tinymce.models import HTMLField

import os


def upload_to_listing_folder(instance, filename):
    """
    Generate upload path for ProductListing thumbnail.
    If instance doesn't have an ID yet (new instance), use a temporary path
    that will be corrected after save.
    """
    if instance.id:
        path = os.path.join("products", str(instance.id), filename)
    else:
        # For new instances, use a temporary path
        # Django will handle this correctly when the instance is saved
        path = os.path.join("products", "temp", filename)
    print(f"DEBUG upload_to_listing_folder: instance.id={instance.id}, filename={filename}, path={path}")
    return path


def upload_to_product_folder(instance, filename):
    # Handle both ProductImage (has product_listing) and ProductVariantImage (has product)
    if hasattr(instance, 'product_listing'):
        return os.path.join("products", str(instance.product_listing.id), filename)
    elif hasattr(instance, 'product'):
        return os.path.join("products", str(instance.product.id), filename)
    else:
        # Fallback for other cases
        return os.path.join("products", filename)


def upload_to_user_folder(instance, filename):
    return os.path.join("users", str(instance.user.id), filename)


class UserProfile(models.Model):
    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="user_info"
    )
    address = models.CharField()
    contact_number = models.CharField()
    image = models.ImageField(
        upload_to=upload_to_user_folder,
        blank=True,
        null=True,
        verbose_name="User Profile Image",
    )
    # Email notification preferences
    email_order_updates = models.BooleanField(
        default=True,
        verbose_name="Order Update Notifications",
        help_text="Receive emails when your orders are completed"
    )
    email_reservation_updates = models.BooleanField(
        default=True,
        verbose_name="Reservation Update Notifications",
        help_text="Receive emails when your reservations are fulfilled"
    )
    email_service_updates = models.BooleanField(
        default=True,
        verbose_name="Service Update Notifications",
        help_text="Receive emails when your service appointments are completed"
    )

    def __str__(self):
        return f"{self.user.username}'s Profile {self.user.date_joined} {self.user.first_name} {self.user.last_name} {self.user.email}"


class StaffPermissions(models.Model):
    """Staff member access permissions for different modules"""

    user = models.OneToOneField(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="staff_permissions",
        limit_choices_to={"is_staff": True},
    )

    # Module permissions
    can_access_pos = models.BooleanField(default=True, verbose_name="POS Access")
    can_access_chats = models.BooleanField(default=True, verbose_name="Chat Access")
    can_access_orders = models.BooleanField(default=True, verbose_name="Orders Access")
    can_access_listings = models.BooleanField(
        default=True, verbose_name="Listings Access"
    )
    can_access_inventory = models.BooleanField(
        default=True, verbose_name="Inventory Access"
    )
    can_access_queueing = models.BooleanField(
        default=True, verbose_name="Service Queue Access"
    )
    can_access_reservations = models.BooleanField(
        default=True, verbose_name="Reservations Access"
    )
    can_access_suppliers = models.BooleanField(
        default=True, verbose_name="Suppliers Access"
    )

    # Superuser-only (these are always False for regular staff)
    # Sales and User Management are controlled by is_superuser flag

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Staff Permission"
        verbose_name_plural = "Staff Permissions"

    def __str__(self):
        return f"Permissions for {self.user.username}"


class Brands(models.Model):
    name = models.CharField(max_length=255)
    slug = AutoSlugField(populate_from="name", unique=True, verbose_name="Slug")

    class Meta:
        ordering = ["name"]
        verbose_name = "Brand"
        verbose_name_plural = "Brands"

    def __str__(self):
        return self.name


class BikeCompatibilityTag(models.Model):
    """
    Simplified compatibility tags for bike builder.
    Tags can be: Use Case (city/trail/casual), Budget (budget/mid/premium), 
    or Physical specs (wheel size, brake type, etc.)
    """
    
    TAG_TYPES = [
        ("use_case", "Use Case"),
        ("budget", "Budget Range"),
        ("physical", "Physical Compatibility"),
    ]
    
    tag_type = models.CharField(
        max_length=20,
        choices=TAG_TYPES,
        verbose_name="Tag Type",
        help_text="Type of compatibility tag"
    )
    value = models.CharField(
        max_length=100,
        verbose_name="Value",
        help_text="Internal value (e.g., 'city', 'budget', 'disc_brake')"
    )
    display_name = models.CharField(
        max_length=255,
        verbose_name="Display Name",
        help_text="User-friendly name (e.g., 'City Commuting', 'Budget ₱15k-24k')"
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Description",
        help_text="Optional description for this tag"
    )
    display_order = models.IntegerField(
        default=0,
        verbose_name="Display Order",
        help_text="Order to display (higher = shows first)"
    )
    
    class Meta:
        ordering = ["tag_type", "-display_order", "display_name"]
        verbose_name = "Bike Compatibility Tag"
        verbose_name_plural = "Bike Compatibility Tags"
        unique_together = ["tag_type", "value"]
    
    def __str__(self):
        return f"[{self.get_tag_type_display()}] {self.display_name}"


# OLD Compatibility Models (Deprecated - kept for backward compatibility)
# These will be removed in a future version
class CompatibilityGroup(models.Model):
    """DEPRECATED: Use BikeCompatibilityTag instead"""
    name = models.CharField(max_length=255, verbose_name="Group Name")
    slug = AutoSlugField(populate_from="name", unique=True, verbose_name="Slug")
    description = models.TextField(blank=True, null=True, verbose_name="Description")

    class Meta:
        ordering = ["name"]
        verbose_name = "Compatibility Group (Deprecated)"
        verbose_name_plural = "Compatibility Groups (Deprecated)"

    def __str__(self):
        return self.name


class CompatibilityAttribute(models.Model):
    """DEPRECATED: Use BikeCompatibilityTag instead"""
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
        verbose_name = "Compatibility Attribute (Deprecated)"
        verbose_name_plural = "Compatibility Attributes (Deprecated)"
        unique_together = ["group", "name"]

    def __str__(self):
        return f"{self.group.name} - {self.name}"


class CompatibilityAttributeValue(models.Model):
    """DEPRECATED: Use BikeCompatibilityTag instead"""
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
        verbose_name = "Compatibility Attribute Value (Deprecated)"
        verbose_name_plural = "Compatibility Attribute Values (Deprecated)"
        unique_together = ["attribute", "value"]

    def __str__(self):
        return f"{self.attribute} - {self.display_name}"


class ProductListing(models.Model):
    name = models.CharField(
        max_length=255,
        verbose_name="Product Name",
        blank=True,
        null=True,
    )
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

    # Bike Builder Fields
    bike_builder_enabled = models.BooleanField(
        default=False,
        verbose_name="Enable in Bike Builder",
        help_text="Make this product available in the bike builder wizard",
    )
    builder_category = models.CharField(
        max_length=50,
        choices=[
            ("frame", "Frame"),
            ("wheels", "Wheels"),
            ("drivetrain", "Drivetrain"),
            ("brakes", "Brakes"),
            ("handlebars", "Handlebars"),
            ("saddle", "Saddle"),
        ],
        blank=True,
        null=True,
        verbose_name="Builder Category",
        help_text="Component type for bike builder (Frame, Wheels, etc.)",
    )
    builder_priority = models.IntegerField(
        default=0,
        verbose_name="Builder Priority",
        help_text="Display order in bike builder (higher = shows first)",
    )

    # Bike Builder Compatibility Tags (New System)
    compatibility_tags = models.ManyToManyField(
        BikeCompatibilityTag,
        blank=True,
        related_name="products",
        verbose_name="Compatibility Tags",
        help_text="Select use case, budget range, and physical compatibility tags for this product",
    )
    
    # OLD fields (Deprecated - kept for backward compatibility during migration)
    # These will be removed in a future version after all data is migrated
    compatibility_attributes = models.ManyToManyField(
        "CompatibilityAttributeValue",
        blank=True,
        related_name="products_with_attribute",
        verbose_name="Product Attributes (Deprecated)",
        help_text="DEPRECATED: Use compatibility_tags instead",
    )
    compatible_with = models.ManyToManyField(
        "CompatibilityAttributeValue",
        blank=True,
        related_name="compatible_products",
        verbose_name="Compatible With (Deprecated)",
        help_text="DEPRECATED: Use compatibility_tags instead",
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
        """Fallback method to get name from products if name field is not set"""
        if self.name:
            return self.name
        if not self.pk:  # instance not saved yet
            return None
        product_name = self.products.filter(name__isnull=False).first()
        return product_name.name if product_name else None

    @property
    def brand(self):
        self.update_brand_from_products()
        return self._brand

    def get_tags_by_type(self):
        """Returns compatibility tags organized by type"""
        tags = self.compatibility_tags.all()
        grouped = {
            "use_case": [],
            "budget": [],
            "physical": []
        }
        
        for tag in tags:
            if tag.tag_type in grouped:
                grouped[tag.tag_type].append(tag)

        return grouped

    def get_use_cases(self):
        """Get use case tags (city, trail, casual)"""
        return self.compatibility_tags.filter(tag_type="use_case")
    
    def get_budget_tiers(self):
        """Get budget tier tags (budget, mid, premium)"""
        return self.compatibility_tags.filter(tag_type="budget")

    def get_physical_specs(self):
        """Get physical compatibility tags (brake type, wheel size, etc.)"""
        return self.compatibility_tags.filter(tag_type="physical")

    def is_compatible_with_tags(self, tag_ids):
        """
        Check if product matches given compatibility tags.
        For bike builder: matches if product has ANY of the physical tags
        and has the selected use case and budget tags.
        """
        if not tag_ids:
            return True
        
        product_tag_ids = set(self.compatibility_tags.values_list('id', flat=True))
        required_tag_ids = set(tag_ids)

        # Product is compatible if it has the required tags
        return bool(product_tag_ids & required_tag_ids)

    class Meta:
        verbose_name = "Product Listing"
        verbose_name_plural = "Product Listings"

    def __str__(self):
        return (
            self.name or self.get_name_from_products() or f"Product Listing {self.id}"
        )


class ProductSupplier(models.Model):
    name = models.CharField(blank=True, null=True)
    contact = models.CharField(blank=True, null=True)

    def __str__(self):
        return f"{self.name}"


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
    supply = models.ForeignKey(
        ProductSupplier,
        related_name="supplier",
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="Supplier",
    )
    supplier_price = models.DecimalField(
        max_digits=10, decimal_places=2, verbose_name="Supplier Price", null=True
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
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subcategories",
        verbose_name="Parent Category",
        help_text="Leave blank for top-level categories",
    )
    is_component = models.BooleanField(
        default=False,
        verbose_name="Is Component Category",
        help_text="Check if this is a bike component category (frame, wheels, etc.)",
    )
    component_type = models.CharField(
        max_length=50,
        choices=[
            ("frame", "Frame"),
            ("fork", "Fork"),
            ("wheels", "Wheels"),
            ("drivetrain", "Drivetrain"),
            ("brakes", "Brakes"),
            ("handlebars", "Handlebars"),
            ("saddle", "Saddle"),
            ("pedals", "Pedals"),
            ("accessories", "Accessories"),
        ],
        blank=True,
        null=True,
        verbose_name="Component Type",
        help_text="Type of component (only for component categories)",
    )

    class Meta:
        verbose_name = "Product Category"
        verbose_name_plural = "Product Categories"
        ordering = ["name"]

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name

    def get_all_subcategories(self):
        """Get all subcategories recursively"""
        subcats = list(self.subcategories.all())
        for subcat in list(subcats):
            subcats.extend(subcat.get_all_subcategories())
        return subcats


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


class ReservedProduct(models.Model):
    """
    Reservation queue system for out-of-stock products.
    When product is restocked, it's reserved for the first user in queue for 3 days.
    """

    STATUS_CHOICES = [
        ("waiting", "Waiting in Queue"),
        ("active", "Active Reservation"),
        ("expired", "Expired"),
        ("fulfilled", "Fulfilled"),
        ("cancelled", "Cancelled"),
    ]

    product = models.ForeignKey(
        Product, related_name="reservations", on_delete=models.CASCADE
    )
    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="product_reservations"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="waiting",
        help_text="Current status of the reservation",
    )
    queue_position = models.IntegerField(
        default=0, help_text="Position in the reservation queue (1 = first)"
    )

    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        null=True,
        blank=True,
        help_text="When the reservation was created",
    )
    reserved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the reservation became active (product became available)",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the active reservation expires (3 days after reserved_at)",
    )
    fulfilled_at = models.DateTimeField(
        null=True, blank=True, help_text="When the user purchased the product"
    )
    cancelled_at = models.DateTimeField(
        null=True, blank=True, help_text="When the reservation was cancelled"
    )

    class Meta:
        ordering = ["product", "queue_position", "created_at"]
        unique_together = ["product", "user"]  # One reservation per user per product

    def __str__(self):
        return f"{self.user.username}'s reservation for {self.product.name} {self.product.variant_attribute} (Status: {self.status})"

    def activate_reservation(self):
        """Activate this reservation when product becomes available."""
        from django.utils import timezone
        from datetime import timedelta

        self.status = "active"
        self.reserved_at = timezone.now()
        self.expires_at = self.reserved_at + timedelta(days=3)
        self.save()

    def cancel_reservation(self):
        """Cancel this reservation."""
        from django.utils import timezone

        self.status = "cancelled"
        self.cancelled_at = timezone.now()
        self.save()

    def fulfill_reservation(self):
        """Mark this reservation as fulfilled (user purchased the product)."""
        from django.utils import timezone
        from .utils import send_reservation_fulfillment_email

        self.status = "fulfilled"
        self.fulfilled_at = timezone.now()
        self.save()
        
        # Send fulfillment email notification
        send_reservation_fulfillment_email(self)

    def is_expired(self):
        """Check if this active reservation has expired."""
        from django.utils import timezone

        if self.status == "active" and self.expires_at:
            return timezone.now() > self.expires_at
        return False


class Cart(models.Model):
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE, verbose_name="User")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")
    notes = models.TextField(blank=True, null=True, verbose_name="Notes")

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
            ("to_pay", "To Pay"),
            ("to_ship", "To Ship"),
            ("to_deliver", "To Deliver"),
            ("completed", "Completed"),
            ("cancelled", "Cancelled"),
            ("returned", "Returned"),
        ],
        default="to_pay",
        verbose_name="Order Status",
    )
    # Shipping Information
    shipping_address = models.TextField(
        verbose_name="Shipping Address", blank=True, null=True
    )
    contact_number = models.CharField(
        max_length=20, verbose_name="Contact Number", blank=True, null=True
    )
    notes = models.TextField(verbose_name="Order Notes", blank=True, null=True)
    tracking_code = models.CharField(
        verbose_name="Tracking Number", blank=True, null=True
    )

    # Payment Information
    payment_method = models.CharField(
        max_length=50,
        choices=[
            ("cash_on_delivery", "Cash on Delivery"),
            ("card", "Credit/Debit Card"),
            ("bank_transfer", "Bank Transfer"),
            ("gcash", "GCash"),
            ("paymaya", "PayMaya"),
            ("dob", "Digital Online Banking"),
            ("grab_pay", "GrabPay"),
            ("shopeepay", "ShopeePay"),
            ("qr_ph", "QR Ph"),
            ("cash", "Cash (POS)"),
        ],
        default="cash_on_delivery",
        verbose_name="Payment Method",
    )
    payment_status = models.CharField(
        max_length=50,
        choices=[
            ("pending", "Pending"),
            ("paid", "Paid"),
            ("failed", "Failed"),
            ("refunded", "Refunded"),
        ],
        default="pending",
        verbose_name="Payment Status",
    )
    paymongo_checkout_session_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="PayMongo Checkout Session ID",
    )
    paymongo_payment_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="PayMongo Payment ID",
        help_text="Payment ID from PayMongo checkout session",
    )
    paid_at = models.DateTimeField(blank=True, null=True, verbose_name="Paid At")

    # Cancel/Return reasons
    cancel_reason = models.TextField(
        verbose_name="Cancellation Reason", blank=True, null=True
    )
    return_reason = models.TextField(
        verbose_name="Return Reason", blank=True, null=True
    )

    class Meta:
        verbose_name = "Order"
        verbose_name_plural = "Orders"

    def __str__(self):
        return f"Order {self.id} by {self.user.username}"

    @property
    def total_amount(self):
        """Calculate total amount for this order"""
        return sum(item.product.price * item.quantity for item in self.items.all())


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


class Sales(models.Model):
    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, verbose_name="User", null=True
    )
    sale_date = models.DateTimeField(auto_now_add=True, verbose_name="Sale Date")
    last_modified = models.DateTimeField(auto_now=True, verbose_name="Last Modified")
    payment_method = models.CharField(
        max_length=50,
        choices=[
            ("cash", "Cash"),
            ("card", "Credit/Debit Card"),
            ("gcash", "GCash"),
            ("paymaya", "PayMaya"),
            ("bank_transfer", "Bank Transfer"),
        ],
        default="cash",
        verbose_name="Payment Method",
    )
    salesperson = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        verbose_name="Salesperson",
        related_name="sales_as_salesperson",
        null=True,
        blank=True,
        help_text="Staff member who processed this sale (POS only, None for online sales)",
    )
    order = models.OneToOneField(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Related Order",
        help_text="Linked order (1 Order = 1 Sale)",
    )

    class Meta:
        verbose_name = "Sale"
        verbose_name_plural = "Sales"

    def __str__(self):
        return f"Sold on {self.sale_date}"


class SalesItem(models.Model):
    sales = models.ForeignKey(
        Sales,
        verbose_name="Sale",
        on_delete=models.CASCADE,
        related_name="sales_item",
        null=True,
    )
    product = models.ForeignKey(
        Product,
        verbose_name="Product",
        on_delete=models.CASCADE,
        null=True,
    )
    quantity_sold = models.IntegerField(verbose_name="Quantity Sold")
    refunded_quantity = models.IntegerField(
        default=0,
        verbose_name="Refunded Quantity",
        help_text="Number of units refunded for this item",
    )
    refunded = models.BooleanField(
        default=False,
        verbose_name="Refunded",
        help_text="True if all units of this item have been refunded",
    )
    supplier_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Supplier Price",
        null=True,
        blank=True,
        help_text="Supplier price at time of sale (snapshot, doesn't change)",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Amount",
        help_text="Total amount for this item (negative for refunds)",
        default=0,
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.product.name} - {self.quantity_sold} - ₱{self.amount}"


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


class ChatRoom(models.Model):
    """Model for chat rooms between customers and staff."""

    owner = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="owned_chat_rooms",
        verbose_name="Room Owner",
        help_text="The customer who owns this chat room",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Last Updated")
    is_read_staff = models.BooleanField(
        default=False,
        verbose_name="Read by Staff",
        help_text="Indicates if staff has read the latest messages",
    )
    is_read_customer = models.BooleanField(
        default=False,
        verbose_name="Read by Customer",
        help_text="Indicates if customer has read the latest messages",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Is Active",
        help_text="Whether this chat room is currently active",
    )

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Chat Room"
        verbose_name_plural = "Chat Rooms"

    def __str__(self):
        return f"Chat Room: {self.owner.username}"

    def mark_read_by_staff(self):
        """Mark the chat room as read by staff."""
        self.is_read_staff = True
        self.save(update_fields=["is_read_staff"])

    def mark_read_by_customer(self):
        """Mark the chat room as read by customer."""
        self.is_read_customer = True
        self.save(update_fields=["is_read_customer"])


class ChatItem(models.Model):
    """Model for individual chat messages within a chat room."""

    MESSAGE_TYPES = [
        ("customer", "Customer Message"),
        ("staff", "Staff Message"),
        ("system", "System Message"),
    ]

    chat_room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name="chat_items",
        verbose_name="Chat Room",
    )
    sender = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_chat_items",
        verbose_name="Sender",
        help_text="User who sent the message (null for system messages)",
    )
    message_type = models.CharField(
        max_length=10,
        choices=MESSAGE_TYPES,
        default="customer",
        verbose_name="Message Type",
    )
    message = models.TextField(verbose_name="Message Content")
    sent_at = models.DateTimeField(auto_now_add=True, verbose_name="Sent At")

    class Meta:
        ordering = ["sent_at"]
        verbose_name = "Chat Item"
        verbose_name_plural = "Chat Items"

    def __str__(self):
        sender_name = self.sender.username if self.sender else "System"
        return f"{self.get_message_type_display()} from {sender_name} at {self.sent_at}"

    @property
    def is_staff_message(self):
        """Check if this is a message from staff."""
        return self.message_type == "staff"

    @property
    def is_customer_message(self):
        """Check if this is a message from a customer."""
        return self.message_type == "customer"

    @property
    def is_system_message(self):
        """Check if this is a system message."""
        return self.message_type == "system"

    def save(self, *args, **kwargs):
        """Override save to update chat room's updated_at timestamp."""
        super().save(*args, **kwargs)
        # Update the chat room's updated_at field
        self.chat_room.save(update_fields=["updated_at"])

        # Mark as unread for the recipient
        if self.message_type == "customer":
            self.chat_room.is_read_staff = False
            self.chat_room.save(update_fields=["is_read_staff"])
        elif self.message_type == "staff":
            self.chat_room.is_read_customer = False
            self.chat_room.save(update_fields=["is_read_customer"])
