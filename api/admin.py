from django.contrib import admin
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.utils.html import format_html
from django import forms
from django.db import models
from .models import *
import nested_admin
from pedal_point.otp_admin import otp_admin_site

# Repair estimator admin
@admin.register(RepairEstimate, site=otp_admin_site)
class RepairEstimateAdmin(admin.ModelAdmin):
    list_display = ["user", "bike_type", "short_issue", "updated_at"]
    search_fields = ["user__username", "user__email", "issue", "bike_type"]
    readonly_fields = ["user", "issue", "bike_type", "ai_summary", "recommendations", "created_at", "updated_at"]
    ordering = ["-updated_at"]

    fieldsets = (
        (None, {"fields": ("user", "bike_type", "issue")}),
        ("AI Response", {"fields": ("ai_summary", "recommendations")}),
        ("Metadata", {"fields": ("created_at", "updated_at")}),
    )

    def has_add_permission(self, request):
        return False

    def short_issue(self, obj):
        return obj.issue[:100] + ("…" if len(obj.issue) > 100 else "")

    short_issue.short_description = "Issue"

# Import allauth models and admins
from allauth.account.models import EmailAddress, EmailConfirmation
from allauth.socialaccount.models import SocialApp, SocialAccount, SocialToken

# OTP devices
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice

try:
    from allauth.account.admin import EmailAddressAdmin, EmailConfirmationAdmin
    from allauth.socialaccount.admin import (
        SocialAppAdmin,
        SocialAccountAdmin,
        SocialTokenAdmin,
    )
except ImportError:
    # Fallback if admin classes aren't available
    EmailAddressAdmin = admin.ModelAdmin
    EmailConfirmationAdmin = admin.ModelAdmin
    SocialAppAdmin = admin.ModelAdmin
    SocialAccountAdmin = admin.ModelAdmin
    SocialTokenAdmin = admin.ModelAdmin


class UnassignedProductFilter(admin.SimpleListFilter):
    title = "Listing Status"
    parameter_name = "listing_status"

    def lookups(self, request, model_admin):
        return (
            ("assigned", "Assigned to Listing"),
            ("unassigned", "Not Assigned"),
        )

    def queryset(self, request, queryset):
        if self.value() == "assigned":
            return queryset.filter(product_listing__isnull=False)
        if self.value() == "unassigned":
            return queryset.filter(product_listing__isnull=True)


class ProductListingFilter(admin.SimpleListFilter):
    title = "Product Status"
    parameter_name = "product_status"

    def lookups(self, request, model_admin):
        return (
            ("with_products", "With Products"),
            ("without_products", "Without Products"),
        )

    def queryset(self, request, queryset):
        if self.value() == "with_products":
            return queryset.filter(products__isnull=False).distinct()
        if self.value() == "without_products":
            return queryset.filter(products__isnull=True)


# Inline for images of a single product (variant)
class ProductImageInline(nested_admin.NestedTabularInline):
    model = ProductImage
    extra = 1
    fields = ["image", "alt_text", "image_preview"]
    readonly_fields = ["image_preview"]

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width: 100px; height: auto;" />', obj.image.url
            )
        return "(No image)"

    image_preview.short_description = "Preview"


# Inline for images of specific variants (now just 'Products')
class ProductVariantImageInline(nested_admin.NestedStackedInline):
    model = ProductVariantImage
    extra = 0
    fields = ["image", "alt_text", "image_preview"]
    readonly_fields = ["image_preview"]

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width: 100px; height: auto;" />', obj.image.url
            )
        return "(No image)"

    image_preview.short_description = "Preview"


# Inline for Products (variants) within a ProductListing
class ProductInline(nested_admin.NestedTabularInline):
    model = Product
    extra = 0
    inlines = [ProductVariantImageInline]


# Inline for compatibility attribute values
class CompatibilityAttributeValueInline(nested_admin.NestedTabularInline):
    model = CompatibilityAttributeValue
    extra = 0
    fields = ["value", "display_name", "description"]


# Admin for Bike Compatibility Tags
@admin.register(BikeCompatibilityTag, site=otp_admin_site)
class BikeCompatibilityTagAdmin(admin.ModelAdmin):
    list_display = ["display_name", "tag_type", "value", "display_order", "get_product_count"]
    list_filter = ["tag_type"]
    search_fields = ["display_name", "value", "description"]
    list_editable = ["display_order"]
    ordering = ["tag_type", "-display_order", "display_name"]
    
    fieldsets = (
        ("Tag Information", {
            "fields": ("tag_type", "value", "display_name", "description")
        }),
        ("Display Settings", {
            "fields": ("display_order",),
            "description": "Higher order numbers appear first in lists"
        }),
    )
    
    def get_product_count(self, obj):
        """Show how many products use this tag"""
        count = obj.products.count()
        if count > 0:
            return f"{count} products"
        return "—"
    
    get_product_count.short_description = "Used By"


# Admin for Products
class ProductAdmin(nested_admin.NestedModelAdmin):
    inlines = [ProductVariantImageInline]
    list_display = [
        "name",
        "product_listing",
        "brand",
        "supply",
        "supplier_price",
        "price",
        "stock",
        "available",
        "get_listing_status",
    ]
    list_filter = [
        UnassignedProductFilter,
        "brand",
        "available",
        "product_listing__category",
        "product_listing",
    ]
    search_fields = ["name", "product_listing__name", "brand__name", "sku"]
    list_editable = ["available"]

    def get_listing_status(self, obj):
        """Show if product is assigned to a listing or available for assignment"""
        if obj.product_listing:
            return f"✓ {obj.product_listing.name}"
        return "🆓 Available"

    get_listing_status.short_description = "Listing Status"

    actions = ["remove_from_listing", "mark_available", "mark_unavailable"]

    def remove_from_listing(self, request, queryset):
        """Remove selected products from their current listing"""
        updated = queryset.update(product_listing=None)
        self.message_user(
            request, f"Successfully removed {updated} product(s) from their listings."
        )

    remove_from_listing.short_description = "Remove from listing"

    def mark_available(self, request, queryset):
        """Mark selected products as available"""
        updated = queryset.update(available=True)
        self.message_user(
            request, f"Successfully marked {updated} product(s) as available."
        )

    mark_available.short_description = "Mark as available"

    def mark_unavailable(self, request, queryset):
        """Mark selected products as unavailable"""
        updated = queryset.update(available=False)
        self.message_user(
            request, f"Successfully marked {updated} product(s) as unavailable."
        )

    mark_unavailable.short_description = "Mark as unavailable"


# --------------------------
# Custom Form for ProductListingAdmin
# --------------------------
class ProductListingAdminForm(forms.ModelForm):
    available_products = forms.ModelMultipleChoiceField(
        queryset=Product.objects.filter(product_listing__isnull=True),
        required=False,
        label="Attach Available Products",
        help_text="Select products not yet assigned to any listing. Products will be displayed as: Name - Brand - SKU - Price",
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = ProductListing
        fields = "__all__"
        exclude = []  # Make sure we're not excluding any fields

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Customize the available_products field to show more product info
        self.fields["available_products"].label_from_instance = self._product_label

        if self.instance.pk:  # editing existing listing
            # include products already linked to this listing + unassigned ones
            self.fields["available_products"].queryset = Product.objects.filter(
                models.Q(product_listing__isnull=True)
                | models.Q(product_listing=self.instance)
            )
            # preselect products already assigned
            self.fields["available_products"].initial = list(
                self.instance.products.values_list("id", flat=True)
            )
            print(
                f"DEBUG: Editing existing listing {self.instance.pk}, initial products: {self.fields['available_products'].initial}"
            )
        else:
            # for new listings, only show unassigned products
            self.fields["available_products"].queryset = Product.objects.filter(
                product_listing__isnull=True
            )
            print(
                f"DEBUG: Creating new listing, available products: {self.fields['available_products'].queryset.count()}"
            )

    def _product_label(self, obj):
        """Custom label for products in the form"""
        brand_name = obj.brand.name if obj.brand else "No Brand"
        sku = obj.sku if obj.sku else "No SKU"
        return f"{obj.name} - {brand_name} - {sku} - ${obj.price}"

    # Note: Product linking is now handled in the admin's save_model method

    def clean(self):
        """Validate the form data"""
        cleaned_data = super().clean()
        # Ensure we have the available_products data
        if "available_products" not in cleaned_data:
            cleaned_data["available_products"] = []
        print(
            f"DEBUG: Clean method - available_products: {cleaned_data.get('available_products')}"
        )
        print(f"DEBUG: Clean method - all data: {cleaned_data}")
        return cleaned_data


# Admin for ProductListing
class ProductListingAdmin(nested_admin.NestedModelAdmin):
    form = ProductListingAdminForm
    inlines = [ProductImageInline, ProductInline]
    list_display = [
        "name",
        "brand",
        "slug",
        "category",
        "price",
        "available",
        "get_bike_builder_status",
        "get_product_count",
        "get_total_value",
    ]
    list_filter = [
        ProductListingFilter, 
        "category", 
        "available", 
        "bike_builder_enabled",
        "builder_category",
    ]
    search_fields = ["name", "description"]
    readonly_fields = ["get_current_products"]
    filter_horizontal = ["compatibility_tags"]

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "name",
                    # "slug",
                    "category",
                    "description",
                    "image",
                    "price",
                    "available",
                    "available_products",  # 👈 show available products here
                )
            },
        ),
        (
            "Bike Builder & Compatibility",
            {
                "fields": (
                    "bike_builder_enabled",
                    "builder_category",
                    "builder_priority",
                    "compatibility_tags",
                ),
                "description": (
                    "<strong>Bike Builder Configuration:</strong><br>"
                    "• Enable to make this product available in the bike builder wizard<br>"
                    "• Select the component type (Frame, Wheels, Brakes, etc.)<br>"
                    "• Set priority for display order (higher shows first)<br><br>"
                    "<strong>Compatibility Tags:</strong><br>"
                    "• <strong>Use Case:</strong> Select which riding styles this product suits (City, Trail, Casual)<br>"
                    "• <strong>Budget Range:</strong> Select price tier (Budget ₱15k-24k, Mid ₱25k-75k, Premium ₱75k+)<br>"
                    "• <strong>Physical Compatibility:</strong> Select specs like wheel size, brake type, material, etc."
                ),
                "classes": ("collapse",),  # Make collapsible
            },
        ),
        (
            "Current Products",
            {
                "fields": ("get_current_products",),
                "description": "Products currently assigned to this listing.",
            },
        ),
    )

    # Note: Product linking and price updates are now handled in save_model

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(self.readonly_fields)
        if obj:  # editing an existing object
            readonly_fields.append("slug")
        return readonly_fields

    def get_product_count(self, obj):
        """Display the number of products attached to this listing"""
        count = obj.products.count()
        return f"{count} product{'s' if count != 1 else ''}"

    get_product_count.short_description = "Products"

    def get_total_value(self, obj):
        """Display the total value of all products in this listing"""
        total = sum(product.price * product.stock for product in obj.products.all())
        return f"${total:.2f}"

    get_total_value.short_description = "Total Value"

    def get_current_products(self, obj):
        """Display currently assigned products in a readable format"""
        if not obj.pk:
            return "Save the listing first to see assigned products."

        products = obj.products.all()
        if not products:
            return "No products assigned yet."

        product_list = []
        for product in products:
            brand_name = product.brand.name if product.brand else "No Brand"
            product_list.append(
                f"• {product.name} ({brand_name}) - ${product.price} - Qty: {product.stock}"
            )

        return format_html("<br>".join(product_list))

    get_current_products.short_description = "Currently Assigned Products"

    def get_bike_builder_status(self, obj):
        """Display bike builder status with icon"""
        if obj.bike_builder_enabled:
            category_display = obj.get_builder_category_display() if obj.builder_category else "N/A"
            return format_html(
                '<span style="color: green;">✓ {}</span>',
                category_display
            )
        return format_html('<span style="color: gray;">—</span>')
    
    get_bike_builder_status.short_description = "Bike Builder"
    get_bike_builder_status.admin_order_field = "bike_builder_enabled"

    def get_form(self, request, obj=None, **kwargs):
        """Ensure we're using our custom form"""
        print(f"DEBUG: Admin get_form called for obj: {obj}")
        form = super().get_form(request, obj, **kwargs)
        print(f"DEBUG: Form fields: {list(form.base_fields.keys())}")
        return form

    def save_model(self, request, obj, form, change):
        """Override save_model to handle product linking"""
        print(f"DEBUG: Admin save_model called for obj: {obj}")

        # Save the ProductListing first
        super().save_model(request, obj, form, change)

        # Now handle the product linking
        selected = form.cleaned_data.get("available_products")
        print(f"DEBUG: Admin save_model - selected products: {selected}")

        if selected is not None:
            print(
                f"DEBUG: Admin save_model - linking {len(selected)} products to listing {obj.id}"
            )
            # unlink old products not in selection
            Product.objects.filter(product_listing=obj).exclude(id__in=selected).update(
                product_listing=None
            )
            # link selected products
            for product in selected:
                product.product_listing = obj
                product.save()
                print(
                    f"DEBUG: Admin save_model - linked product {product.id} ({product.name}) to listing {obj.id}"
                )
        else:
            print("DEBUG: Admin save_model - no products selected")

        # Update the price from variants after linking products
        obj.update_price_from_variants()

    actions = [
        "update_prices_from_variants",
        "mark_all_available",
        "mark_all_unavailable",
        "enable_bike_builder",
        "disable_bike_builder",
    ]

    def update_prices_from_variants(self, request, queryset):
        """Update prices for selected listings based on their variants"""
        updated = 0
        for listing in queryset:
            listing.update_price_from_variants()
            updated += 1
        self.message_user(
            request, f"Successfully updated prices for {updated} listing(s)."
        )

    update_prices_from_variants.short_description = "Update prices from variants"

    def mark_all_available(self, request, queryset):
        """Mark all products in selected listings as available"""
        updated = 0
        for listing in queryset:
            listing.products.update(available=True)
            updated += listing.products.count()
        self.message_user(
            request, f"Successfully marked {updated} product(s) as available."
        )

    mark_all_available.short_description = "Mark all products as available"

    def mark_all_unavailable(self, request, queryset):
        """Mark all products in selected listings as unavailable"""
        updated = 0
        for listing in queryset:
            listing.products.update(available=False)
            updated += listing.products.count()
        self.message_user(
            request, f"Successfully marked {updated} product(s) as unavailable."
        )

    mark_all_unavailable.short_description = "Mark all products as unavailable"

    def enable_bike_builder(self, request, queryset):
        """Enable selected listings in bike builder"""
        updated = queryset.update(bike_builder_enabled=True)
        self.message_user(
            request, 
            f"Successfully enabled {updated} listing(s) in bike builder. Don't forget to set the builder category!"
        )
    
    enable_bike_builder.short_description = "Enable in bike builder"

    def disable_bike_builder(self, request, queryset):
        """Disable selected listings in bike builder"""
        updated = queryset.update(bike_builder_enabled=False)
        self.message_user(
            request, f"Successfully disabled {updated} listing(s) in bike builder."
        )
    
    disable_bike_builder.short_description = "Disable in bike builder"


# Enhanced admin for other models
@admin.register(Brands, site=otp_admin_site)
class BrandsAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    fields = ["name"]
    search_fields = ["name"]


@admin.register(ProductCategory, site=otp_admin_site)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "parent", "is_component", "component_type", "get_subcategory_count"]
    list_filter = ["is_component", "parent", "component_type"]
    fields = ["name", "parent", "is_component", "component_type"]
    search_fields = ["name"]
    
    def get_subcategory_count(self, obj):
        """Show number of subcategories"""
        count = obj.subcategories.count()
        if count > 0:
            return f"{count} subcategories"
        return "—"
    
    get_subcategory_count.short_description = "Subcategories"


@admin.register(ProductReview, site=otp_admin_site)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ["user", "product_listing", "star", "date"]
    list_filter = ["star", "date"]
    search_fields = ["user__username", "product_listing__name"]
    readonly_fields = ["date"]


@admin.register(Cart, site=otp_admin_site)
class CartAdmin(admin.ModelAdmin):
    list_display = ["user", "created_at", "updated_at"]
    readonly_fields = ["created_at", "updated_at"]
    search_fields = ["user__username"]


@admin.register(CartItem, site=otp_admin_site)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ["cart", "product", "quantity"]
    search_fields = ["cart__user__username", "product__name"]


@admin.register(Order, site=otp_admin_site)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "status", "created_at", "total_amount"]
    list_filter = ["status", "created_at"]
    search_fields = ["user__username", "shipping_address", "notes"]
    readonly_fields = ["created_at", "total_amount"]

    def total_amount(self, obj):
        total = sum(item.product.price * item.quantity for item in obj.items.all())
        return f"₱{total:.2f}"

    total_amount.short_description = "Total Amount"


@admin.register(OrderItem, site=otp_admin_site)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ["order", "product", "quantity"]
    search_fields = ["order__user__username", "product__name"]


@admin.register(ServiceQueue, site=otp_admin_site)
class ServiceQueueAdmin(admin.ModelAdmin):
    list_display = ["user", "queue_date", "info"]
    list_filter = ["queue_date"]
    search_fields = ["user__username", "info"]


otp_admin_site.register(ChatRoom)
otp_admin_site.register(ChatItem)
@admin.register(Sales, site=otp_admin_site)
class SalesAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'salesperson', 'sale_date', 'payment_method', 'get_total_amount']
    list_filter = ['payment_method', 'sale_date', 'salesperson']
    search_fields = ['user__username', 'salesperson__username']
    readonly_fields = ['sale_date']
    date_hierarchy = 'sale_date'
    
    def get_total_amount(self, obj):
        total = sum(item.amount or 0 for item in obj.sales_item.all())
        return f"₱{total:,.2f}"
    get_total_amount.short_description = 'Total Amount'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'salesperson').prefetch_related('sales_item')

otp_admin_site.register(SalesItem)
otp_admin_site.register(UserProfile)
otp_admin_site.register(ReservedProduct)
otp_admin_site.register(ProductSupplier)

# Register remaining models
otp_admin_site.register(ProductVariantImage)
otp_admin_site.register(ProductImage)
otp_admin_site.register(ProductListing, ProductListingAdmin)
otp_admin_site.register(Product, ProductAdmin)

# Register Django's built-in User and Group models with OTP admin
otp_admin_site.register(User, UserAdmin)
otp_admin_site.register(Group, GroupAdmin)

# Register django-allauth models with OTP admin
otp_admin_site.register(EmailAddress, EmailAddressAdmin)
otp_admin_site.register(EmailConfirmation, EmailConfirmationAdmin)
otp_admin_site.register(SocialApp, SocialAppAdmin)
otp_admin_site.register(SocialAccount, SocialAccountAdmin)
otp_admin_site.register(SocialToken, SocialTokenAdmin)


# Register OTP devices in OTP-protected admin (use simple ModelAdmin)
class TOTPDeviceAdmin(admin.ModelAdmin):
    list_display = ["user", "name", "confirmed"]
    list_filter = ["confirmed"]
    search_fields = ["user__username", "name"]


class StaticDeviceAdmin(admin.ModelAdmin):
    list_display = ["user", "name"]
    search_fields = ["user__username", "name"]


otp_admin_site.register(TOTPDevice, TOTPDeviceAdmin)
otp_admin_site.register(StaticDevice, StaticDeviceAdmin)