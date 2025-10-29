"""
Utility functions for sending realtime updates via WebSocket.
"""

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json


def send_cart_update(user_id, cart_data):
    """Send cart update to user's WebSocket connection."""
    channel_layer = get_channel_layer()
    group_name = f"cart_{user_id}"
    
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'cart_update',
            'data': cart_data
        }
    )


def send_order_update(user_id, order_data):
    """Send order update to user's WebSocket connection."""
    channel_layer = get_channel_layer()
    group_name = f"orders_{user_id}"
    
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'order_update',
            'data': order_data
        }
    )


def send_inventory_update(product_data):
    """Send inventory update to all connected clients."""
    channel_layer = get_channel_layer()
    group_name = "inventory_updates"
    
    print(f"DEBUG: Sending inventory update to group '{group_name}': {product_data}")
    
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'inventory_update',
            'data': product_data
        }
    )
    
    print(f"DEBUG: Inventory update sent successfully")


def send_notification(user_id, notification_data):
    """Send notification to specific user."""
    channel_layer = get_channel_layer()
    group_name = f"notifications_{user_id}"
    
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'notification',
            'data': notification_data
        }
    )


def broadcast_notification(notification_data):
    """Broadcast notification to all connected users."""
    channel_layer = get_channel_layer()
    
    # This would require a different approach for broadcasting to all users
    # For now, we'll use a specific group for admin notifications
    group_name = "admin_notifications"
    
    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'notification',
            'data': notification_data
        }
    )
