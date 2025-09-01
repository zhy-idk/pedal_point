from django.contrib import admin
from django.utils.html import format_html
from django import forms
from django.db import models
from .models import *
import nested_admin


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


# Admin for Compatibility Groups
@admin.register(CompatibilityGroup)
class CompatibilityGroupAdmin(nested_admin.NestedModelAdmin):
    list_display = ["name", "slug", "description"]
    fields = ["name", "description"]
    search_fields = ["name", "description"]


# Admin for Compatibility Attributes
@admin.register(CompatibilityAttribute)
class CompatibilityAttributeAdmin(nested_admin.NestedModelAdmin):
    list_display = ["name", "group", "attribute_type", "is_required"]
    list_filter = ["group", "attribute_type", "is_required"]
    search_fields = ["name", "group__name"]
    inlines = [CompatibilityAttributeValueInline]


# Admin for Compatibility Attribute Values
@admin.register(CompatibilityAttributeValue)
class CompatibilityAttributeValueAdmin(admin.ModelAdmin):
    list_display = ["attribute", "display_name", "value"]
    list_filter = ["attribute__group", "attribute"]
    search_fields = ["display_name", "value", "attribute__name"]


# Admin for Products
class ProductAdmin(nested_admin.NestedModelAdmin):
    inlines = [ProductVariantImageInline]
    list_display = [
        "name",
        "product_listing",
        "brand",
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
        "category",
        "price",
        "available",
        "get_product_count",
        "get_total_value",
    ]
    list_filter = [ProductListingFilter, "category", "available"]
    search_fields = ["name", "description"]
    readonly_fields = ["slug", "get_current_products"]
    filter_horizontal = ["compatibility_attributes", "compatible_with"]

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "slug",
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
            "Compatibility",
            {
                "fields": ("compatibility_attributes", "compatible_with"),
                "description": "Product Attributes: What this product IS. Compatible With: What this product works WITH.",
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


# Enhanced admin for other models
@admin.register(Brands)
class BrandsAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    fields = ["name"]
    search_fields = ["name"]


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ["user", "product_listing", "star", "date"]
    list_filter = ["star", "date"]
    search_fields = ["user__username", "product_listing__name"]
    readonly_fields = ["date"]


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["user", "created_at", "updated_at"]
    readonly_fields = ["created_at", "updated_at"]
    search_fields = ["user__username"]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ["cart", "product", "quantity"]
    search_fields = ["cart__user__username", "product__name"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "status", "created_at"]
    list_filter = ["status", "created_at"]
    search_fields = ["user__username"]
    readonly_fields = ["created_at"]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ["order", "product", "quantity"]
    search_fields = ["order__user__username", "product__name"]


@admin.register(Sales)
class SalesAdmin(admin.ModelAdmin):
    list_display = ["product_listing", "user", "quantity_sold", "sale_date"]
    list_filter = ["sale_date"]
    search_fields = ["product_listing__name", "user__username"]
    readonly_fields = ["sale_date"]


@admin.register(ServiceQueue)
class ServiceQueueAdmin(admin.ModelAdmin):
    list_display = ["user", "queue_date", "info"]
    list_filter = ["queue_date"]
    search_fields = ["user__username", "info"]


# Register remaining models
admin.site.register(ProductVariantImage)
admin.site.register(ProductImage)
admin.site.register(ProductListing, ProductListingAdmin)
admin.site.register(Product, ProductAdmin)
