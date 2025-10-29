from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.db.models import Count, Max, Q
from .models import *
from .serializer import *
from django.shortcuts import get_object_or_404
from .realtime_utils import (
    send_cart_update,
    send_order_update,
    send_inventory_update,
    send_notification,
)
import random
from django.conf import settings
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


def deduct_inventory_for_order(order):
    """Deduct inventory for a confirmed order and fulfill any reservations"""
    try:
        for item in order.items.all():
            product = item.product
            if product.stock >= item.quantity:
                product.stock -= item.quantity
                product.save()

                # Check if user has an active reservation for this product and fulfill it
                user_reservation = ReservedProduct.objects.filter(
                    product=product, user=order.user, status="active"
                ).first()

                if user_reservation:
                    user_reservation.fulfill_reservation()
                    logger.info(
                        f"Fulfilled reservation {user_reservation.id} for user {order.user.username}"
                    )

                    # Process next in queue if product still has stock
                    if product.stock > 0:
                        from .utils import process_product_reservations

                        process_product_reservations(product)

                # Send inventory update
                send_inventory_update(
                    {
                        "type": "stock_update",
                        "product_id": product.id,
                        "new_stock": product.stock,
                        "product_name": product.name,
                    }
                )
            else:
                logger.warning(
                    f"Insufficient stock for product {product.id} in order {order.id}"
                )
    except Exception as e:
        logger.error(f"Error deducting inventory for order {order.id}: {str(e)}")


def clear_reserved_cart(user_id, order_id):
    """Clear cart that was reserved for an order"""
    try:
        cart = Cart.objects.get(
            user_id=user_id, notes=f"Reserved for Order #{order_id}"
        )
        cart.delete()
    except Cart.DoesNotExist:
        pass


def map_paymongo_source_to_payment_method(source_type):
    """Map PayMongo source type to our payment method"""
    mapping = {
        "card": "card",
        "gcash": "gcash",
        "paymaya": "paymaya",
        "grab_pay": "grab_pay",
        "dob": "dob",  # Direct Online Banking
        "qrph": "qr_ph",
        "billease": "billease",
    }
    return mapping.get(source_type, source_type)


# CSRF & Auth
@ensure_csrf_cookie
@require_http_methods(["GET"])
def get_csrf_token(request):
    # Return the token in the response body so frontend can read it
    # The cookie is still set by @ensure_csrf_cookie decorator
    csrf_token = request.META.get('CSRF_COOKIE', '')
    if not csrf_token:
        # Generate new token if not exists
        from django.middleware.csrf import get_token
        csrf_token = get_token(request)
    
    return JsonResponse({
        "csrfToken": csrf_token,
        "message": "CSRF cookie and token ready"
    })


@api_view(["GET"])
def test_user(request):
    return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)


# User Management API
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_all_users(request):
    """Get all users for staff management. Only accessible by staff."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    users = User.objects.all().order_by("-date_joined")
    
    # Search functionality
    search_query = request.GET.get('search', '').strip()
    if search_query:
        from django.db.models import Q
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )
    
    serializer = StaffUserSerializer(users, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user(request, user_id):
    """Get a specific user by ID. Only accessible by staff."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        user = User.objects.get(id=user_id)
        serializer = StaffUserSerializer(user)
        return Response(serializer.data)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_user(request, user_id):
    """Update user information. Only accessible by staff."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        user = User.objects.get(id=user_id)
        serializer = StaffUserSerializer(user, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_user(request, user_id):
    """Delete a user. Only accessible by superusers."""
    if not request.user.is_superuser:
        return Response(
            {"error": "Superuser access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        user = User.objects.get(id=user_id)
        # Prevent deleting superusers
        if user.is_superuser:
            return Response(
                {"error": "Cannot delete superuser"}, status=status.HTTP_400_BAD_REQUEST
            )
        user.delete()
        return Response({"message": "User deleted successfully"})
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_staff_permissions(request, user_id):
    """Update staff permissions. Only accessible by superusers."""
    if not request.user.is_superuser:
        return Response(
            {"error": "Superuser access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        user = User.objects.get(id=user_id)
        
        # Only allow updating permissions for staff members (not superusers)
        if not user.is_staff:
            return Response(
                {"error": "User is not a staff member"}, status=status.HTTP_400_BAD_REQUEST
            )
            
        if user.is_superuser:
            return Response(
                {"error": "Cannot modify superuser permissions"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Get or create staff permissions
        permissions, created = StaffPermissions.objects.get_or_create(user=user)
        
        # Update permissions
        serializer = StaffPermissionsSerializer(permissions, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)


# Categories
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_category(request):
    """Create a new product category. Only accessible by staff."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        name = request.data.get('name')
        parent_id = request.data.get('parent')
        is_component = request.data.get('is_component', False)
        
        if not name:
            return Response(
                {"error": "Category name is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create category
        category_data = {
            'name': name,
            'is_component': is_component,
        }
        
        if parent_id:
            try:
                parent = ProductCategory.objects.get(id=parent_id)
                category_data['parent'] = parent
            except ProductCategory.DoesNotExist:
                return Response(
                    {"error": "Parent category not found"}, 
                    status=status.HTTP_404_NOT_FOUND
                )
        
        category = ProductCategory.objects.create(**category_data)
        serializer = ProductCategorySerializer(category)
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response(
            {"error": str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# Brands
@api_view(["GET"])
def get_brands(request):
    brands = Brands.objects.all()
    serializer = BrandsSerializer(brands, many=True)
    return Response(serializer.data)


@api_view(["POST"])
def create_brand(request):
    """Create a new brand"""
    try:
        name = request.data.get("name")

        if not name:
            return Response(
                {"error": "Brand name is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Check if brand already exists
        if Brands.objects.filter(name=name).exists():
            return Response(
                {"error": "Brand with this name already exists"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create the brand
        brand = Brands.objects.create(name=name)
        serializer = BrandsSerializer(brand)

        return Response(serializer.data, status=status.HTTP_201_CREATED)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Categories
@api_view(["GET"])
def get_product_categories(request):
    categories = ProductCategory.objects.all()
    serializer = ProductCategorySerializer(categories, many=True)
    return Response(serializer.data)


# Listings
@api_view(["GET"])
def get_product_listings(request):
    """Get product listings with optional pagination"""
    from django.core.paginator import Paginator, EmptyPage
    
    # Get pagination parameters
    page = request.GET.get('page', None)
    page_size = request.GET.get('page_size', None)
    
    listings = ProductListing.objects.filter(available=True).distinct().order_by('-id')
    
    # If pagination parameters provided, paginate
    if page and page_size:
        try:
            paginator = Paginator(listings, int(page_size))
            page_obj = paginator.get_page(int(page))
            
            serializer = ProductListingSerializer(page_obj.object_list, many=True)
            
            return Response({
                'results': serializer.data,
                'count': paginator.count,
                'total_pages': paginator.num_pages,
                'current_page': page_obj.number,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
            })
        except (EmptyPage, ValueError):
            return Response({
                'results': [],
                'count': 0,
                'total_pages': 0,
                'current_page': 1,
                'has_next': False,
                'has_previous': False,
            })
    
    # If no pagination, return all
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

        # Send realtime cart update
        cart_serializer = CartSerializer(cart)
        send_cart_update(user.id, cart_serializer.data)

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

        # Send realtime cart update
        cart_serializer = CartSerializer(cart)
        send_cart_update(user.id, cart_serializer.data)

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

        # Send realtime cart update
        cart_serializer = CartSerializer(cart)
        send_cart_update(user.id, cart_serializer.data)

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

        # Send realtime cart update
        cart_serializer = CartSerializer(cart)
        send_cart_update(user.id, cart_serializer.data)

        return Response(status=status.HTTP_204_NO_CONTENT)
    except Cart.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
def buy_now_checkout(request):
    """Direct checkout for Buy Now (bypasses cart)."""
    user = request.user
    try:
        product_id = request.data.get("product_id")
        quantity = int(request.data.get("quantity", 1))

        if not product_id:
            return Response(
                {"error": "Product ID is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        product = Product.objects.get(id=product_id)

        # Check stock availability
        if product.stock < quantity:
            return Response(
                {
                    "error": f"Insufficient stock. Available: {product.stock}, Requested: {quantity}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check reservation access
        from .utils import check_reservation_access

        can_purchase, reason = check_reservation_access(product, user)
        if not can_purchase:
            return Response({"error": reason}, status=status.HTTP_400_BAD_REQUEST)

        # Get shipping information from request
        shipping_address = request.data.get("shipping_address", "")
        contact_number = request.data.get("contact_number", "")
        notes = request.data.get("notes", "")
        payment_method = request.data.get("payment_method", "cash_on_delivery")

        # Create order
        order = Order.objects.create(
            user=user,
            shipping_address=shipping_address,
            contact_number=contact_number,
            notes=notes,
            payment_method=payment_method,
        )

        # Create order item
        OrderItem.objects.create(order=order, product=product, quantity=quantity)

        # For COD, deduct inventory immediately
        if payment_method == "cash_on_delivery":
            deduct_inventory_for_order(order)

        # Send realtime updates
        order_serializer = OrderSerializer(order)
        send_order_update(user.id, order_serializer.data)

        # Send notification
        send_notification(
            user.id,
            {
                "type": "order_created",
                "message": f"Order #{order.id} has been created successfully",
                "order_id": order.id,
            },
        )

        return Response(order_serializer.data, status=status.HTTP_201_CREATED)

    except Product.DoesNotExist:
        return Response(
            {"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Checkout error: {str(e)}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
def checkout(request):
    user = request.user
    try:
        cart = Cart.objects.get(user=user)

        # Check stock availability before creating order
        for item in cart.items.all():
            if item.product.stock < item.quantity:
                return Response(
                    {
                        "error": f"Insufficient stock for {item.product.name}. Available: {item.product.stock}, Requested: {item.quantity}"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Get shipping information from request
        shipping_address = request.data.get("shipping_address", "")
        contact_number = request.data.get("contact_number", "")
        notes = request.data.get("notes", "")
        payment_method = request.data.get("payment_method", "cash_on_delivery")

        # Create order with shipping information
        order = Order.objects.create(
            user=user,
            shipping_address=shipping_address,
            contact_number=contact_number,
            notes=notes,
            payment_method=payment_method,
        )

        # Create order items but don't deduct inventory yet
        for item in cart.items.all():
            OrderItem.objects.create(
                order=order, product=item.product, quantity=item.quantity
            )

        # Only clear cart for cash on delivery (immediate payment)
        # For other payment methods, keep cart until payment is confirmed
        if payment_method == "cash_on_delivery":
            cart.delete()
            # Deduct inventory for COD orders
            deduct_inventory_for_order(order)
        else:
            # For digital payments, mark cart as "reserved" for this order
            cart.notes = f"Reserved for Order #{order.id}"
            cart.save()

        # Send realtime updates
        order_serializer = OrderSerializer(order)
        send_order_update(user.id, order_serializer.data)

        # Send notification
        send_notification(
            user.id,
            {
                "type": "order_created",
                "message": f"Order #{order.id} has been created successfully",
                "order_id": order.id,
            },
        )

        serializer = OrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    except Cart.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
def pos_sale(request):
    """Process a POS sale - record directly to Sales without creating an order"""
    user = request.user

    # Check if user is staff
    if not user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        # Get cart items from request
        cart_items = request.data.get("items", [])
        payment_method = request.data.get("payment_method", "cash")
        customer_name = request.data.get("customer_name", "Walk-in Customer")
        customer_contact = request.data.get("customer_contact", "")

        if not cart_items:
            return Response(
                {"error": "No items in cart"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Create a Sales record for this POS transaction
        sale = Sales.objects.create(user=user, payment_method=payment_method)

        # Process sale items
        total_amount = 0
        for item in cart_items:
            try:
                product = Product.objects.get(id=item["product_id"])
                quantity = int(item["quantity"])
                item_amount = float(product.price) * quantity

                # Record sale item with amount
                SalesItem.objects.create(
                    sales=sale,
                    product=product,
                    quantity_sold=quantity,
                    amount=item_amount,
                )

                # Update product stock if available
                if hasattr(product, "stock") and product.stock is not None:
                    product.stock = max(0, product.stock - quantity)
                    product.save()

                total_amount += item_amount

            except Product.DoesNotExist:
                # Delete the sale if a product is not found
                sale.delete()
                return Response(
                    {"error": f'Product with ID {item["product_id"]} not found'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Send notification
        send_notification(
            user.id,
            {
                "type": "pos_sale_completed",
                "message": f"POS Sale #{sale.id} completed - ₱{total_amount:.2f}",
                "sale_id": sale.id,
                "total_amount": total_amount,
            },
        )

        return Response(
            {
                "success": True,
                "sale_id": sale.id,
                "total_amount": total_amount,
                "message": f"Sale completed successfully! Sale #{sale.id}",
            },
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        return Response(
            {"error": f"Failed to process sale: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


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
    # Exclude POS sales from orders list (they're tracked in Sales model)
    orders = Order.objects.exclude(shipping_address__icontains="POS Sale").all()
    serializer = OrderSerializer(orders, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def get_customer_orders(request):
    """Get orders for the authenticated customer"""
    user = request.user

    # Check if user is authenticated
    if not user.is_authenticated:
        return Response(
            {"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED
        )

    # Get orders for this customer only, excluding POS sales
    orders = (
        Order.objects.filter(user=user)
        .exclude(shipping_address__icontains="POS Sale")
        .order_by("-created_at")
    )
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


@api_view(["PATCH"])
def update_order_status(request, order_id):
    """Update order status - staff only, or order owner for specific fields"""
    # For PayMongo checkout session ID, allow order owner
    checkout_session_id = request.data.get("paymongo_checkout_session_id")
    if checkout_session_id:
        try:
            order = Order.objects.get(pk=order_id, user=request.user)
            order.paymongo_checkout_session_id = checkout_session_id
            order.save()
            return Response(
                {"message": "Checkout session ID stored"}, status=status.HTTP_200_OK
            )
        except Order.DoesNotExist:
            return Response(
                {"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND
            )

    # For status updates, require staff access
    if not request.user.is_authenticated or not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        order = Order.objects.get(pk=order_id)
        new_status = request.data.get("status")
        payment_status = request.data.get("payment_status")
        reason = request.data.get("reason", "")

        # Update order status if provided
        if new_status:
            if new_status not in [
                "to_pay",
                "to_ship",
                "to_deliver",
                "completed",
                "cancelled",
                "returned",
            ]:
                return Response(
                    {"error": "Invalid status"}, status=status.HTTP_400_BAD_REQUEST
                )

            was_completed = order.status == "completed"
            order.status = new_status

            # Handle cancellation reason
            if new_status == "cancelled":
                if reason:
                    order.cancel_reason = reason
                else:
                    # Default reason for staff cancellations
                    order.cancel_reason = (
                        f"Order cancelled by staff: {request.user.username}"
                    )

            # Handle return reason
            if new_status == "returned":
                if reason:
                    order.return_reason = reason
                else:
                    # Staff override for returned status
                    order.return_reason = (
                        f"Order status override by staff: {request.user.username}"
                    )
        else:
            was_completed = order.status == "completed"

        # Update payment status if provided
        if payment_status:
            if payment_status not in ["pending", "paid", "failed", "refunded"]:
                return Response(
                    {"error": "Invalid payment status"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            order.payment_status = payment_status

        order.save()

        # If newly completed, record a Sales record and lines
        if new_status == "completed" and not was_completed:
            try:
                # Map order payment method to sales payment method
                sale_payment_method = order.payment_method
                if sale_payment_method == "cash_on_delivery":
                    sale_payment_method = "cash"
                elif sale_payment_method not in [
                    "cash",
                    "card",
                    "gcash",
                    "paymaya",
                    "bank_transfer",
                ]:
                    sale_payment_method = "cash"  # Default to cash for other methods

                sale = Sales.objects.create(
                    user=order.user, payment_method=sale_payment_method
                )
                for item in order.items.select_related("product").all():
                    item_amount = float(item.product.price) * item.quantity
                    SalesItem.objects.create(
                        sales=sale,
                        product=item.product,
                        quantity_sold=item.quantity,
                        amount=item_amount,
                    )
            except Exception as e:
                logger.error(f"Failed to record sale for order {order.id}: {str(e)}")

        # Send realtime updates
        order_serializer = OrderSerializer(order)
        send_order_update(order.user.id, order_serializer.data)

        return Response(order_serializer.data, status=status.HTTP_200_OK)

    except Order.DoesNotExist:
        return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Sales
@api_view(["GET"])
def get_sales(request):
    sales = Sales.objects.prefetch_related(
        "sales_item__product__product_listing", "sales_item__product__brand", "user"
    ).order_by("-sale_date")
    serializer = SalesSerializer(sales, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def get_top_selling_products(request):
    """Get top selling products based on sales data"""
    try:
        from django.db.models import Sum, Count, F, DecimalField
        from django.db.models.functions import Coalesce

        # Aggregate sales by product
        top_products = (
            SalesItem.objects.values(
                "product__id", "product__name", "product__product_listing__name"
            )
            .annotate(
                total_quantity=Sum("quantity_sold"),
                total_revenue=Sum("amount"),
                sales_count=Count("id"),
            )
            .filter(total_quantity__gt=0)  # Only positive sales (exclude pure refunds)
            .order_by("-total_quantity")[:10]  # Top 10
        )

        # Format the response
        result = [
            {
                "product_id": item["product__id"],
                "product_name": item["product__product_listing__name"]
                or item["product__name"]
                or "Unknown Product",
                "quantity_sold": item["total_quantity"],
                "revenue": float(item["total_revenue"]) if item["total_revenue"] else 0,
                "sales_count": item["sales_count"],
            }
            for item in top_products
        ]

        return Response(result, status=status.HTTP_200_OK)
    except Exception as e:
        logger.error(f"Failed to get top selling products: {str(e)}")
        return Response(
            {"error": f"Failed to fetch top selling products: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def create_refund(request):
    """Create a refund by recording negative sale items"""
    user = request.user

    # Check if user is staff
    if not user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        # Get refund data from request
        items = request.data.get("items", [])
        payment_method = request.data.get("payment_method", "cash")
        reason = request.data.get("reason", "")

        if not items:
            return Response(
                {"error": "No items to refund"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Create a Sales record for this refund
        sale = Sales.objects.create(user=user, payment_method=payment_method)

        # Process refund items (negative amounts)
        total_refund = 0
        for item in items:
            try:
                product = Product.objects.get(id=item["product_id"])
                quantity = int(item["quantity"])
                refund_amount = -abs(
                    float(item.get("amount", float(product.price) * quantity))
                )

                # Record refund as negative sale item
                SalesItem.objects.create(
                    sales=sale,
                    product=product,
                    quantity_sold=-abs(quantity),  # Negative quantity for refunds
                    amount=refund_amount,
                )

                # Restore product stock if available
                if hasattr(product, "stock") and product.stock is not None:
                    product.stock += abs(quantity)
                    product.save()

                total_refund += refund_amount

            except Product.DoesNotExist:
                sale.delete()
                return Response(
                    {"error": f'Product with ID {item["product_id"]} not found'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Send notification
        send_notification(
            user.id,
            {
                "type": "refund_processed",
                "message": f"Refund #{sale.id} processed - ₱{abs(total_refund):.2f}",
                "sale_id": sale.id,
                "refund_amount": total_refund,
            },
        )

        return Response(
            {
                "success": True,
                "sale_id": sale.id,
                "refund_amount": total_refund,
                "message": f"Refund processed successfully! Refund #{sale.id}",
            },
            status=status.HTTP_201_CREATED,
        )

    except Exception as e:
        return Response(
            {"error": f"Failed to process refund: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# Repair Queue
@api_view(["GET"])
def get_all_schedule(request):
    queue = (
        ServiceQueue.objects.all().select_related("user").order_by("queue_date", "id")
    )
    serializer = QueueSerializer(queue, many=True)
    return Response(serializer.data)


# Product Listing Management API
@api_view(["GET"])
def get_all_listings(request):
    """Get all product listings for staff management."""
    listings = (
        ProductListing.objects.all()
        .select_related("category", "brand")
        .prefetch_related("products", "compatibility_tags")
    )
    serializer = ProductListingSerializer(listings, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def get_listing(request, listing_id):
    """Get a specific product listing by ID."""
    try:
        listing = ProductListing.objects.get(id=listing_id)
        serializer = ProductListingSerializer(listing)
        return Response(serializer.data)
    except ProductListing.DoesNotExist:
        return Response(
            {"error": "Product listing not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_listing(request):
    """Create a new product listing. Only accessible by staff."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    # Parse JSON arrays from FormData if they exist
    data = request.data.copy()
    if "compatibility_tag_ids" in data and isinstance(
        data["compatibility_tag_ids"], str
    ):
        import json

        data["compatibility_tag_ids"] = json.loads(
            data["compatibility_tag_ids"]
        )

    serializer = ProductListingSerializer(data=data)
    if serializer.is_valid():
        listing = serializer.save()

        # Handle product images
        for key in request.FILES.keys():
            if key.startswith("product_image_"):
                ProductImage.objects.create(
                    product_listing=listing,
                    image=request.FILES[key],
                    alt_text=listing.name or "Product image",
                )

        return Response(
            ProductListingSerializer(listing).data, status=status.HTTP_201_CREATED
        )
    else:
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_listing(request, listing_id):
    """Update a product listing. Only accessible by staff."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        listing = ProductListing.objects.get(id=listing_id)

        # Parse JSON arrays from FormData if they exist
        data = request.data.copy()
        if "compatibility_tag_ids" in data and isinstance(
            data["compatibility_tag_ids"], str
        ):
            import json

            data["compatibility_tag_ids"] = json.loads(
                data["compatibility_tag_ids"]
            )

        serializer = ProductListingSerializer(listing, data=data, partial=True)

        if serializer.is_valid():
            listing = serializer.save()

            # Handle new product images
            for key in request.FILES.keys():
                if key.startswith("product_image_"):
                    ProductImage.objects.create(
                        product_listing=listing,
                        image=request.FILES[key],
                        alt_text=listing.name or "Product image",
                    )

            return Response(ProductListingSerializer(listing).data)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except ProductListing.DoesNotExist:
        return Response(
            {"error": "Product listing not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_listing(request, listing_id):
    """Delete a product listing. Only accessible by staff."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        listing = ProductListing.objects.get(id=listing_id)
        listing.delete()
        return Response({"message": "Product listing deleted successfully"})
    except ProductListing.DoesNotExist:
        return Response(
            {"error": "Product listing not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_listing_image(request, image_id):
    """Delete a product listing image. Only accessible by staff."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        image = ProductImage.objects.get(id=image_id)
        image.delete()
        return Response({"message": "Image deleted successfully"})
    except ProductImage.DoesNotExist:
        return Response({"error": "Image not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_unassigned_products(request):
    """Get all products not assigned to any listing."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    products = Product.objects.filter(product_listing__isnull=True).select_related(
        "brand", "supply"
    )
    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def assign_products_to_listing(request, listing_id):
    """Assign products to a listing."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        listing = ProductListing.objects.get(id=listing_id)
        product_ids = request.data.get("product_ids", [])

        if not product_ids:
            return Response(
                {"error": "No product IDs provided"}, status=status.HTTP_400_BAD_REQUEST
            )

        # Update products to be assigned to this listing
        updated_count = Product.objects.filter(
            id__in=product_ids,
            product_listing__isnull=True,  # Only assign unassigned products
        ).update(product_listing=listing)

        return Response(
            {
                "message": f"Successfully assigned {updated_count} product(s) to listing",
                "assigned_count": updated_count,
            }
        )
    except ProductListing.DoesNotExist:
        return Response(
            {"error": "Listing not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def unassign_products_from_listing(request):
    """Unassign products from their current listing."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    product_ids = request.data.get("product_ids", [])

    if not product_ids:
        return Response(
            {"error": "No product IDs provided"}, status=status.HTTP_400_BAD_REQUEST
        )

    # Remove products from their listings
    updated_count = Product.objects.filter(id__in=product_ids).update(
        product_listing=None
    )

    return Response(
        {
            "message": f"Successfully unassigned {updated_count} product(s)",
            "unassigned_count": updated_count,
        }
    )


# Bike Compatibility Tag Management API
@api_view(["GET"])
def get_compatibility_tags(request):
    """Get all bike compatibility tags, optionally filtered by type."""
    tag_type = request.query_params.get("tag_type")
    
    if tag_type:
        tags = BikeCompatibilityTag.objects.filter(tag_type=tag_type)
    else:
        tags = BikeCompatibilityTag.objects.all()
    
    serializer = BikeCompatibilityTagSerializer(tags, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_compatibility_tag(request):
    """Create a new bike compatibility tag. Staff only."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )
    
    tag_type = request.data.get("tag_type")
    value = request.data.get("value")
    display_name = request.data.get("display_name")
    description = request.data.get("description", "")
    display_order = request.data.get("display_order", 0)
    
    if not tag_type or not value or not display_name:
        return Response(
            {"error": "tag_type, value, and display_name are required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if tag_type not in ["use_case", "budget", "physical"]:
        return Response(
            {"error": "tag_type must be 'use_case', 'budget', or 'physical'"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if tag already exists
    if BikeCompatibilityTag.objects.filter(tag_type=tag_type, value=value).exists():
        return Response(
            {"error": f"Tag with type '{tag_type}' and value '{value}' already exists"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    tag = BikeCompatibilityTag.objects.create(
        tag_type=tag_type,
        value=value,
        display_name=display_name,
        description=description,
        display_order=display_order
    )
    serializer = BikeCompatibilityTagSerializer(tag)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_compatibility_tag(request, tag_id):
    """Update a bike compatibility tag. Staff only."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        tag = BikeCompatibilityTag.objects.get(id=tag_id)
        
        if "tag_type" in request.data:
            if request.data["tag_type"] not in ["use_case", "budget", "physical"]:
                return Response(
                    {"error": "tag_type must be 'use_case', 'budget', or 'physical'"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            tag.tag_type = request.data["tag_type"]
        
        if "value" in request.data:
            tag.value = request.data["value"]
        if "display_name" in request.data:
            tag.display_name = request.data["display_name"]
        if "description" in request.data:
            tag.description = request.data["description"]
        if "display_order" in request.data:
            tag.display_order = request.data["display_order"]
        
        tag.save()
        serializer = BikeCompatibilityTagSerializer(tag)
        return Response(serializer.data)
    except BikeCompatibilityTag.DoesNotExist:
        return Response({"error": "Tag not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_compatibility_tag(request, tag_id):
    """Delete a bike compatibility tag. Staff only."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        tag = BikeCompatibilityTag.objects.get(id=tag_id)
        tag.delete()
        return Response({"message": "Tag deleted successfully"})
    except BikeCompatibilityTag.DoesNotExist:
        return Response({"error": "Tag not found"}, status=status.HTTP_404_NOT_FOUND)


# OLD Compatibility Management API (kept for backward compatibility, will be removed)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_compatibility_group(request):
    """Create a new compatibility group."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    name = request.data.get("name")
    description = request.data.get("description", "")

    if not name:
        return Response(
            {"error": "Group name is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    group = CompatibilityGroup.objects.create(name=name, description=description)
    serializer = CompatibilityGroupSerializer(group)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_compatibility_group(request, group_id):
    """Update a compatibility group."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        group = CompatibilityGroup.objects.get(id=group_id)

        if "name" in request.data:
            group.name = request.data["name"]
        if "description" in request.data:
            group.description = request.data["description"]

        group.save()
        serializer = CompatibilityGroupSerializer(group)
        return Response(serializer.data)
    except CompatibilityGroup.DoesNotExist:
        return Response({"error": "Group not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_compatibility_group(request, group_id):
    """Delete a compatibility group."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        group = CompatibilityGroup.objects.get(id=group_id)
        group.delete()
        return Response({"message": "Group deleted successfully"})
    except CompatibilityGroup.DoesNotExist:
        return Response({"error": "Group not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_compatibility_attribute(request):
    """Create a new compatibility attribute."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    group_id = request.data.get("group_id")
    name = request.data.get("name")

    if not group_id or not name:
        return Response(
            {"error": "Group ID and name are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        group = CompatibilityGroup.objects.get(id=group_id)
        attribute = CompatibilityAttribute.objects.create(group=group, name=name)
        serializer = CompatibilityAttributeSerializer(attribute)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    except CompatibilityGroup.DoesNotExist:
        return Response({"error": "Group not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_compatibility_attribute(request, attribute_id):
    """Update a compatibility attribute."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        attribute = CompatibilityAttribute.objects.get(id=attribute_id)

        if "name" in request.data:
            attribute.name = request.data["name"]
        if "group_id" in request.data:
            group = CompatibilityGroup.objects.get(id=request.data["group_id"])
            attribute.group = group

        attribute.save()
        serializer = CompatibilityAttributeSerializer(attribute)
        return Response(serializer.data)
    except CompatibilityAttribute.DoesNotExist:
        return Response(
            {"error": "Attribute not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except CompatibilityGroup.DoesNotExist:
        return Response({"error": "Group not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_compatibility_attribute(request, attribute_id):
    """Delete a compatibility attribute."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        attribute = CompatibilityAttribute.objects.get(id=attribute_id)
        attribute.delete()
        return Response({"message": "Attribute deleted successfully"})
    except CompatibilityAttribute.DoesNotExist:
        return Response(
            {"error": "Attribute not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_compatibility_value(request):
    """Create a new compatibility attribute value."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    attribute_id = request.data.get("attribute_id")
    value = request.data.get("value")
    display_name = request.data.get("display_name")

    if not attribute_id or not value or not display_name:
        return Response(
            {"error": "Attribute ID, value, and display name are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        attribute = CompatibilityAttribute.objects.get(id=attribute_id)
        attr_value = CompatibilityAttributeValue.objects.create(
            attribute=attribute, value=value, display_name=display_name
        )
        serializer = CompatibilityAttributeValueSerializer(attr_value)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    except CompatibilityAttribute.DoesNotExist:
        return Response(
            {"error": "Attribute not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_compatibility_value(request, value_id):
    """Update a compatibility attribute value."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        attr_value = CompatibilityAttributeValue.objects.get(id=value_id)

        if "value" in request.data:
            attr_value.value = request.data["value"]
        if "display_name" in request.data:
            attr_value.display_name = request.data["display_name"]
        if "attribute_id" in request.data:
            attribute = CompatibilityAttribute.objects.get(
                id=request.data["attribute_id"]
            )
            attr_value.attribute = attribute

        attr_value.save()
        serializer = CompatibilityAttributeValueSerializer(attr_value)
        return Response(serializer.data)
    except CompatibilityAttributeValue.DoesNotExist:
        return Response({"error": "Value not found"}, status=status.HTTP_404_NOT_FOUND)
    except CompatibilityAttribute.DoesNotExist:
        return Response(
            {"error": "Attribute not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_compatibility_value(request, value_id):
    """Delete a compatibility attribute value."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        attr_value = CompatibilityAttributeValue.objects.get(id=value_id)
        attr_value.delete()
        return Response({"message": "Value deleted successfully"})
    except CompatibilityAttributeValue.DoesNotExist:
        return Response({"error": "Value not found"}, status=status.HTTP_404_NOT_FOUND)


# Product Reservation API
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_reservation(request):
    """Create a reservation for an out-of-stock product."""
    try:
        product_id = request.data.get("product_id")

        if not product_id:
            return Response(
                {"error": "Product ID is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        product = Product.objects.get(id=product_id)

        # Check if user already has an active/waiting reservation for this product
        existing = ReservedProduct.objects.filter(
            product=product, user=request.user, status__in=["waiting", "active"]
        ).first()

        if existing:
            return Response(
                {
                    "error": "You already have a reservation for this product",
                    "reservation": ReservedProductSerializer(existing).data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Delete any old expired/fulfilled/cancelled reservations for this product by this user
        # This allows users to reserve again after their previous reservation ended
        ReservedProduct.objects.filter(
            product=product,
            user=request.user,
            status__in=["expired", "fulfilled", "cancelled"],
        ).delete()

        # Get the next queue position
        max_position = (
            ReservedProduct.objects.filter(
                product=product, status__in=["waiting", "active"]
            ).aggregate(models.Max("queue_position"))["queue_position__max"]
            or 0
        )

        # Create reservation
        reservation = ReservedProduct.objects.create(
            product=product,
            user=request.user,
            queue_position=max_position + 1,
            status="waiting",
        )

        # If product is in stock, activate the first reservation
        if product.stock > 0:
            from .utils import process_product_reservations

            process_product_reservations(product)
            reservation.refresh_from_db()

        serializer = ReservedProductSerializer(reservation)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    except Product.DoesNotExist:
        return Response(
            {"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Failed to create reservation: {str(e)}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user_reservations(request):
    """Get all reservations for the current user."""
    reservations = (
        ReservedProduct.objects.filter(user=request.user)
        .select_related("product", "product__brand", "product__product_listing")
        .order_by("status", "queue_position")
    )

    serializer = ReservedProductSerializer(reservations, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_reservation(request, reservation_id):
    """Cancel a reservation."""
    try:
        reservation = ReservedProduct.objects.get(id=reservation_id, user=request.user)

        if reservation.status in ["fulfilled", "cancelled"]:
            return Response(
                {"error": "Cannot cancel this reservation"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        product = reservation.product
        reservation.cancel_reservation()

        # Reprocess queue to move everyone up and activate next person if needed
        from .utils import process_product_reservations

        process_product_reservations(product)

        return Response({"message": "Reservation cancelled successfully"})

    except ReservedProduct.DoesNotExist:
        return Response(
            {"error": "Reservation not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["GET"])
def check_product_reservation(request, product_id):
    """Check if a product has reservations and if current user is in queue."""
    try:
        product = Product.objects.get(id=product_id)

        # Get all active/waiting reservations for this product
        reservations = ReservedProduct.objects.filter(
            product=product, status__in=["waiting", "active"]
        ).order_by("queue_position")

        user_reservation = None
        if request.user.is_authenticated:
            user_reservation = reservations.filter(user=request.user).first()

        data = {
            "has_reservations": reservations.exists(),
            "total_in_queue": reservations.count(),
            "user_reservation": ReservedProductSerializer(user_reservation).data
            if user_reservation
            else None,
            "product_available": product.stock > 0
            and (
                # Product is available if no active reservations OR user has active reservation
                not reservations.filter(status="active").exists()
                or (user_reservation and user_reservation.status == "active")
            ),
        }

        return Response(data)

    except Product.DoesNotExist:
        return Response(
            {"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_all_reservations(request):
    """Get all reservations (staff only)."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    reservations = (
        ReservedProduct.objects.all()
        .select_related("product", "product__brand", "product__product_listing", "user")
        .order_by("product", "queue_position")
    )

    serializer = ReservedProductSerializer(reservations, many=True)
    return Response(serializer.data)


# Supplier Management API
@api_view(["GET"])
def get_all_suppliers(request):
    """Get all suppliers with their product counts and low stock alerts."""
    suppliers = ProductSupplier.objects.all().prefetch_related("supplier")

    supplier_data = []
    for supplier in suppliers:
        # Get products from this supplier
        products = Product.objects.filter(supply=supplier)

        # Count low stock items (assuming threshold is 10)
        low_stock_count = products.filter(stock__lt=10).count()
        total_products = products.count()

        # Calculate total stock value
        total_stock_value = sum(product.stock * product.price for product in products)

        supplier_data.append(
            {
                "id": supplier.id,
                "name": supplier.name,
                "contact": supplier.contact,
                "total_products": total_products,
                "low_stock_count": low_stock_count,
                "total_stock_value": total_stock_value,
                "has_low_stock": low_stock_count > 0,
            }
        )

    return Response(supplier_data)


@api_view(["POST"])
def create_supplier(request):
    """Create a new supplier."""
    try:
        data = request.data
        name = data.get("name", "").strip()
        contact = data.get("contact", "").strip()

        if not name:
            return Response(
                {"error": "Supplier name is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if supplier with same name already exists
        if ProductSupplier.objects.filter(name__iexact=name).exists():
            return Response(
                {"error": "Supplier with this name already exists"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        supplier = ProductSupplier.objects.create(
            name=name, contact=contact if contact else None
        )

        # Return the created supplier data
        supplier_data = {
            "id": supplier.id,
            "name": supplier.name,
            "contact": supplier.contact,
            "total_products": 0,
            "low_stock_count": 0,
            "total_stock_value": 0,
            "has_low_stock": False,
        }

        return Response(supplier_data, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response(
            {"error": f"Failed to create supplier: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["PUT"])
def update_supplier(request, supplier_id):
    """Update an existing supplier."""
    try:
        data = request.data
        name = data.get("name", "").strip()
        contact = data.get("contact", "").strip()

        if not name:
            return Response(
                {"error": "Supplier name is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            supplier = ProductSupplier.objects.get(id=supplier_id)
        except ProductSupplier.DoesNotExist:
            return Response(
                {"error": "Supplier not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Check if another supplier with same name already exists
        existing_supplier = (
            ProductSupplier.objects.filter(name__iexact=name)
            .exclude(id=supplier_id)
            .first()
        )
        if existing_supplier:
            return Response(
                {"error": "Another supplier with this name already exists"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update the supplier
        supplier.name = name
        supplier.contact = contact if contact else None
        supplier.save()

        # Calculate updated stats
        products = Product.objects.filter(supply=supplier)
        total_products = products.count()
        low_stock_count = products.filter(stock__lt=10).count()
        total_stock_value = sum(p.price * p.stock for p in products)

        # Return the updated supplier data
        supplier_data = {
            "id": supplier.id,
            "name": supplier.name,
            "contact": supplier.contact,
            "total_products": total_products,
            "low_stock_count": low_stock_count,
            "total_stock_value": total_stock_value,
            "has_low_stock": low_stock_count > 0,
        }

        return Response(supplier_data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Failed to update supplier: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["DELETE"])
def delete_supplier(request, supplier_id):
    """Delete a supplier."""
    try:
        try:
            supplier = ProductSupplier.objects.get(id=supplier_id)
        except ProductSupplier.DoesNotExist:
            return Response(
                {"error": "Supplier not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Check if supplier has products
        products_count = Product.objects.filter(supply=supplier).count()
        if products_count > 0:
            return Response(
                {
                    "error": f"Cannot delete supplier. {products_count} product(s) are still associated with this supplier."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        supplier_name = supplier.name
        supplier.delete()

        return Response(
            {"message": f"Supplier '{supplier_name}' has been deleted successfully"},
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"error": f"Failed to delete supplier: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_supplier_products(request, supplier_id):
    """Get all products from a specific supplier with low stock alerts."""
    try:
        supplier = ProductSupplier.objects.get(id=supplier_id)
        products = Product.objects.filter(supply=supplier).select_related(
            "brand", "product_listing"
        )

        product_data = []
        for product in products:
            is_low_stock = product.stock < 10  # Assuming threshold is 10

            product_data.append(
                {
                    "id": product.id,
                    "name": product.name,
                    "variant_attribute": product.variant_attribute,
                    "brand": product.brand.name if product.brand else "No Brand",
                    "sku": product.sku,
                    "price": product.price,
                    "stock": product.stock,
                    "available": product.available,
                    "is_low_stock": is_low_stock,
                    "product_listing": {
                        "id": product.product_listing.id
                        if product.product_listing
                        else None,
                        "name": product.product_listing.name
                        if product.product_listing
                        else "No Listing",
                        "slug": product.product_listing.slug
                        if product.product_listing
                        else None,
                    }
                    if product.product_listing
                    else None,
                }
            )

        return Response(
            {
                "supplier": {
                    "id": supplier.id,
                    "name": supplier.name,
                    "contact": supplier.contact,
                },
                "products": product_data,
            }
        )
    except ProductSupplier.DoesNotExist:
        return Response(
            {"error": "Supplier not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_queue_item(request, item_id):
    """Update a service queue item status. Only accessible by staff."""
    if not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        queue_item = ServiceQueue.objects.get(id=item_id)
        serializer = QueueSerializer(queue_item, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except ServiceQueue.DoesNotExist:
        return Response(
            {"error": "Queue item not found"}, status=status.HTTP_404_NOT_FOUND
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_pending_services(request):
    """Check if the authenticated user has any pending services."""
    pending_services = ServiceQueue.objects.filter(
        user=request.user, status="pending"
    ).exists()

    return Response({"has_pending_services": pending_services})


@api_view(["GET"])
def get_queue_count(request):
    """Get the number of pending queue items for a specific date."""
    queue_date = request.GET.get("queue_date")
    if not queue_date:
        return Response(
            {"error": "queue_date parameter is required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        from datetime import datetime
        date_obj = datetime.strptime(queue_date, "%Y-%m-%d").date()
    except ValueError:
        return Response(
            {"error": "Invalid date format. Use YYYY-MM-DD"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Count pending items for this date
    count = ServiceQueue.objects.filter(
        queue_date=date_obj,
        status="pending"
    ).count()
    
    return Response({
        "queue_date": queue_date,
        "count": count,
        "max_customer_limit": 10,
        "is_full": count >= 10
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def schedule_service(request):
    # Support both customer self-service and staff adding for customer
    user_id = request.data.get("user")  # Staff can specify customer ID
    is_staff_request = bool(user_id and user_id != request.user.id)
    
    if not user_id:
        user_id = request.user.id  # Default to current user (customer self-service)
    
    print(f"DEBUG schedule_service: Received user_id={user_id}, is_staff={is_staff_request}")
    print(f"DEBUG schedule_service: Request data={request.data}")
    
    queue_date_str = request.data.get("queue_date")
    if not queue_date_str:
        return Response(
            {"error": "queue_date is required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check queue limit for customers (not for staff)
    if not is_staff_request:
        from datetime import datetime
        try:
            queue_date_obj = datetime.strptime(queue_date_str, "%Y-%m-%d").date()
            current_count = ServiceQueue.objects.filter(
                queue_date=queue_date_obj,
                status="pending"
            ).count()
            
            if current_count >= 10:
                return Response(
                    {
                        "error": f"This date is fully booked (10 customers). Please choose another date or contact staff for assistance.",
                        "queue_count": current_count,
                        "max_limit": 10
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    data = {
        "queue_date": queue_date_str,
        "info": request.data.get("info"),
        "status": "pending",
        "user_id": user_id,  # Use user_id for the serializer
    }

    serializer = QueueSerializer(data=data)
    if serializer.is_valid():
        queue_item = serializer.save()
        print(f"DEBUG schedule_service: Created queue item {queue_item.id} for user {queue_item.user_id}")
        
        # Re-fetch with user relation to ensure user data is included
        queue_item = ServiceQueue.objects.select_related('user').get(id=queue_item.id)
        serializer = QueueSerializer(queue_item)
        
        print(f"DEBUG schedule_service: Serialized data has user={serializer.data.get('user')}")
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    else:
        print(f"DEBUG schedule_service: Validation errors={serializer.errors}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Inventory Management API
@api_view(["GET"])
def get_inventory(request):
    """Get all products for inventory management."""
    products = Product.objects.all().select_related("brand", "product_listing")
    serializer = ProductSerializer(products, many=True)
    return Response(serializer.data)


@api_view(["GET"])
def get_inventory_item(request, product_id):
    """Get a specific product for inventory management."""
    try:
        product = Product.objects.get(pk=product_id)
        serializer = ProductSerializer(product)
        return Response(serializer.data)
    except Product.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(["PUT"])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def update_inventory_item(request, product_id):
    """Update product inventory (stock, price, availability)."""
    try:
        product = Product.objects.get(pk=product_id)
        old_stock = product.stock

        # Update fields if provided
        if "stock" in request.data:
            product.stock = int(request.data["stock"])
        if "price" in request.data:
            product.price = request.data["price"]
        if "available" in request.data:
            # Convert string to boolean (FormData sends '1' or '0')
            available_value = request.data["available"]
            if isinstance(available_value, str):
                product.available = available_value in ["1", "true", "True"]
            else:
                product.available = bool(available_value)
        if "name" in request.data:
            product.name = request.data["name"]
        if "sku" in request.data:
            product.sku = request.data["sku"]
        if "variant_attribute" in request.data:
            product.variant_attribute = request.data["variant_attribute"]
        if "brand" in request.data:
            brand_id = request.data["brand"]
            # Handle potential list values from FormData
            if isinstance(brand_id, list):
                brand_id = brand_id[0] if brand_id else None
            if brand_id:
                try:
                    brand = Brands.objects.get(pk=brand_id)
                    product.brand = brand
                except Brands.DoesNotExist:
                    pass
        if "supplier_id" in request.data:
            supplier_id = request.data["supplier_id"]
            # Handle potential list values from FormData
            if isinstance(supplier_id, list):
                supplier_id = supplier_id[0] if supplier_id else None
            if supplier_id:
                try:
                    supplier = ProductSupplier.objects.get(pk=supplier_id)
                    product.supply = supplier
                except ProductSupplier.DoesNotExist:
                    pass
            else:
                product.supply = None

        product.save()

        # Handle images from request.FILES
        for key in list(request.FILES.keys()):
            if key.startswith("image_"):
                image_file = request.FILES[key]
                ProductVariantImage.objects.create(
                    product=product,
                    image=image_file,
                    alt_text=product.name or "Product image",
                )

        # If stock was increased, process reservations
        if product.stock > old_stock:
            from .utils import process_product_reservations

            process_product_reservations(product)

        # Send realtime inventory update
        serializer = ProductSerializer(product)
        send_inventory_update(serializer.data)

        return Response(serializer.data, status=status.HTTP_200_OK)
    except Product.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def create_inventory_item(request):
    """Create a new product in inventory."""
    try:
        # Log the incoming data
        logger.info(f"Creating inventory item with data: {request.data}")

        # Extract brand and supplier_id to handle separately
        data = request.data.copy()
        brand_id = data.pop("brand", None)
        supplier_id = data.pop("supplier_id", None)

        # Handle potential list values from FormData
        if isinstance(brand_id, list):
            brand_id = brand_id[0] if brand_id else None
        if isinstance(supplier_id, list):
            supplier_id = supplier_id[0] if supplier_id else None

        # Extract images from request.FILES
        images = []
        for key in list(request.FILES.keys()):
            if key.startswith("image_"):
                images.append(request.FILES[key])

        serializer = ProductSerializer(data=data)
        if serializer.is_valid():
            product = serializer.save()

            # Set brand if provided
            if brand_id:
                try:
                    brand = Brands.objects.get(pk=brand_id)
                    product.brand = brand
                except Brands.DoesNotExist:
                    pass

            # Set supplier if provided
            if supplier_id:
                try:
                    supplier = ProductSupplier.objects.get(pk=supplier_id)
                    product.supply = supplier
                except ProductSupplier.DoesNotExist:
                    pass

            product.save()

            # Create product images
            for image_file in images:
                ProductVariantImage.objects.create(
                    product=product,
                    image=image_file,
                    alt_text=product.name or "Product image",
                )

            # Send realtime inventory update with refreshed data
            updated_serializer = ProductSerializer(product)
            send_inventory_update(updated_serializer.data)

            return Response(updated_serializer.data, status=status.HTTP_201_CREATED)
        else:
            logger.error(f"Serializer validation failed: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Failed to create inventory item: {str(e)}")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_product_image(request, image_id):
    """Delete a product variant image."""
    try:
        image = ProductVariantImage.objects.get(pk=image_id)
        product = image.product
        image.delete()

        # Send realtime inventory update
        if product:
            serializer = ProductSerializer(product)
            send_inventory_update(serializer.data)

        return Response(
            {"message": "Image deleted successfully"}, status=status.HTTP_200_OK
        )
    except ProductVariantImage.DoesNotExist:
        return Response({"error": "Image not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def delete_inventory_item(request, product_id):
    """Delete a product from inventory."""
    try:
        product = Product.objects.get(pk=product_id)
        product_data = ProductSerializer(product).data
        product.delete()

        # Send realtime inventory update with deleted item info
        send_inventory_update(
            {"action": "deleted", "product_id": product_id, "data": product_data}
        )

        return Response(status=status.HTTP_204_NO_CONTENT)
    except Product.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def bulk_update_inventory(request):
    """Bulk update multiple inventory items."""
    updates = request.data.get("updates", [])
    updated_products = []

    for update in updates:
        try:
            product = Product.objects.get(pk=update["id"])

            if "stock" in update:
                product.stock = update["stock"]
            if "price" in update:
                product.price = update["price"]
            if "available" in update:
                product.available = update["available"]

            product.save()
            updated_products.append(ProductSerializer(product).data)
        except Product.DoesNotExist:
            continue

    # Send realtime inventory update for all changes
    send_inventory_update({"action": "bulk_update", "data": updated_products})

    return Response({"updated_count": len(updated_products)}, status=status.HTTP_200_OK)


@api_view(["POST"])
def test_inventory_update(request):
    """Test endpoint to manually trigger inventory WebSocket update."""
    test_data = {
        "id": 999,
        "name": "Test Product",
        "variant_attribute": "Test Variant",
        "brand": "Test Brand",
        "price": 100.00,
        "stock": 5,
        "sku": "TEST123",
        "available": True,
    }

    print(f"DEBUG: Test endpoint called, sending inventory update")
    send_inventory_update(test_data)

    return Response({"message": "Test inventory update sent", "data": test_data})


@api_view(["GET"])
def dashboard_data(request):
    """Get dashboard data for staff users"""
    if not request.user.is_authenticated or not request.user.is_staff:
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        from datetime import date, timedelta

        # Get today's date
        today = date.today()

        # Get real data from models
        dashboard_data = {
            "new_chats": 5,  # Mock data for now - would query unread chat messages
            "new_orders": Order.objects.filter(status="pending").count(),
            "service_queue_today": {
                "pending": ServiceQueue.objects.filter(
                    queue_date=today, status="pending"
                ).count(),
                "completed": ServiceQueue.objects.filter(
                    queue_date=today, status="completed"
                ).count(),
            },
        }

        return Response(dashboard_data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Note: Checkout session creation is now handled directly in the frontend
# The frontend calls PayMongo API directly for better performance and reduced backend complexity


@api_view(["GET"])
def confirm_payment(request, order_id):
    """
    Get payment status for an order - Read-only endpoint
    Note: Webhook handles actual payment processing (cart clearing, inventory, status updates)
    This endpoint just returns the current order status
    """
    if not request.user.is_authenticated:
        return Response(
            {"error": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED
        )

    try:
        logger.info(f"=== GET PAYMENT STATUS ===")
        logger.info(f"Order ID: {order_id}")
        logger.info(f"User: {request.user.username}")

        # Get the order - just return current status
        try:
            order = Order.objects.get(id=order_id, user=request.user)
            logger.info(
                f"Order found: ID={order.id}, Status={order.status}, Payment Status={order.payment_status}"
            )
        except Order.DoesNotExist:
            logger.error(f"Order {order_id} not found for user {request.user.username}")
            return Response(
                {"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND
            )

        # Serialize and return order data
        order_serializer = OrderSerializer(order)

        return Response(
            {
                "order": order_serializer.data,
                "payment_status": order.payment_status,
                "status": order.status,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error(f"Error getting payment status: {str(e)}")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_order(request, order_id):
    """Cancel an order - customer only, for to_pay and to_ship orders"""
    try:
        order = Order.objects.get(pk=order_id, user=request.user)

        # Only allow cancellation for to_pay and to_ship orders
        if order.status not in ["to_pay", "to_ship"]:
            return Response(
                {
                    "error": 'Order cannot be cancelled. Only orders with status "To Pay" or "To Ship" can be cancelled.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update order status to cancelled
        order.status = "cancelled"
        order.save()

        # If order was paid, we might want to handle refunds here
        # For now, we'll just mark it as cancelled

        # Send realtime update
        order_serializer = OrderSerializer(order)
        send_order_update(request.user.id, order_serializer.data)

        return Response(
            {"message": "Order cancelled successfully", "order": order_serializer.data}
        )

    except Order.DoesNotExist:
        return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Error cancelling order {order_id}: {str(e)}")
        return Response(
            {"error": "Failed to cancel order"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def user_info(request):
    """Get current user information including user_info details"""
    try:
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def update_user_profile(request):
    """Update current user's profile information"""
    try:
        user = request.user
        
        # Update user's basic info
        if 'first_name' in request.data:
            user.first_name = request.data['first_name']
        if 'last_name' in request.data:
            user.last_name = request.data['last_name']
        user.save()
        
        # Get or create user profile
        user_profile, created = UserProfile.objects.get_or_create(user=user)
        
        # Update profile fields
        if 'contact_number' in request.data:
            # Validate phone number format
            phone = request.data['contact_number']
            if phone:
                # Remove spaces and dashes
                clean_phone = phone.replace(' ', '').replace('-', '')
                # Validate format: 11 digits starting with 09
                import re
                if not re.match(r'^09\d{9}$', clean_phone):
                    return Response(
                        {"error": "Phone must be 11 digits starting with 09"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                user_profile.contact_number = clean_phone
            else:
                user_profile.contact_number = ''
                
        if 'address' in request.data:
            user_profile.address = request.data['address']
            
        # Handle image upload
        if 'image' in request.FILES:
            user_profile.image = request.FILES['image']
            
        user_profile.save()
        
        # Return updated user data
        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response(
            {"error": str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_chat_rooms(request):
    """Get all active chat rooms for staff."""
    print(f"\n{'='*80}")
    print(f"GET CHAT ROOMS REQUEST")
    print(f"User: {request.user.username}")
    print(f"Is Staff: {request.user.is_staff}")
    print(f"{'='*80}\n")

    if not request.user.is_staff:
        print("ERROR: User is not staff, returning 403")
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    try:
        from django.db.models import Prefetch, Q
        from datetime import timedelta

        # Get all active chat rooms (remove 24 hour filter for now to show all rooms)
        chat_rooms = (
            ChatRoom.objects.filter(is_active=True)
            .select_related("owner")
            .prefetch_related("chat_items")
            .annotate(
                message_count=Count("chat_items"),
                last_message_time=Max("chat_items__sent_at"),
            )
            .distinct()
            .order_by("-last_message_time")
        )

        print(f"Query executed. Found {chat_rooms.count()} active chat rooms")
        logger.info(f"Found {chat_rooms.count()} active chat rooms")

        # Format the response
        chat_rooms_data = []
        for room in chat_rooms:
            print(
                f"Processing room ID={room.id}, owner={room.owner.username}, is_active={room.is_active}"
            )
            logger.info(f"Processing room {room.id} for owner {room.owner.username}")

            # Get the most recent message
            latest_message = room.chat_items.order_by("-sent_at").first()
            print(
                f"  Latest message: {latest_message.message if latest_message else 'None'}"
            )

            # Get customer info
            customer_name = room.owner.get_full_name() or room.owner.username
            # Default avatar (None - frontend will use placeholder)
            customer_avatar = None

            # Get avatar if user has profile image
            if hasattr(room.owner, "user_info") and room.owner.user_info.exists():
                user_profile = room.owner.user_info.first()
                if user_profile and user_profile.image:
                    customer_avatar = user_profile.image.url

            # Format timestamp for display
            formatted_timestamp = ""
            if latest_message:
                formatted_timestamp = latest_message.sent_at.strftime("%I:%M %p")

            # Compute unread customer messages for staff
            unread_count = (
                room.chat_items.filter(
                    message_type="customer",
                ).count()
                if not room.is_read_staff
                else 0
            )

            # Generate room_id in format expected by frontend (customer_{user_id})
            room_id = f"customer_{room.owner.id}"

            room_data = {
                "id": room_id,  # Use string format for frontend
                "customer_id": room.owner.id,
                "customer_name": customer_name,
                "customer_avatar": customer_avatar,
                "last_message": latest_message.message
                if latest_message
                else "No messages yet",
                "formatted_timestamp": formatted_timestamp,
                "timestamp": latest_message.sent_at.strftime("%I:%M %p")
                if latest_message
                else "",
                "message_count": room.message_count,
                "unread_count": unread_count,
                "is_online": True,  # Assume online if there's recent activity
                "is_read_staff": room.is_read_staff,
                "is_read_customer": room.is_read_customer,
            }
            chat_rooms_data.append(room_data)
            print(
                f"  Added room data: id={room_data['id']}, customer={room_data['customer_name']}"
            )
            logger.info(f"Added room data: {room_data}")

        print(f"\nReturning {len(chat_rooms_data)} chat rooms")
        print(
            f"Response: {{'success': True, 'chat_rooms': {len(chat_rooms_data)} rooms}}"
        )
        print(f"{'='*80}\n")

        logger.info(f"Returning {len(chat_rooms_data)} chat rooms")
        return Response({"success": True, "chat_rooms": chat_rooms_data})

    except Exception as e:
        print(f"\nERROR in get_chat_rooms: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        print(f"{'='*80}\n")

        logger.error(f"Error fetching chat rooms: {str(e)}")
        return Response(
            {"error": f"Failed to fetch chat rooms: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@csrf_exempt
@api_view(["POST"])
def paymongo_webhook(request):
    """Handle PayMongo webhooks"""
    try:
        # Print webhook received
        print("\n" + "=" * 80)
        print("🔔 PAYMONGO WEBHOOK RECEIVED")
        print("=" * 80)
        print(f"📅 Timestamp: {timezone.now()}")
        print(f"🌐 Remote Address: {request.META.get('REMOTE_ADDR', 'Unknown')}")
        print(f"📋 Headers:")
        for header, value in request.headers.items():
            if header.lower() in ["content-type", "user-agent", "paymongo-signature"]:
                print(f"   {header}: {value}")
        print("\n📦 Raw Request Body:")
        print(request.body.decode("utf-8") if request.body else "Empty body")
        print("\n" + "-" * 80)

        # Get webhook data
        webhook_data = request.data.get("data", {})
        attributes = webhook_data.get("attributes", {})
        event_type = attributes.get("type")  # Note: event type is in attributes.type

        print(f"📌 Event Type: {event_type}")
        print(f"📊 Webhook Data: {webhook_data}")
        print(f"🔍 Attributes: {attributes}")
        print("-" * 80 + "\n")

        # Handle checkout session payment events
        if event_type == "checkout_session.payment.paid":
            # Handle successful checkout session payment
            checkout_data = attributes.get("data", {})
            checkout_attributes = checkout_data.get("attributes", {})
            metadata = checkout_attributes.get("metadata", {})
            payments = checkout_attributes.get("payments", [])

            order_id = metadata.get("order_id")
            print(f"🔍 Order ID from metadata: {order_id}")
            print(f"💳 Payments array: {payments}")

            # Check payment status from the payments array
            payment_status = None
            payment_source_type = None
            payment_id = None
            if payments and len(payments) > 0:
                # Extract payment ID directly from webhook data
                payment_id = payments[0].get("id")
                payment_attrs = payments[0].get("attributes", {})
                payment_status = payment_attrs.get("status")
                # Extract payment source type
                source = payment_attrs.get("source", {})
                payment_source_type = source.get("type")
                print(f"💰 Payment Status: {payment_status}")
                print(f"💳 Payment Source Type: {payment_source_type}")
                print(f"🔑 Payment ID from webhook: {payment_id}")

            if order_id and payment_status == "paid":
                try:
                    order = Order.objects.get(id=order_id)
                    print(
                        f"📦 Order found: {order.id} - Current status: {order.status}, Payment status: {order.payment_status}"
                    )
                    print(f"🔑 Checkout Session ID: {order.paymongo_checkout_session_id}")
                    print(f"💳 Current Payment ID: {order.paymongo_payment_id}")

                    # Update order payment method based on actual payment source
                    if payment_source_type:
                        mapped_payment_method = map_paymongo_source_to_payment_method(
                            payment_source_type
                        )
                        order.payment_method = mapped_payment_method
                        print(
                            f"💳 Payment method updated to: {mapped_payment_method} (from source: {payment_source_type})"
                        )

                    # Update order to paid and to_ship
                    order.payment_status = "paid"
                    order.paid_at = timezone.now()
                    if order.status == "to_pay":
                        order.status = "to_ship"
                    
                    # Set payment ID from webhook data (already extracted above)
                    if payment_id:
                        order.paymongo_payment_id = payment_id
                        print(f"✅ Payment ID set from webhook data: {payment_id}")

                    # Also try to fetch full checkout session data as backup
                    if order.paymongo_checkout_session_id and not payment_id:
                        try:
                            import requests
                            from django.conf import settings

                            paymongo_secret = settings.PAYMONGO_SECRET_KEY
                            if paymongo_secret:
                                checkout_session_url = f"https://api.paymongo.com/v1/checkout_sessions/{order.paymongo_checkout_session_id}"

                                print(
                                    f"🔍 Fetching checkout session from: {checkout_session_url}"
                                )

                                # Encode secret key as base64 for Basic auth
                                import base64
                                auth_string = f"{paymongo_secret}:"
                                encoded_auth = base64.b64encode(auth_string.encode()).decode()

                                response = requests.get(
                                    checkout_session_url,
                                    headers={
                                        "accept": "application/json",
                                        "authorization": f"Basic {encoded_auth}"
                                    }
                                )

                                print(f"📡 Response Status: {response.status_code}")

                                if response.status_code == 200:
                                    session_data = response.json()
                                    print(f"📦 Session data keys: {session_data.keys()}")
                                    
                                    session_payments = (
                                        session_data.get("data", {})
                                        .get("attributes", {})
                                        .get("payments", [])
                                    )

                                    print(f"💰 Found {len(session_payments)} payment(s) in session")

                                    if session_payments and len(session_payments) > 0:
                                        payment_id = session_payments[0].get("id")
                                        print(f"🔍 Payment ID from session: {payment_id}")
                                        
                                        if payment_id:
                                            order.paymongo_payment_id = payment_id
                                            print(
                                                f"✅ Payment ID set on order object: {payment_id}"
                                            )
                                        else:
                                            print(
                                                f"⚠️ No payment ID found in checkout session"
                                            )
                                    else:
                                        print(
                                            f"⚠️ No payments found in checkout session"
                                        )
                                        print(f"Session attributes keys: {session_data.get('data', {}).get('attributes', {}).keys()}")
                                else:
                                    print(
                                        f"⚠️ Failed to fetch checkout session: {response.status_code}"
                                    )
                                    print(f"Response body: {response.text}")
                            else:
                                print(
                                    f"⚠️ PAYMONGO_SECRET_KEY not configured, skipping payment ID fetch"
                                )
                        except Exception as e:
                            print(f"⚠️ Error fetching checkout session: {str(e)}")
                            import traceback
                            traceback.print_exc()
                            # Don't fail the webhook if we can't fetch payment ID

                    # Save all changes
                    order.save()

                    # Refresh from database to confirm it was saved
                    order.refresh_from_db()
                    
                    print("\n" + "=" * 80)
                    print("💾 ORDER SAVED - FINAL STATE:")
                    print("=" * 80)
                    print(f"Order ID: {order.id}")
                    print(f"Status: {order.status}")
                    print(f"Payment Status: {order.payment_status}")
                    print(f"Checkout Session ID: {order.paymongo_checkout_session_id}")
                    print(f"⭐ PAYMENT ID: {order.paymongo_payment_id}")
                    print("=" * 80 + "\n")

                    # Deduct inventory and clear cart
                    deduct_inventory_for_order(order)
                    clear_reserved_cart(order.user.id, order.id)

                    print(f"🗑️ Cart cleared for user {order.user.id}")

                    # Send realtime updates
                    order_serializer = OrderSerializer(order)
                    send_order_update(order.user.id, order_serializer.data)

                    # Send realtime cart update (empty cart)
                    try:
                        cart = Cart.objects.get(user=order.user)
                        cart_serializer = CartSerializer(cart)
                        send_cart_update(order.user.id, cart_serializer.data)
                    except Cart.DoesNotExist:
                        # Cart already deleted, send empty cart
                        send_cart_update(order.user.id, {"items": [], "total": 0})

                    # Send notification
                    send_notification(
                        order.user.id,
                        {
                            "type": "payment_success",
                            "message": f"Payment for Order #{order.id} has been confirmed",
                            "order_id": order.id,
                        },
                    )

                    print(
                        f"✅ Payment successful webhook processed for order {order.id}"
                    )

                except Order.DoesNotExist:
                    logger.error(f"Order {order_id} not found for webhook")
                    print(f"❌ ERROR: Order {order_id} not found for webhook")

        elif event_type == "checkout_session.payment.failed":
            # Handle failed checkout session payment
            checkout_data = attributes.get("data", {})
            checkout_attributes = checkout_data.get("attributes", {})
            metadata = checkout_attributes.get("metadata", {})
            order_id = metadata.get("order_id")

            if order_id:
                try:
                    order = Order.objects.get(id=order_id)
                    order.payment_status = "failed"
                    # Keep order status as "to_pay" so user can retry
                    order.save()

                    print(
                        f"⚠️ Payment failed for order {order.id} - status remains 'to_pay'"
                    )

                    # Send realtime updates
                    order_serializer = OrderSerializer(order)
                    send_order_update(order.user.id, order_serializer.data)

                    # Send notification
                    send_notification(
                        order.user.id,
                        {
                            "type": "payment_failed",
                            "message": f"Payment for Order #{order.id} has failed. Please try again.",
                            "order_id": order.id,
                        },
                    )

                except Order.DoesNotExist:
                    logger.error(f"Order {order_id} not found for webhook")
                    print(f"❌ ERROR: Order {order_id} not found for webhook")

        # Legacy payment intent events (keep for backward compatibility)
        elif event_type == "payment_intent.succeeded":
            from .paymongo_service import update_order_payment_status

            # Handle successful payment intent
            payment_intent_data = attributes.get("data", {})
            payment_intent_attrs = payment_intent_data.get("attributes", {})
            metadata = payment_intent_attrs.get("metadata", {})
            order_id = metadata.get("order_id")

            if order_id:
                try:
                    order = Order.objects.get(id=order_id)

                    # Extract payment source type from payments array
                    payments = payment_intent_attrs.get("payments", [])
                    if payments and len(payments) > 0:
                        source = payments[0].get("attributes", {}).get("source", {})
                        payment_source_type = source.get("type")
                        if payment_source_type:
                            mapped_payment_method = (
                                map_paymongo_source_to_payment_method(
                                    payment_source_type
                                )
                            )
                            order.payment_method = mapped_payment_method
                            print(
                                f"💳 Payment method updated to: {mapped_payment_method} (from source: {payment_source_type})"
                            )

                    update_order_payment_status(order, {"data": payment_intent_data})

                    # Deduct inventory and clear reserved cart for successful payment
                    deduct_inventory_for_order(order)
                    clear_reserved_cart(order.user.id, order.id)

                    # Send realtime updates
                    order_serializer = OrderSerializer(order)
                    send_order_update(order.user.id, order_serializer.data)

                    # Send notification
                    send_notification(
                        order.user.id,
                        {
                            "type": "payment_success",
                            "message": f"Payment for Order #{order.id} has been confirmed",
                            "order_id": order.id,
                        },
                    )

                except Order.DoesNotExist:
                    logger.error(f"Order {order_id} not found for webhook")

        elif event_type == "payment_intent.payment_failed":
            # Handle failed payment intent
            payment_intent_data = attributes.get("data", {})
            metadata = payment_intent_data.get("attributes", {}).get("metadata", {})
            order_id = metadata.get("order_id")

            if order_id:
                try:
                    order = Order.objects.get(id=order_id)
                    order.payment_status = "failed"
                    order.save()

                    # Send realtime updates
                    order_serializer = OrderSerializer(order)
                    send_order_update(order.user.id, order_serializer.data)

                    # Send notification
                    send_notification(
                        order.user.id,
                        {
                            "type": "payment_failed",
                            "message": f"Payment for Order #{order.id} has failed",
                            "order_id": order.id,
                        },
                    )

                except Order.DoesNotExist:
                    logger.error(f"Order {order_id} not found for webhook")
                    print(f"❌ ERROR: Order {order_id} not found for webhook")

        print("=" * 80)
        print("✅ WEBHOOK PROCESSED SUCCESSFULLY")
        print(f"Event Type: {event_type}")
        print("=" * 80 + "\n")

        return Response({"status": "success"}, status=status.HTTP_200_OK)

    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ WEBHOOK ERROR")
        print("=" * 80)
        print(f"Error: {str(e)}")
        print(f"Type: {type(e).__name__}")
        import traceback

        print(f"Traceback:\n{traceback.format_exc()}")
        print("=" * 80 + "\n")

        logger.error(f"Error handling PayMongo webhook: {str(e)}")
        return Response(
            {"error": "Internal server error"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


# Bike Builder & Compatibility API
@api_view(["GET"])
def get_compatibility_groups(request):
    """Get all compatibility groups with their attributes and values"""
    groups = CompatibilityGroup.objects.prefetch_related("attributes__values").all()
    serializer = CompatibilityGroupSerializer(groups, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
def get_compatibility_attributes(request):
    """Get all compatibility attributes"""
    attributes = CompatibilityAttribute.objects.select_related("group").all()
    serializer = CompatibilityAttributeSerializer(attributes, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
def get_compatibility_attribute_values(request):
    """Get all compatibility attribute values"""
    values = CompatibilityAttributeValue.objects.select_related(
        "attribute", "attribute__group"
    ).all()
    serializer = CompatibilityAttributeValueSerializer(values, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
def get_bike_builder_products(request):
    """
    Get products enabled for bike builder.
    Can filter by:
    - builder_category: frame, wheels, drivetrain, brakes, handlebars, saddle
    - compatibility_tag_ids: comma-separated list of compatibility tag IDs to match
    - use_case: filter by use case value (city, trail, casual)
    - budget: filter by budget value (budget, mid, premium)
    """
    products = (
        ProductListing.objects.filter(bike_builder_enabled=True, available=True)
        .prefetch_related(
            "products",
            "products__brand",
            "compatibility_tags",
            "images",
        )
        .select_related("category")
    )

    # Filter by builder category
    builder_category = request.GET.get("builder_category")
    if builder_category:
        products = products.filter(builder_category=builder_category)

    # Filter by use case
    use_case = request.GET.get("use_case")
    if use_case:
        products = products.filter(
            compatibility_tags__tag_type="use_case",
            compatibility_tags__value=use_case
        ).distinct()
    
    # Filter by budget
    budget = request.GET.get("budget")
    if budget:
        products = products.filter(
            compatibility_tags__tag_type="budget",
            compatibility_tags__value=budget
        ).distinct()

    # Filter by compatibility tags - products that have ANY of the specified tags
    compatibility_tag_ids = request.GET.get("compatibility_tag_ids")
    if compatibility_tag_ids:
        try:
            # Parse comma-separated IDs
            ids = [int(id.strip()) for id in compatibility_tag_ids.split(",") if id.strip()]
            if ids:
                # Find products that have ANY of the specified compatibility tags
                products = products.filter(compatibility_tags__id__in=ids).distinct()
        except ValueError:
            return Response(
                {"error": "Invalid compatibility_tag_ids format"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Order by priority (higher first), then by name
    products = products.order_by("-builder_priority", "name")

    serializer = ProductListingSerializer(products, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["GET"])
def get_compatible_products(request, listing_id):
    """
    Get products compatible with a specific listing.
    This checks what products can work together with the given product.
    """
    try:
        listing = ProductListing.objects.get(id=listing_id)

        # Get products that are compatible
        compatible_products = listing.find_compatible_products()

        serializer = ProductListingSerializer(compatible_products, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except ProductListing.DoesNotExist:
        return Response(
            {"error": "Product listing not found"}, status=status.HTTP_404_NOT_FOUND
        )
