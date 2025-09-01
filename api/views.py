from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.db.models import Count
from .models import *
from .serializer import *
from django.shortcuts import get_object_or_404
import random


# CSRF & Auth
@ensure_csrf_cookie
@require_http_methods(["GET"])
def get_csrf_token(request):
    return JsonResponse({"message": "cookie has been set."})


@api_view(["GET"])
def test_user(request):
    return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)


# Brands
@api_view(["GET"])
def get_brands(request):
    brands = Brands.objects.all()
    serializer = BrandsSerializer(brands, many=True)
    return Response(serializer.data)


# Categories
@api_view(["GET"])
def get_product_categories(request):
    categories = ProductCategory.objects.all()
    serializer = ProductCategorySerializer(categories, many=True)
    return Response(serializer.data)


# Listings
@api_view(["GET"])
def get_product_listings(request):
    listings = ProductListing.objects.filter(available=True).distinct()
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
            .filter(variant_count__gt=0)
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
        return Response(status=status.HTTP_204_NO_CONTENT)
    except Cart.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
def checkout(request):
    user = request.user
    try:
        cart = Cart.objects.get(user=user)
        order = Order.objects.create(user=user)
        for item in cart.items.all():
            OrderItem.objects.create(
                order=order, product=item.product, quantity=item.quantity
            )
        cart.delete()
        serializer = OrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    except Cart.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


# Orders
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
    orders = Order.objects.all()
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


# Sales
@api_view(["GET"])
def get_sales(request):
    sales = Sales.objects.all()
    serializer = SalesSerializer(sales, many=True)
    return Response(serializer.data)


# Repair Queue
@api_view(["GET"])
def get_all_schedule(request):
    queue = ServiceQueue.objects.all()
    serializer = QueueSerializer(queue, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def schedule_service(request):
    data = {
        "queue_date": request.data.get("queue_date"),
        "info": request.data.get("info"),
        "status": "pending",
        "user": request.user.id,
    }

    serializer = QueueSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
