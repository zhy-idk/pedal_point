from django.urls import path
from . import views

urlpatterns = [
    path("brands/", views.get_brands, name="get_brands"),
    # Product Listings (formerly Product)
    path("listings/", views.get_product_listings, name="get_product_listings"),
    path("listings/<int:pk>/", views.get_product_listing, name="get_product_listing"),
    path(
        "listings/<str:slug>/",
        views.get_product_listing_by_slug,
        name="get_product_listing_by_slug",
    ),
    path(
        "categories/<slug:category_slug>/recommendations/",
        views.listings_by_category,
        name="category-recommendations",
    ),
    # Images for product listings
    path(
        "listings/images/<int:product_listing_id>/",
        views.get_listing_images,
        name="get_listing_images",
    ),
    # Products (formerly ProductVariant)
    path("products/", views.get_all_products, name="get_all_products"),
    path(
        "listings/<int:product_listing_id>/products/",
        views.get_listing_products,
        name="get_listing_products",
    ),
    # Images for individual product (variant) items
    path(
        "products/images/<int:product_id>/",
        views.get_product_images,
        name="get_product_images",
    ),
    # Categories & Compatibility
    path("categories/", views.get_product_categories, name="get_product_categories"),
    # Cart
    path("cart/", views.get_cart, name="get_cart"),
    path("cart/add/", views.add_to_cart, name="add_to_cart"),
    path(
        "cart/remove/<int:product_id>/", views.remove_from_cart, name="remove_from_cart"
    ),
    path(
        "cart/update/<int:product_id>/",
        views.update_cart_item_quantity,
        name="update_cart_item_quantity",
    ),
    path("cart/clear/", views.clear_cart, name="clear_cart"),
    path("cart/checkout/", views.checkout, name="checkout"),
    path("cart/checkout/<int:order_id>/", views.get_order, name="get_order"),
    path(
        "cart/checkout/<int:order_id>/items/",
        views.get_order_items,
        name="get_order_items",
    ),
    # Orders
    path("orders/", views.get_all_order, name="get_all_order"),
    # Queue
    path("queue/", views.get_all_schedule, name="get_all_schedule"),
    path("queue/add/", views.schedule_service, name="schedule_service"),
    # Sales
    path("sales/", views.get_sales, name="get_sales"),
    # Auth & Misc
    path("csrf/", views.get_csrf_token, name="get_csrf"),
    path("test", views.test_user),
]
