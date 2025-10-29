/**
 * Frontend WebSocket Integration Examples for Pedal Point API
 * 
 * This file contains JavaScript examples for connecting to the realtime API
 * using WebSocket connections. Copy and adapt these examples for your frontend.
 */

// WebSocket Connection Manager
class PedalPointWebSocket {
    constructor(baseUrl = 'ws://localhost:8000') {
        this.baseUrl = baseUrl;
        this.connections = {};
        this.reconnectAttempts = 3;
        this.reconnectDelay = 1000;
    }

    // Connect to cart WebSocket
    connectToCart(userId, onMessage, onError) {
        const wsUrl = `${this.baseUrl}/ws/api/cart/`;
        const ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            console.log('Cart WebSocket connected');
            this.connections.cart = ws;
        };
        
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            onMessage(data);
        };
        
        ws.onerror = (error) => {
            console.error('Cart WebSocket error:', error);
            onError(error);
        };
        
        ws.onclose = () => {
            console.log('Cart WebSocket disconnected');
            delete this.connections.cart;
        };
        
        return ws;
    }

    // Connect to orders WebSocket
    connectToOrders(userId, onMessage, onError) {
        const wsUrl = `${this.baseUrl}/ws/api/orders/`;
        const ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            console.log('Orders WebSocket connected');
            this.connections.orders = ws;
        };
        
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            onMessage(data);
        };
        
        ws.onerror = (error) => {
            console.error('Orders WebSocket error:', error);
            onError(error);
        };
        
        ws.onclose = () => {
            console.log('Orders WebSocket disconnected');
            delete this.connections.orders;
        };
        
        return ws;
    }

    // Connect to inventory WebSocket
    connectToInventory(onMessage, onError) {
        const wsUrl = `${this.baseUrl}/ws/api/inventory/`;
        const ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            console.log('Inventory WebSocket connected');
            this.connections.inventory = ws;
        };
        
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            onMessage(data);
        };
        
        ws.onerror = (error) => {
            console.error('Inventory WebSocket error:', error);
            onError(error);
        };
        
        ws.onclose = () => {
            console.log('Inventory WebSocket disconnected');
            delete this.connections.inventory;
        };
        
        return ws;
    }

    // Connect to notifications WebSocket
    connectToNotifications(userId, onMessage, onError) {
        const wsUrl = `${this.baseUrl}/ws/api/notifications/`;
        const ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            console.log('Notifications WebSocket connected');
            this.connections.notifications = ws;
        };
        
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            onMessage(data);
        };
        
        ws.onerror = (error) => {
            console.error('Notifications WebSocket error:', error);
            onError(error);
        };
        
        ws.onclose = () => {
            console.log('Notifications WebSocket disconnected');
            delete this.connections.notifications;
        };
        
        return ws;
    }

    // Send message to WebSocket
    sendMessage(connectionType, message) {
        if (this.connections[connectionType]) {
            this.connections[connectionType].send(JSON.stringify(message));
        }
    }

    // Close all connections
    disconnect() {
        Object.values(this.connections).forEach(ws => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.close();
            }
        });
        this.connections = {};
    }
}

// React Hook Example
function usePedalPointWebSocket(userId) {
    const [cartData, setCartData] = useState(null);
    const [ordersData, setOrdersData] = useState([]);
    const [inventoryData, setInventoryData] = useState([]);
    const [notifications, setNotifications] = useState([]);
    const [wsManager] = useState(() => new PedalPointWebSocket());

    useEffect(() => {
        if (!userId) return;

        // Connect to cart updates
        wsManager.connectToCart(userId, (data) => {
            if (data.type === 'cart_update') {
                setCartData(data.data);
            }
        }, (error) => {
            console.error('Cart WebSocket error:', error);
        });

        // Connect to order updates
        wsManager.connectToOrders(userId, (data) => {
            if (data.type === 'orders_update') {
                setOrdersData(data.data);
            } else if (data.type === 'order_update') {
                setOrdersData(prev => [data.data, ...prev]);
            }
        }, (error) => {
            console.error('Orders WebSocket error:', error);
        });

        // Connect to inventory updates
        wsManager.connectToInventory((data) => {
            if (data.type === 'inventory_update') {
                setInventoryData(data.data);
            }
        }, (error) => {
            console.error('Inventory WebSocket error:', error);
        });

        // Connect to notifications
        wsManager.connectToNotifications(userId, (data) => {
            if (data.type === 'notification') {
                setNotifications(prev => [data.data, ...prev]);
            }
        }, (error) => {
            console.error('Notifications WebSocket error:', error);
        });

        return () => {
            wsManager.disconnect();
        };
    }, [userId, wsManager]);

    return {
        cartData,
        ordersData,
        inventoryData,
        notifications,
        wsManager
    };
}

// Vue.js Composition API Example
function usePedalPointWebSocket(userId) {
    const cartData = ref(null);
    const ordersData = ref([]);
    const inventoryData = ref([]);
    const notifications = ref([]);
    const wsManager = new PedalPointWebSocket();

    onMounted(() => {
        if (!userId.value) return;

        // Connect to cart updates
        wsManager.connectToCart(userId.value, (data) => {
            if (data.type === 'cart_update') {
                cartData.value = data.data;
            }
        }, (error) => {
            console.error('Cart WebSocket error:', error);
        });

        // Connect to order updates
        wsManager.connectToOrders(userId.value, (data) => {
            if (data.type === 'orders_update') {
                ordersData.value = data.data;
            } else if (data.type === 'order_update') {
                ordersData.value.unshift(data.data);
            }
        }, (error) => {
            console.error('Orders WebSocket error:', error);
        });

        // Connect to inventory updates
        wsManager.connectToInventory((data) => {
            if (data.type === 'inventory_update') {
                inventoryData.value = data.data;
            }
        }, (error) => {
            console.error('Inventory WebSocket error:', error);
        });

        // Connect to notifications
        wsManager.connectToNotifications(userId.value, (data) => {
            if (data.type === 'notification') {
                notifications.value.unshift(data.data);
            }
        }, (error) => {
            console.error('Notifications WebSocket error:', error);
        });
    });

    onUnmounted(() => {
        wsManager.disconnect();
    });

    return {
        cartData,
        ordersData,
        inventoryData,
        notifications,
        wsManager
    };
}

// Angular Service Example
@Injectable({
    providedIn: 'root'
})
export class PedalPointWebSocketService {
    private wsManager = new PedalPointWebSocket();
    private cartSubject = new BehaviorSubject(null);
    private ordersSubject = new BehaviorSubject([]);
    private inventorySubject = new BehaviorSubject([]);
    private notificationsSubject = new BehaviorSubject([]);

    public cart$ = this.cartSubject.asObservable();
    public orders$ = this.ordersSubject.asObservable();
    public inventory$ = this.inventorySubject.asObservable();
    public notifications$ = this.notificationsSubject.asObservable();

    connect(userId: number) {
        // Connect to cart updates
        this.wsManager.connectToCart(userId, (data) => {
            if (data.type === 'cart_update') {
                this.cartSubject.next(data.data);
            }
        }, (error) => {
            console.error('Cart WebSocket error:', error);
        });

        // Connect to order updates
        this.wsManager.connectToOrders(userId, (data) => {
            if (data.type === 'orders_update') {
                this.ordersSubject.next(data.data);
            } else if (data.type === 'order_update') {
                const currentOrders = this.ordersSubject.value;
                this.ordersSubject.next([data.data, ...currentOrders]);
            }
        }, (error) => {
            console.error('Orders WebSocket error:', error);
        });

        // Connect to inventory updates
        this.wsManager.connectToInventory((data) => {
            if (data.type === 'inventory_update') {
                this.inventorySubject.next(data.data);
            }
        }, (error) => {
            console.error('Inventory WebSocket error:', error);
        });

        // Connect to notifications
        this.wsManager.connectToNotifications(userId, (data) => {
            if (data.type === 'notification') {
                const currentNotifications = this.notificationsSubject.value;
                this.notificationsSubject.next([data.data, ...currentNotifications]);
            }
        }, (error) => {
            console.error('Notifications WebSocket error:', error);
        });
    }

    disconnect() {
        this.wsManager.disconnect();
    }
}

// Usage Examples

// 1. Basic Cart Integration
const wsManager = new PedalPointWebSocket();

wsManager.connectToCart(userId, (data) => {
    if (data.type === 'cart_update') {
        // Update cart UI
        updateCartDisplay(data.data);
    }
}, (error) => {
    console.error('Cart WebSocket error:', error);
});

// 2. Real-time Order Tracking
wsManager.connectToOrders(userId, (data) => {
    if (data.type === 'order_update') {
        // Show order update notification
        showNotification(`Order #${data.data.id} status updated`);
        // Refresh orders list
        refreshOrdersList();
    }
}, (error) => {
    console.error('Orders WebSocket error:', error);
});

// 3. Inventory Stock Updates
wsManager.connectToInventory((data) => {
    if (data.type === 'inventory_update') {
        // Update product availability
        updateProductAvailability(data.data);
    }
}, (error) => {
    console.error('Inventory WebSocket error:', error);
});

// 4. Notifications
wsManager.connectToNotifications(userId, (data) => {
    if (data.type === 'notification') {
        // Show notification to user
        showToastNotification(data.data.message);
    }
}, (error) => {
    console.error('Notifications WebSocket error:', error);
});

// 5. Request current data
wsManager.sendMessage('cart', { type: 'get_cart' });
wsManager.sendMessage('orders', { type: 'get_orders' });
wsManager.sendMessage('inventory', { type: 'get_inventory' });
wsManager.sendMessage('notifications', { type: 'ping' });

// Clean up when done
wsManager.disconnect();
