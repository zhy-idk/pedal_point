import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser, User
from .models import *
from .serializer import *


class CartConsumer(AsyncWebsocketConsumer):
    """Consumer for realtime cart updates."""

    async def connect(self):
        """Accept WebSocket connection and join user's cart group."""
        self.user = self.scope["user"]

        if isinstance(self.user, AnonymousUser):
            await self.close()
            return

        self.cart_group_name = f"cart_{self.user.id}"

        # Join cart group
        await self.channel_layer.group_add(self.cart_group_name, self.channel_name)

        await self.accept()

        # Send current cart state
        cart_data = await self.get_cart_data()
        await self.send(
            text_data=json.dumps({"type": "cart_update", "data": cart_data})
        )

    async def disconnect(self, close_code):
        """Leave cart group when disconnected."""
        if hasattr(self, "cart_group_name"):
            await self.channel_layer.group_discard(
                self.cart_group_name, self.channel_name
            )

    async def receive(self, text_data):
        """Handle messages from WebSocket."""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get("type")

            if message_type == "get_cart":
                cart_data = await self.get_cart_data()
                await self.send(
                    text_data=json.dumps({"type": "cart_update", "data": cart_data})
                )
        except json.JSONDecodeError:
            await self.send(
                text_data=json.dumps({"type": "error", "message": "Invalid JSON"})
            )

    async def cart_update(self, event):
        """Send cart update to WebSocket."""
        await self.send(
            text_data=json.dumps({"type": "cart_update", "data": event["data"]})
        )

    @database_sync_to_async
    def get_cart_data(self):
        """Get current cart data for the user."""
        try:
            cart = Cart.objects.get(user=self.user)
            serializer = CartSerializer(cart)
            return serializer.data
        except Cart.DoesNotExist:
            return {"items": [], "total": 0}


class OrderConsumer(AsyncWebsocketConsumer):
    """Consumer for realtime order updates."""

    async def connect(self):
        """Accept WebSocket connection and join user's order group."""
        self.user = self.scope["user"]

        if isinstance(self.user, AnonymousUser):
            await self.close()
            return

        self.order_group_name = f"orders_{self.user.id}"

        # Join order group
        await self.channel_layer.group_add(self.order_group_name, self.channel_name)

        await self.accept()

        # Send current orders
        orders_data = await self.get_orders_data()
        await self.send(
            text_data=json.dumps({"type": "orders_update", "data": orders_data})
        )

    async def disconnect(self, close_code):
        """Leave order group when disconnected."""
        if hasattr(self, "order_group_name"):
            await self.channel_layer.group_discard(
                self.order_group_name, self.channel_name
            )

    async def receive(self, text_data):
        """Handle messages from WebSocket."""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get("type")

            if message_type == "get_orders":
                orders_data = await self.get_orders_data()
                await self.send(
                    text_data=json.dumps({"type": "orders_update", "data": orders_data})
                )
        except json.JSONDecodeError:
            await self.send(
                text_data=json.dumps({"type": "error", "message": "Invalid JSON"})
            )

    async def order_update(self, event):
        """Send order update to WebSocket."""
        await self.send(
            text_data=json.dumps({"type": "order_update", "data": event["data"]})
        )

    @database_sync_to_async
    def get_orders_data(self):
        """Get current orders for the user."""
        orders = Order.objects.filter(user=self.user).order_by("-created_at")
        serializer = OrderSerializer(orders, many=True)
        return serializer.data


class InventoryConsumer(AsyncWebsocketConsumer):
    """Consumer for realtime inventory updates."""

    async def connect(self):
        """Accept WebSocket connection and join inventory group."""
        self.inventory_group_name = "inventory_updates"

        # Join inventory group
        await self.channel_layer.group_add(self.inventory_group_name, self.channel_name)

        print(
            f"DEBUG: InventoryConsumer connected to group '{self.inventory_group_name}'"
        )
        await self.accept()

        # Send current inventory data
        inventory_data = await self.get_inventory_data()
        await self.send(
            text_data=json.dumps({"type": "inventory_update", "data": inventory_data})
        )
        print(f"DEBUG: Sent initial inventory data with {len(inventory_data)} items")

    async def disconnect(self, close_code):
        """Leave inventory group when disconnected."""
        await self.channel_layer.group_discard(
            self.inventory_group_name, self.channel_name
        )

    async def receive(self, text_data):
        """Handle messages from WebSocket."""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get("type")

            if message_type == "get_inventory":
                inventory_data = await self.get_inventory_data()
                await self.send(
                    text_data=json.dumps(
                        {"type": "inventory_update", "data": inventory_data}
                    )
                )
        except json.JSONDecodeError:
            await self.send(
                text_data=json.dumps({"type": "error", "message": "Invalid JSON"})
            )

    async def inventory_update(self, event):
        """Send inventory update to WebSocket."""
        print(f"DEBUG: InventoryConsumer received update: {event['data']}")
        await self.send(
            text_data=json.dumps({"type": "inventory_update", "data": event["data"]})
        )
        print(f"DEBUG: InventoryConsumer sent update to WebSocket client")

    @database_sync_to_async
    def get_inventory_data(self):
        """Get current inventory data."""
        products = Product.objects.filter(available=True)
        serializer = ProductSerializer(products, many=True)
        return serializer.data


class NotificationConsumer(AsyncWebsocketConsumer):
    """Consumer for general notifications."""

    async def connect(self):
        """Accept WebSocket connection and join notification group."""
        self.user = self.scope["user"]

        if isinstance(self.user, AnonymousUser):
            await self.close()
            return

        self.notification_group_name = f"notifications_{self.user.id}"

        # Join notification group
        await self.channel_layer.group_add(
            self.notification_group_name, self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        """Leave notification group when disconnected."""
        if hasattr(self, "notification_group_name"):
            await self.channel_layer.group_discard(
                self.notification_group_name, self.channel_name
            )

    async def receive(self, text_data):
        """Handle messages from WebSocket."""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get("type")

            if message_type == "ping":
                await self.send(
                    text_data=json.dumps(
                        {"type": "pong", "message": "Connection active"}
                    )
                )
        except json.JSONDecodeError:
            await self.send(
                text_data=json.dumps({"type": "error", "message": "Invalid JSON"})
            )

    async def notification(self, event):
        """Send notification to WebSocket."""
        await self.send(
            text_data=json.dumps({"type": "notification", "data": event["data"]})
        )


class ChatConsumer(AsyncWebsocketConsumer):
    """Consumer for real-time chat messaging between customers and staff."""

    async def connect(self):
        """Accept WebSocket connection and join chat room."""
        self.user = self.scope["user"]
        self.room_id = self.scope["url_route"]["kwargs"].get("room_id", "")

        print(f"DEBUG: ChatConsumer connecting with room_id: '{self.room_id}'")
        print(f"DEBUG: URL route kwargs: {self.scope['url_route']['kwargs']}")

        # Only allow authenticated users
        if self.user.is_anonymous or not self.user.is_authenticated:
            print("DEBUG: Rejecting connection - user not authenticated")
            await self.close(code=4001)  # Custom close code for unauthenticated
            return

        # Don't accept connection if room_id is empty or invalid
        if not self.room_id or self.room_id.strip() == "" or self.room_id.startswith("customer_guest_"):
            print(f"DEBUG: Rejecting connection due to invalid room_id: {self.room_id}")
            await self.close(code=4000)  # Custom close code for invalid room_id
            return

        self.chat_group_name = f"chat_{self.room_id}"

        # Join chat room group
        await self.channel_layer.group_add(self.chat_group_name, self.channel_name)

        await self.accept()

        # Send chat history
        chat_history = await self.get_chat_history()
        await self.send(
            text_data=json.dumps({"type": "chat_history", "data": chat_history})
        )

    async def disconnect(self, close_code):
        """Leave chat room when disconnected."""
        if hasattr(self, "chat_group_name"):
            await self.channel_layer.group_discard(
                self.chat_group_name, self.channel_name
            )

    async def receive(self, text_data):
        """Handle messages from WebSocket."""
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get("type")
            content = text_data_json.get("content", "").strip()

            if message_type == "chat_message":
                if not content:
                    return
                # Save message to database and get serialized data
                message_data = await self.save_message(content)
                
                print(f"DEBUG: save_message returned: {message_data}")

                # Only broadcast if message was saved successfully
                if message_data:
                    # Broadcast message to all participants in the room
                    await self.channel_layer.group_send(
                        self.chat_group_name,
                        {
                            "type": "chat_message",
                            "message": message_data,
                        },
                    )
                else:
                    print(f"ERROR: Failed to save message for room {self.room_id}")
                    await self.send(
                        text_data=json.dumps({"type": "error", "message": "Failed to save message"})
                    )
            elif message_type == "mark_read":
                # Mark messages as read based on which interface is being used
                if self.user and self.user.is_authenticated:
                    is_staff_interface = text_data_json.get("is_staff_interface", False)
                    print(f"DEBUG mark_read: user={self.user.username}, is_staff_interface={is_staff_interface}")
                    await self.mark_messages_read(is_staff_interface)
                    reader_type = "staff" if is_staff_interface else "customer"
                    print(f"DEBUG mark_read: Broadcasting as reader_type={reader_type}")
                    # Broadcast read event to the room so UIs update
                    await self.channel_layer.group_send(
                        self.chat_group_name,
                        {
                            "type": "chat_read",
                            "data": {
                                "room_id": self.room_id,
                                "reader": reader_type,
                            },
                        },
                    )

        except json.JSONDecodeError:
            await self.send(
                text_data=json.dumps({"type": "error", "message": "Invalid JSON"})
            )

    async def chat_message(self, event):
        message_data = event["message"]
        if message_data:
            await self.send(
                text_data=json.dumps({"type": "chat_message", "message": message_data})
            )

    async def chat_read(self, event):
        """Notify clients in the room that messages were marked as read."""
        await self.send(
            text_data=json.dumps({"type": "chat_read", "data": event.get("data", {})})
        )

    @database_sync_to_async
    def get_chat_history(self):
        """Get recent chat messages for this room."""
        try:
            # Extract user_id from room_id (format: customer_{user_id})
            if self.room_id.startswith("customer_"):
                user_id = int(self.room_id.split("_")[1])
                owner = User.objects.get(id=user_id)
                
                # Get or create chat room for this user
                chat_room, created = ChatRoom.objects.get_or_create(
                    owner=owner,
                    defaults={"is_active": True},
                )

                messages = (
                    ChatItem.objects.filter(chat_room=chat_room)
                    .select_related("sender")
                    .order_by("-sent_at")[:50]
                )

                serializer = ChatItemSerializer(messages, many=True)
                return list(reversed(serializer.data))  # Reverse to show oldest first
            
            print(f"ERROR: Invalid room_id format: {self.room_id}")
            return []
        except (ValueError, User.DoesNotExist, ChatRoom.DoesNotExist) as e:
            print(f"ERROR get_chat_history: {e}")
            return []

    @database_sync_to_async
    def save_message(self, content):
        """Save message to database and return serialized data."""
        try:
            print(f"DEBUG save_message: room_id={self.room_id}, user={self.user}, content={content[:50]}")
            
            # Determine message type
            if self.user.is_authenticated and self.user.is_staff:
                message_type = "staff"
            elif self.user.is_authenticated:
                message_type = "customer"
            else:
                message_type = "customer"

            print(f"DEBUG save_message: message_type={message_type}")

            # Extract user_id from room_id (format: customer_{user_id})
            if self.room_id.startswith("customer_"):
                user_id = int(self.room_id.split("_")[1])
                print(f"DEBUG save_message: extracted user_id={user_id}")
                
                owner = User.objects.get(id=user_id)
                print(f"DEBUG save_message: found owner={owner.username}")
                
                # Get or create chat room for this owner (one room per customer)
                chat_room, created = ChatRoom.objects.get_or_create(
                    owner=owner,
                    defaults={"is_active": True},
                )
                print(f"DEBUG save_message: chat_room={chat_room.id}, created={created}")

                # Create chat item
                message = ChatItem.objects.create(
                    chat_room=chat_room,
                    sender=self.user,
                    message_type=message_type,
                    message=content,
                )
                print(f"DEBUG save_message: created message={message.id}")

                # Refresh the message to get updated chat_room state
                message.refresh_from_db()
                message.chat_room.refresh_from_db()
                print(f"DEBUG save_message: After refresh - chat_room.is_read_staff={message.chat_room.is_read_staff}, is_read_customer={message.chat_room.is_read_customer}")

                # Serialize it before returning
                serializer = ChatItemSerializer(message)
                print(f"DEBUG save_message: serialized data keys={serializer.data.keys()}")
                print(f"DEBUG save_message: is_read value={serializer.data.get('is_read')}")
                return serializer.data
            else:
                print(f"ERROR save_message: Invalid room_id format: {self.room_id}")
                return None
                
        except ValueError as e:
            print(f"ERROR save_message ValueError: {e}")
            return None
        except User.DoesNotExist as e:
            print(f"ERROR save_message User.DoesNotExist: {e}")
            return None
        except Exception as e:
            print(f"ERROR save_message unexpected: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return None

    @database_sync_to_async
    def mark_messages_read(self, is_staff_interface=False):
        """Mark chat room as read based on which interface is being used."""
        try:
            # Extract user_id from room_id (format: customer_{user_id})
            if self.room_id.startswith("customer_"):
                user_id = int(self.room_id.split("_")[1])
                owner = User.objects.get(id=user_id)
                
                chat_room = ChatRoom.objects.get(owner=owner)
                print(f"DEBUG mark_messages_read: chat_room={chat_room.id}, is_read_staff={chat_room.is_read_staff}, is_read_customer={chat_room.is_read_customer}")

                if is_staff_interface:
                    print(f"DEBUG mark_messages_read: Marking as read by staff (staff interface)")
                    chat_room.mark_read_by_staff()
                else:
                    print(f"DEBUG mark_messages_read: Marking as read by customer (customer interface)")
                    chat_room.mark_read_by_customer()
                
                # Reload to see updated values
                chat_room.refresh_from_db()
                print(f"DEBUG mark_messages_read: AFTER update - is_read_staff={chat_room.is_read_staff}, is_read_customer={chat_room.is_read_customer}")

        except (ValueError, User.DoesNotExist, ChatRoom.DoesNotExist) as e:
            print(f"ERROR mark_messages_read: {e}")
            pass
