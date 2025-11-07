from rest_framework import serializers
from django.contrib.auth.models import User
from .models import *


class UserInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ["address", "contact_number", "image", "email_order_updates", "email_reservation_updates", "email_service_updates"]


class StaffPermissionsSerializer(serializers.ModelSerializer):
    """Serializer for staff permissions"""
    class Meta:
        model = StaffPermissions
        fields = [
            "can_access_pos",
            "can_access_chats",
            "can_access_orders",
            "can_access_listings",
            "can_access_inventory",
            "can_access_queueing",
            "can_access_reservations",
            "can_access_suppliers",
        ]


class AuditLogActorSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "full_name"]

    def get_full_name(self, obj):
        if obj.first_name and obj.last_name:
            return f"{obj.first_name} {obj.last_name}"
        return obj.first_name or obj.last_name or obj.username


class AuditLogSerializer(serializers.ModelSerializer):
    actor = AuditLogActorSerializer(read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "module",
            "action",
            "description",
            "severity",
            "metadata",
            "target_object_id",
            "target_object_repr",
            "actor",
            "ip_address",
            "user_agent",
            "created_at",
        ]


class UserSerializer(serializers.ModelSerializer):
    is_staff = serializers.BooleanField(read_only=True)
    is_superuser = serializers.BooleanField(read_only=True)
    user_info = UserInfoSerializer(many=True)
    staff_permissions = StaffPermissionsSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "user_info",
            "is_staff",
            "is_superuser",
            "staff_permissions",
        ]


class UsernameSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["username"]


class StaffUserSerializer(serializers.ModelSerializer):
    """Comprehensive user serializer for staff management"""

    full_name = serializers.SerializerMethodField()
    staff_permissions = StaffPermissionsSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "staff_permissions",
            "is_staff",
            "is_superuser",
            "is_active",
            "date_joined",
            "last_login",
        ]
        read_only_fields = ["id", "date_joined", "last_login"]

    def get_full_name(self, obj):
        """Combine first_name and last_name"""
        if obj.first_name and obj.last_name:
            return f"{obj.first_name} {obj.last_name}"
        elif obj.first_name:
            return obj.first_name
        elif obj.last_name:
            return obj.last_name
        else:
            return obj.username


class BrandsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brands
        fields = ["id", "name", "slug"]


class BikeCompatibilityTagSerializer(serializers.ModelSerializer):
    """Serializer for bike compatibility tags"""
    tag_type_display = serializers.CharField(source='get_tag_type_display', read_only=True)
    
    class Meta:
        model = BikeCompatibilityTag
        fields = ["id", "tag_type", "tag_type_display", "value", "display_name", "description", "display_order"]


# Old Compatibility Serializers (Deprecated - kept for backward compatibility)
class CompatibilityAttributeValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompatibilityAttributeValue
        fields = ["id", "value", "display_name"]


class CompatibilityAttributeSerializer(serializers.ModelSerializer):
    values = CompatibilityAttributeValueSerializer(many=True, read_only=True)
    
    class Meta:
        model = CompatibilityAttribute
        fields = ["id", "name", "attribute_type", "is_required", "values"]


class CompatibilityGroupSerializer(serializers.ModelSerializer):
    attributes = CompatibilityAttributeSerializer(many=True, read_only=True)
    
    class Meta:
        model = CompatibilityGroup
        fields = ["id", "name", "slug", "description", "attributes"]


class CompatibilityAttributeValueDetailSerializer(serializers.ModelSerializer):
    attribute = serializers.SerializerMethodField()
    
    class Meta:
        model = CompatibilityAttributeValue
        fields = ["id", "value", "display_name", "description", "attribute"]


class ProductCategorySerializer(serializers.ModelSerializer):
    subcategories = serializers.SerializerMethodField()
    
    class Meta:
        model = ProductCategory
        fields = ["id", "name", "slug", "parent", "is_component", "component_type", "subcategories"]
    
    def get_subcategories(self, obj):
        """Get immediate subcategories"""
        if obj.subcategories.exists():
            return ProductCategorySerializer(obj.subcategories.all(), many=True).data
        return []


class ProductVariantImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariantImage
        fields = ["id", "image", "alt_text"]


class ProductSerializer(serializers.ModelSerializer):
    product_images = ProductVariantImageSerializer(many=True, required=False)
    supply = serializers.StringRelatedField(source="supply.name", read_only=True)
    supply_id = serializers.IntegerField(source="supply.id", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "variant_attribute",
            "brand",
            "sku",
            "price",
            "supplier_price",
            "stock",
            "product_images",
            "available",
            "supply",
            "supply_id",
        ]


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["image", "alt_text"]


class ProductReviewSerializer(serializers.ModelSerializer):
    user = UsernameSerializer()
    date = serializers.SerializerMethodField()

    class Meta:
        model = ProductReview
        fields = ["review", "star", "date", "user"]

    def get_date(self, obj):
        return obj.date.date().strftime("%m/%d/%Y") if obj.date else None


class ProductListingSerializer(serializers.ModelSerializer):
    brand = BrandsSerializer(read_only=True)
    category = ProductCategorySerializer(read_only=True)
    compatibility_tags = BikeCompatibilityTagSerializer(many=True, read_only=True)
    products = ProductSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    reviews = ProductReviewSerializer(many=True, read_only=True)
    
    # Old compatibility fields (deprecated, read-only for backward compatibility)
    compatibility_attributes = CompatibilityAttributeValueSerializer(many=True, read_only=True, required=False)
    compatible_with = CompatibilityAttributeValueSerializer(many=True, read_only=True, required=False)

    # Write-only fields for foreign keys
    category_id = serializers.IntegerField(
        write_only=True, required=False, allow_null=True
    )
    name_input = serializers.CharField(
        write_only=True, required=False, allow_blank=True, source="name"
    )
    
    # Write-only field for compatibility tags
    compatibility_tag_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
    )

    # Override name to handle fallback to products (read-only)
    name = serializers.SerializerMethodField()

    class Meta:
        model = ProductListing
        fields = [
            "id",
            "name",
            "name_input",
            "brand",
            "price",
            "description",
            "images",
            "image",
            "products",
            "compatibility_tags",
            "compatibility_tag_ids",
            "compatibility_attributes",  # deprecated
            "compatible_with",  # deprecated
            "category",
            "category_id",
            "reviews",
            "slug",
            "available",
            "bike_builder_enabled",
            "builder_category",
            "builder_priority",
        ]

    def get_name(self, obj):
        """Get name from field, or fallback to getting from first product"""
        if obj.name:
            return obj.name
        return obj.get_name_from_products()

    def create(self, validated_data):
        category_id = validated_data.pop("category_id", None)
        compatibility_tag_ids = validated_data.pop("compatibility_tag_ids", None)
        
        if category_id:
            from .models import ProductCategory
            validated_data["category"] = ProductCategory.objects.get(id=category_id)
        
        instance = super().create(validated_data)
        
        # Set compatibility tags
        if compatibility_tag_ids is not None:
            instance.compatibility_tags.set(compatibility_tag_ids)
        
        return instance

    def update(self, instance, validated_data):
        category_id = validated_data.pop("category_id", None)
        compatibility_tag_ids = validated_data.pop("compatibility_tag_ids", None)
        
        print(f"DEBUG: Updating listing {instance.id}")
        print(f"DEBUG: Compatibility tag IDs: {compatibility_tag_ids}")
        
        if category_id:
            from .models import ProductCategory
            instance.category = ProductCategory.objects.get(id=category_id)
        
        # Update other fields first
        instance = super().update(instance, validated_data)
        
        # Update compatibility tags after instance is saved
        if compatibility_tag_ids is not None:
            instance.compatibility_tags.set(compatibility_tag_ids)
            print(f"DEBUG: Set compatibility_tags to: {list(instance.compatibility_tags.values_list('id', flat=True))}")
        
        return instance


class ProductListingSummarySerializer(serializers.ModelSerializer):
    brand = BrandsSerializer()
    category = ProductCategorySerializer()
    compatibility_tags = BikeCompatibilityTagSerializer(many=True, read_only=True)

    class Meta:
        model = ProductListing
        fields = [
            "id",
            "name",
            "brand",
            "price",
            "image",
            "compatibility_tags",
            "category",
            "slug",
            "available",
        ]


class ChatItemSerializer(serializers.ModelSerializer):
    """Serializer for ChatItem model."""

    sender = UserSerializer(read_only=True)
    sender_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source="sender",
        write_only=True,
        required=False,
        allow_null=True,
    )
    
    # Add fields for frontend compatibility
    content = serializers.CharField(source="message", read_only=True)
    formatted_timestamp = serializers.SerializerMethodField()
    staff_name = serializers.SerializerMethodField()
    customer_name = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = ChatItem
        fields = [
            "id",
            "chat_room",
            "sender",
            "sender_id",
            "message_type",
            "message",
            "content",  # Alias for message
            "sent_at",
            "formatted_timestamp",
            "staff_name",
            "customer_name",
            "user_name",
            "is_read",
            "is_staff_message",
            "is_customer_message",
            "is_system_message",
        ]
        read_only_fields = ["id", "sent_at", "sender"]
    
    def get_formatted_timestamp(self, obj):
        """Format timestamp for display."""
        return obj.sent_at.strftime("%I:%M %p")
    
    def get_staff_name(self, obj):
        """Get staff name if sender is staff."""
        if obj.sender and obj.sender.is_staff:
            return obj.sender.get_full_name() or obj.sender.username
        return None
    
    def get_customer_name(self, obj):
        """Get customer name if sender is customer."""
        if obj.sender and not obj.sender.is_staff:
            return obj.sender.get_full_name() or obj.sender.username
        return None
    
    def get_user_name(self, obj):
        """Get sender name."""
        if obj.sender:
            return obj.sender.get_full_name() or obj.sender.username
        return "Anonymous"
    
    def get_is_read(self, obj):
        """Check if message is read based on chat room read status."""
        if obj.message_type == "customer":
            return obj.chat_room.is_read_staff
        elif obj.message_type == "staff":
            return obj.chat_room.is_read_customer
        return True

    def validate_message_type(self, value):
        """Validate message type based on sender."""
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            user = request.user
            if user.is_staff and value == "customer":
                raise serializers.ValidationError(
                    "Staff users cannot send customer messages."
                )
            elif not user.is_staff and value == "staff":
                raise serializers.ValidationError(
                    "Non-staff users cannot send staff messages."
                )
        return value


class ChatRoomListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing chat rooms (without all chat items)."""

    owner = UserSerializer(read_only=True)
    unread_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = [
            "id",
            "owner",
            "created_at",
            "updated_at",
            "is_read_staff",
            "is_read_customer",
            "is_active",
            "unread_count",
            "last_message",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_unread_count(self, obj):
        """Get unread message count based on user type."""
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            user = request.user
            if user.is_staff and not obj.is_read_staff:
                return obj.chat_items.filter(message_type="customer").count()
            elif not user.is_staff and not obj.is_read_customer:
                return obj.chat_items.filter(message_type="staff").count()
        return 0

    def get_last_message(self, obj):
        """Get the last message in the chat room."""
        last_item = obj.chat_items.last()
        if last_item:
            return {
                "message": last_item.message,
                "sent_at": last_item.sent_at,
                "message_type": last_item.message_type,
                "sender": last_item.sender.username if last_item.sender else "System",
            }
        return None


# Cart Serializers


class CartProductListingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductListing
        fields = ["id", "name", "image", "slug"]


class CartProductSerializer(serializers.ModelSerializer):
    product_listing = CartProductListingSerializer()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "sku",
            "price",
            "stock",
            "product_listing",
            "variant_attribute",
        ]


class CartItemSerializer(serializers.ModelSerializer):
    product = CartProductSerializer()

    class Meta:
        model = CartItem
        fields = ["product", "quantity"]


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)

    class Meta:
        model = Cart
        fields = ["items", "created_at", "updated_at"]


# Order Serializers


class OrderListingSerializer(serializers.ModelSerializer):
    category = ProductCategorySerializer()

    class Meta:
        model = ProductListing
        fields = ["name", "image", "slug", "category"]


class OrderProductSerializer(serializers.ModelSerializer):
    product_listing = OrderListingSerializer()

    class Meta:
        model = Product
        fields = ["variant_attribute", "price", "product_listing"]


class OrderItemSerializer(serializers.ModelSerializer):
    product = OrderProductSerializer()

    class Meta:
        model = OrderItem
        fields = "__all__"


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    user = UsernameSerializer()
    total_amount = serializers.ReadOnlyField()

    class Meta:
        model = Order
        fields = "__all__"


class SalesItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    
    class Meta:
        model = SalesItem
        fields = ["id", "product", "quantity_sold", "refunded_quantity", "refunded", "supplier_price", "amount"]


class SalesSerializer(serializers.ModelSerializer):
    user = UsernameSerializer(read_only=True)
    salesperson = UsernameSerializer(read_only=True)
    sales_item = SalesItemSerializer(many=True, read_only=True)
    total_amount = serializers.SerializerMethodField()
    net_revenue = serializers.SerializerMethodField()
    capital = serializers.SerializerMethodField()
    
    class Meta:
        model = Sales
        fields = ["id", "user", "sale_date", "last_modified", "payment_method", "salesperson", "order", "sales_item", "total_amount", "net_revenue", "capital"]
    
    def get_total_amount(self, obj):
        # Sum up all item amounts (positive for sales, negative for refunds)
        # For backward compatibility, calculate from price if amount is None
        total = 0
        for item in obj.sales_item.all():
            if item.amount is not None:
                total += float(item.amount)
            elif item.product:
                # Fallback for old records without amount
                total += float(item.product.price) * item.quantity_sold
        return total
    
    def get_net_revenue(self, obj):
        """Calculate net revenue (total - capital cost)"""
        total = self.get_total_amount(obj)
        capital = self.get_capital(obj)
        return total - capital
    
    def get_capital(self, obj):
        """Calculate total capital cost (supplier prices * quantities)"""
        capital = 0
        for item in obj.sales_item.all():
            if item.supplier_price is not None:
                # Only count non-refunded quantities
                non_refunded_qty = item.quantity_sold - item.refunded_quantity
                capital += float(item.supplier_price) * non_refunded_qty
        return capital


class ScheduleQueueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceQueue
        fields = ["queue_date", "info", "user"]


class QueueSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = ServiceQueue
        fields = "__all__"
    
    def create(self, validated_data):
        # Extract user_id and set user object
        user_id = validated_data.pop('user_id', None)
        if user_id:
            from django.contrib.auth.models import User
            validated_data['user'] = User.objects.get(id=user_id)
        return super().create(validated_data)


class ReservedProductSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    product = ProductSerializer(read_only=True)
    product_id = serializers.IntegerField(write_only=True)
    time_remaining = serializers.SerializerMethodField()
    
    class Meta:
        model = ReservedProduct
        fields = [
            'id', 'product', 'product_id', 'user', 'status', 'queue_position',
            'created_at', 'reserved_at', 'expires_at', 'fulfilled_at', 'cancelled_at',
            'time_remaining'
        ]
        read_only_fields = ['status', 'queue_position', 'reserved_at', 'expires_at', 'fulfilled_at', 'cancelled_at']
    
    def get_time_remaining(self, obj):
        """Get time remaining for active reservations."""
        from django.utils import timezone
        
        if obj.status == 'active' and obj.expires_at:
            remaining = obj.expires_at - timezone.now()
            if remaining.total_seconds() > 0:
                days = remaining.days
                hours = remaining.seconds // 3600
                return {
                    'days': days,
                    'hours': hours,
                    'total_seconds': int(remaining.total_seconds())
                }
        return None
