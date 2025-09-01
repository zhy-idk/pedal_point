from rest_framework import serializers
from django.contrib.auth.models import User
from .models import *


class UserSerializer(serializers.ModelSerializer):
    is_staff = serializers.BooleanField(read_only=True)
    is_superuser = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = ["username", "is_staff", "is_superuser"]


class UsernameSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["username"]


class BrandsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brands
        fields = ["name", "slug"]


class CompatibilityAttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompatibilityAttribute
        fields = ["name"]


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ["name", "slug"]


class ProductVariantImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariantImage
        fields = ["image", "alt_text"]


class ProductSerializer(serializers.ModelSerializer):
    product_images = ProductVariantImageSerializer(many=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "variant_attribute",
            "brand",
            "sku",
            "price",
            "stock",
            "product_images",
            "available",
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
    brand = BrandsSerializer()
    category = ProductCategorySerializer()
    compatibility_attributes = CompatibilityAttributeSerializer(many=True)
    products = ProductSerializer(many=True)
    images = ProductImageSerializer(many=True)
    reviews = ProductReviewSerializer(many=True)

    class Meta:
        model = ProductListing
        fields = [
            "id",
            "name",
            "brand",
            "price",
            "description",
            "images",
            "image",
            "products",
            "compatibility_attributes",
            "category",
            "reviews",
            "slug",
            "available",
        ]


class ProductListingSummarySerializer(serializers.ModelSerializer):
    brand = BrandsSerializer()
    category = ProductCategorySerializer()
    compatibility = CompatibilityAttributeSerializer(many=True)

    class Meta:
        model = ProductListing
        fields = [
            "id",
            "name",
            "brand",
            "price",
            "image",
            "compatibility",
            "category",
            "slug",
            "available",
        ]


# Cart Serializers


class CartProductListingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductListing
        fields = ["id", "name", "image", "slug"]


class CartProductSerializer(serializers.ModelSerializer):
    product_listing = CartProductListingSerializer()

    class Meta:
        model = Product
        fields = ["id", "name", "sku", "price", "stock", "product_listing"]


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


class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer()

    class Meta:
        model = OrderItem
        fields = "__all__"


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    user = UsernameSerializer()

    class Meta:
        model = Order
        fields = "__all__"


class SalesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sales
        fields = "__all__"


class ScheduleQueueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceQueue
        fields = ["queue_date", "info", "user"]


class QueueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceQueue
        fields = "__all__"
