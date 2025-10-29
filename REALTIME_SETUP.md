# Pedal Point API - Realtime Setup Guide

This guide will help you set up realtime functionality for your Pedal Point API using Django Channels and WebSockets.

## Prerequisites

1. **Python 3.8+**: For Django Channels compatibility
2. **Django 5.2**: Already configured in your project

## Installation Steps

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

The following packages have been added to your `requirements.txt`:
- `channels==4.1.0` - WebSocket support
- `daphne==4.0.0` - ASGI server for production

**Note**: Redis is no longer required! The system now uses in-memory channel layers for real-time updates.

### 2. Database Migration

```bash
python manage.py makemigrations
python manage.py migrate
```

### 3. Run the Development Server

```bash
python manage.py runserver
```

The server will now support both HTTP and WebSocket connections.

## WebSocket Endpoints

Your API now supports the following WebSocket endpoints:

### Cart Updates
- **URL**: `ws://localhost:8000/ws/api/cart/`
- **Purpose**: Real-time cart updates when items are added, removed, or quantities changed
- **Authentication**: Required (user must be logged in)

### Order Updates
- **URL**: `ws://localhost:8000/ws/api/orders/`
- **Purpose**: Real-time order status updates and new order notifications
- **Authentication**: Required (user must be logged in)

### Inventory Updates
- **URL**: `ws://localhost:8000/ws/api/inventory/`
- **Purpose**: Real-time inventory stock updates, product additions, deletions, and modifications
- **Authentication**: Not required (public updates)
- **Features**: 
  - Real-time stock level changes
  - Product availability updates
  - New product additions
  - Product deletions
  - Bulk update notifications

### Notifications
- **URL**: `ws://localhost:8000/ws/api/notifications/`
- **Purpose**: General notifications and system messages
- **Authentication**: Required (user must be logged in)

## API Endpoints

### Inventory Management API

The following REST API endpoints are available for inventory management:

- `GET /api/inventory/` - Get all inventory items
- `GET /api/inventory/{id}/` - Get specific inventory item
- `PUT /api/inventory/{id}/update/` - Update inventory item (requires authentication)
- `POST /api/inventory/create/` - Create new inventory item (requires authentication)
- `DELETE /api/inventory/{id}/delete/` - Delete inventory item (requires authentication)
- `PUT /api/inventory/bulk-update/` - Bulk update multiple items (requires authentication)

All inventory changes automatically trigger WebSocket updates to connected clients.

## Frontend Integration

### JavaScript Example

```javascript
// Connect to cart updates
const cartWs = new WebSocket('ws://localhost:8000/ws/api/cart/');

cartWs.onmessage = function(event) {
    const data = JSON.parse(event.data);
    if (data.type === 'cart_update') {
        // Update your cart UI
        updateCartDisplay(data.data);
    }
};

// Request current cart data
cartWs.send(JSON.stringify({ type: 'get_cart' }));
```

### React Hook Example

```javascript
import { useState, useEffect } from 'react';

function useCartWebSocket(userId) {
    const [cartData, setCartData] = useState(null);
    
    useEffect(() => {
        if (!userId) return;
        
        const ws = new WebSocket('ws://localhost:8000/ws/api/cart/');
        
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'cart_update') {
                setCartData(data.data);
            }
        };
        
        return () => ws.close();
    }, [userId]);
    
    return cartData;
}

// Inventory WebSocket Hook
function useInventoryWebSocket() {
    const [inventory, setInventory] = useState([]);
    const [isConnected, setIsConnected] = useState(false);
    
    useEffect(() => {
        const ws = new WebSocket('ws://localhost:8000/ws/api/inventory/');
        
        ws.onopen = () => {
            setIsConnected(true);
            ws.send(JSON.stringify({ type: 'get_inventory' }));
        };
        
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'inventory_update') {
                if (Array.isArray(data.data)) {
                    setInventory(data.data);
                } else if (data.data.action === 'deleted') {
                    setInventory(prev => prev.filter(item => item.id !== data.data.product_id));
                } else {
                    // Single item update
                    setInventory(prev => {
                        const index = prev.findIndex(item => item.id === data.data.id);
                        if (index !== -1) {
                            const updated = [...prev];
                            updated[index] = data.data;
                            return updated;
                        }
                        return [...prev, data.data];
                    });
                }
            }
        };
        
        ws.onclose = () => setIsConnected(false);
        
        return () => ws.close();
    }, []);
    
    return { inventory, isConnected };
}
```

## Realtime Features

### 1. Cart Synchronization
- Items added to cart trigger real-time updates
- Quantity changes are instantly reflected
- Cart clearing sends immediate notifications
- Multiple browser tabs stay synchronized

### 2. Order Tracking
- New orders are instantly created and broadcast
- Order status changes trigger notifications
- Order history updates in real-time

### 3. Inventory Management
- Stock level changes are broadcast to all clients in real-time
- Product availability updates instantly across all connected staff interfaces
- Price changes are reflected immediately
- New products are added to the inventory list automatically
- Product deletions are reflected across all connected clients
- Bulk updates are synchronized in real-time

### 4. Notifications
- Order confirmations
- Stock alerts
- System messages
- Custom notifications

## Production Deployment

### 1. Channel Layer Configuration

The system uses in-memory channel layers by default, which is perfect for single-server deployments:

```python
# In settings.py (already configured)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}
```

**Note**: For multi-server deployments, you may want to use Redis or another channel layer backend.

### 2. ASGI Server

Use an ASGI server like Daphne for production:

```bash
pip install daphne
daphne -b 0.0.0.0 -p 8000 pedal_point.asgi:application
```

### 3. Nginx Configuration

```nginx
upstream channels-backend {
    server localhost:8000;
}

server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://channels-backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Testing WebSocket Connections

### 1. Using Browser Console

```javascript
// Test cart WebSocket
const ws = new WebSocket('ws://localhost:8000/ws/api/cart/');
ws.onopen = () => console.log('Connected');
ws.onmessage = (event) => console.log('Message:', JSON.parse(event.data));
ws.send(JSON.stringify({ type: 'get_cart' }));
```

### 2. Using WebSocket Testing Tools

- **WebSocket King**: Browser extension for testing WebSocket connections
- **Postman**: Supports WebSocket testing
- **wscat**: Command-line WebSocket client

```bash
npm install -g wscat
wscat -c ws://localhost:8000/ws/api/cart/
```

## Troubleshooting

### Common Issues

1. **WebSocket Connection Failed**
   - Check if ASGI application is properly configured
   - Verify WebSocket routing is set up correctly
   - Ensure proper CORS settings for WebSocket connections

2. **Authentication Issues**
   - WebSocket authentication uses Django session authentication
   - Ensure user is logged in before connecting
   - Check session configuration in settings

### Debug Mode

Enable debug logging for WebSocket connections:

```python
# In settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'channels': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

## Security Considerations

1. **Authentication**: All user-specific WebSocket connections require authentication
2. **CORS**: Configure proper CORS settings for WebSocket connections
3. **Rate Limiting**: Consider implementing rate limiting for WebSocket connections
4. **Input Validation**: Validate all WebSocket messages on the server side

## Performance Optimization

1. **Connection Pooling**: Use Redis connection pooling for better performance
2. **Message Compression**: Consider compressing large WebSocket messages
3. **Connection Limits**: Implement connection limits per user
4. **Monitoring**: Monitor WebSocket connection counts and message rates

## Next Steps

1. **Custom Events**: Add custom WebSocket events for specific business logic
2. **Presence**: Implement user presence tracking
3. **Scaling**: Consider using Redis Cluster for horizontal scaling
4. **Analytics**: Add WebSocket connection and message analytics

For more detailed examples and advanced usage, see `api/frontend_examples.js`.
