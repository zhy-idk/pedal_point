from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/api/cart/$", consumers.CartConsumer.as_asgi()),
    re_path(r"ws/api/orders/$", consumers.OrderConsumer.as_asgi()),
    re_path(r"ws/api/inventory/$", consumers.InventoryConsumer.as_asgi()),
    re_path(r"ws/api/notifications/$", consumers.NotificationConsumer.as_asgi()),
    re_path(r"ws/api/chat/(?P<room_id>[^/]+)/$", consumers.ChatConsumer.as_asgi()),
]
