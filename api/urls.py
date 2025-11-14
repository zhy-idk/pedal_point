from django.urls import path
from . import views

urlpatterns = [
    path("brands/", views.get_brands, name="get_brands"),
    path("brands/create/", views.create_brand, name="create_brand"),
    # Product Listings (formerly Product)
    # IMPORTANT: Specific patterns MUST come before generic slug pattern
    path("listings/create/", views.create_listing, name="create_listing"),
    path(
        "listings/unassigned-products/",
        views.get_unassigned_products,
        name="get_unassigned_products",
    ),
    path(
        "listings/<int:listing_id>/assign-products/",
        views.assign_products_to_listing,
        name="assign_products_to_listing",
    ),
    path(
        "listings/unassign-products/",
        views.unassign_products_from_listing,
        name="unassign_products_from_listing",
    ),
    path(
        "listings/images/<int:image_id>/delete/",
        views.delete_listing_image,
        name="delete_listing_image",
    ),
    path(
        "listings/<int:listing_id>/update/", views.update_listing, name="update_listing"
    ),
    path(
        "listings/<int:listing_id>/delete/", views.delete_listing, name="delete_listing"
    ),
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
    path("categories/create/", views.create_category, name="create_category"),
    # Bike Builder & Compatibility Tags (New System)
    path(
        "bike-builder/compatibility-tags/",
        views.get_compatibility_tags,
        name="get_compatibility_tags",
    ),
    path(
        "bike-builder/compatibility-tags/create/",
        views.create_compatibility_tag,
        name="create_compatibility_tag",
    ),
    path(
        "bike-builder/compatibility-tags/<int:tag_id>/update/",
        views.update_compatibility_tag,
        name="update_compatibility_tag",
    ),
    path(
        "bike-builder/compatibility-tags/<int:tag_id>/delete/",
        views.delete_compatibility_tag,
        name="delete_compatibility_tag",
    ),
    path(
        "bike-builder/products/",
        views.get_bike_builder_products,
        name="get_bike_builder_products",
    ),
    # Old Compatibility System (Deprecated, kept for backward compatibility)
    path(
        "compatibility/groups/",
        views.get_compatibility_groups,
        name="get_compatibility_groups",
    ),
    path(
        "compatibility/attributes/",
        views.get_compatibility_attributes,
        name="get_compatibility_attributes",
    ),
    path(
        "compatibility/values/",
        views.get_compatibility_attribute_values,
        name="get_compatibility_attribute_values",
    ),
    path(
        "listings/<int:listing_id>/compatible/",
        views.get_compatible_products,
        name="get_compatible_products",
    ),
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
    path("cart/buy-now-checkout/", views.buy_now_checkout, name="buy_now_checkout"),
    path("cart/checkout/<int:order_id>/", views.get_order, name="get_order"),
    # POS Sales
    path("pos/sale/", views.pos_sale, name="pos_sale"),
    path(
        "cart/checkout/<int:order_id>/items/",
        views.get_order_items,
        name="get_order_items",
    ),
    # Orders
    path("orders/", views.get_all_order, name="get_all_order"),
    path("orders/<int:order_id>", views.get_order, name="get_order"),
    path("orders/my-orders/", views.get_customer_orders, name="get_customer_orders"),
    path(
        "orders/<int:order_id>/update-status/",
        views.update_order_status,
        name="update_order_status",
    ),
    path("reviews/", views.create_product_review, name="create_product_review"),
    # Queue
    path("queue/", views.get_all_schedule, name="get_all_schedule"),
    path("queue/count/", views.get_queue_count, name="get_queue_count"),
    path("queue/add/", views.schedule_service, name="schedule_service"),
    path(
        "queue/check-pending/",
        views.check_pending_services,
        name="check_pending_services",
    ),
    path(
        "queue/<int:item_id>/update/", views.update_queue_item, name="update_queue_item"
    ),
    # Sales
    path("sales/", views.get_sales, name="get_sales"),
    path("sales/export/", views.export_sales, name="export_sales"),
    path(
        "sales/top-products/",
        views.get_top_selling_products,
        name="get_top_selling_products",
    ),
    path(
        "sales/<int:sale_id>/refund/", views.refund_full_sale, name="refund_full_sale"
    ),
    path(
        "sales/<int:sale_id>/items/<int:item_id>/refund/",
        views.refund_sale_item,
        name="refund_sale_item",
    ),
    # User Management
    path("users/", views.get_all_users, name="get_all_users"),
    path("users/<int:user_id>/", views.get_user, name="get_user"),
    path("users/<int:user_id>/update/", views.update_user, name="update_user"),
    path("users/<int:user_id>/delete/", views.delete_user, name="delete_user"),
    path(
        "users/<int:user_id>/permissions/",
        views.update_staff_permissions,
        name="update_staff_permissions",
    ),
    path("audit-logs/", views.get_audit_logs, name="get_audit_logs"),
    # Compatibility Management
    path(
        "compatibility/groups/create/",
        views.create_compatibility_group,
        name="create_compatibility_group",
    ),
    path(
        "compatibility/groups/<int:group_id>/update/",
        views.update_compatibility_group,
        name="update_compatibility_group",
    ),
    path(
        "compatibility/groups/<int:group_id>/delete/",
        views.delete_compatibility_group,
        name="delete_compatibility_group",
    ),
    path(
        "compatibility/attributes/create/",
        views.create_compatibility_attribute,
        name="create_compatibility_attribute",
    ),
    path(
        "compatibility/attributes/<int:attribute_id>/update/",
        views.update_compatibility_attribute,
        name="update_compatibility_attribute",
    ),
    path(
        "compatibility/attributes/<int:attribute_id>/delete/",
        views.delete_compatibility_attribute,
        name="delete_compatibility_attribute",
    ),
    path(
        "compatibility/values/create/",
        views.create_compatibility_value,
        name="create_compatibility_value",
    ),
    path(
        "compatibility/values/<int:value_id>/update/",
        views.update_compatibility_value,
        name="update_compatibility_value",
    ),
    path(
        "compatibility/values/<int:value_id>/delete/",
        views.delete_compatibility_value,
        name="delete_compatibility_value",
    ),
    # Product Reservations
    path("reservations/create/", views.create_reservation, name="create_reservation"),
    path(
        "reservations/my-reservations/",
        views.get_user_reservations,
        name="get_user_reservations",
    ),
    path(
        "reservations/<int:reservation_id>/cancel/",
        views.cancel_reservation,
        name="cancel_reservation",
    ),
    path(
        "reservations/product/<int:product_id>/check/",
        views.check_product_reservation,
        name="check_product_reservation",
    ),
    path("reservations/all/", views.get_all_reservations, name="get_all_reservations"),
    # Supplier Management
    path("suppliers/", views.get_all_suppliers, name="get_all_suppliers"),
    path("suppliers/create/", views.create_supplier, name="create_supplier"),
    path(
        "suppliers/<int:supplier_id>/update/",
        views.update_supplier,
        name="update_supplier",
    ),
    path(
        "suppliers/<int:supplier_id>/delete/",
        views.delete_supplier,
        name="delete_supplier",
    ),
    path(
        "suppliers/<int:supplier_id>/products/",
        views.get_supplier_products,
        name="get_supplier_products",
    ),
    # Inventory Management
    path("inventory/", views.get_inventory, name="get_inventory"),
    path(
        "inventory/<int:product_id>/",
        views.get_inventory_item,
        name="get_inventory_item",
    ),
    path(
        "inventory/<int:product_id>/update/",
        views.update_inventory_item,
        name="update_inventory_item",
    ),
    path(
        "inventory/create/", views.create_inventory_item, name="create_inventory_item"
    ),
    path(
        "inventory/<int:product_id>/delete/",
        views.delete_inventory_item,
        name="delete_inventory_item",
    ),
    path(
        "inventory/image/<int:image_id>/delete/",
        views.delete_product_image,
        name="delete_product_image",
    ),
    path(
        "inventory/bulk-update/",
        views.bulk_update_inventory,
        name="bulk_update_inventory",
    ),
    path(
        "inventory/test-update/",
        views.test_inventory_update,
        name="test_inventory_update",
    ),
    # PayMongo Payment Integration
    path(
        "payments/create-checkout/",
        views.create_paymongo_checkout_session,
        name="create_paymongo_checkout_session",
    ),
    path(
        "payments/confirm/<int:order_id>/",
        views.confirm_payment,
        name="confirm_payment",
    ),
    path("payments/webhook/", views.paymongo_webhook, name="paymongo_webhook"),
    # User Info
    path("user_info/", views.user_info, name="user_info"),
    path("user/profile/", views.get_user_profile, name="get_user_profile"),
    path("user/profile/update/", views.update_user_profile, name="update_user_profile"),
    # Order Cancellation
    path("orders/<int:order_id>/cancel/", views.cancel_order, name="cancel_order"),
    path(
        "orders/<int:order_id>/received/",
        views.mark_order_received,
        name="mark_order_received",
    ),
    # Chat System
    path("chat/rooms/", views.get_chat_rooms, name="get_chat_rooms"),
    # Dashboard
    path("dashboard/", views.dashboard_data, name="dashboard_data"),
    # Repair Estimator
    path("repair-estimator/", views.repair_estimator, name="repair_estimator"),
    # Auth & Misc
    path("csrf/", views.get_csrf_token, name="get_csrf"),
    path("test", views.test_user),
]
