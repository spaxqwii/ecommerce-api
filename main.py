
from flask import Flask, request, jsonify
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
import os
from psycopg2.extras import RealDictCursor
import logging
import json
from flask import request, g
import time
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# [NEW] Import Prometheus metrics library
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)

# [NEW] Track when app started for uptime calculation
start_time = time.time()

# [NEW] Define Prometheus metrics (these track data over time)
REQUEST_COUNT = Counter(
    'http_requests_total', 
    'Total HTTP requests', 
    ['method', 'endpoint', 'status']  # Labels to categorize requests
)
REQUEST_DURATION = Histogram(
    'http_request_duration_seconds', 
    'HTTP request duration',
    ['method', 'endpoint']
)
PRODUCT_COUNT = Gauge(
    'products_total', 
    'Total number of products in database'
)
ORDER_COUNT = Gauge(
    'orders_total', 
    'Total number of orders in database'
)
UPTIME = Gauge(
    'uptime_seconds', 
    'API uptime in seconds'
)

# Initialize connection pool (global, created once)
pool = None

def init_pool():
    """Initialize database connection pool"""
    global pool
    if pool is None:
        # ❌ NO FALLBACKS - fail fast if env vars missing
        pool = ThreadedConnectionPool(
            minconn=2,
            maxconn=10,
            host=os.environ['DB_HOST'],        # Will crash if not set (good!)
            port=os.environ.get('DB_PORT', '5432'),
            database=os.environ['DB_NAME'],
            user=os.environ['DB_USER'],
            password=os.environ['DB_PASSWORD']   # Will crash if not set (good!)
        )

def get_db_connection():
    """Get connection from pool"""
    init_pool()
    return pool.getconn()

def release_db_connection(conn):
    """Return connection to pool (DON'T close it!)"""
    if pool:
        pool.putconn(conn)

# [NEW] Helper function to update gauges from database
def update_gauges():
    """Update Prometheus gauges with current database counts"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM products')
        PRODUCT_COUNT.set(cur.fetchone()[0])
        cur.execute('SELECT COUNT(*) FROM orders')
        ORDER_COUNT.set(cur.fetchone()[0])
        cur.close()
        release_db_connection(conn)  # ✅ Return to pool, don't close!
    except Exception as e:
        logger.error(f"Failed to update gauges: {e}")

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per minute", "1000 per hour"]
)

@app.route('/')
def home():
    return jsonify({
        "message": "Welcome to Ecommerce API",
        "status": "running",
        "version": "1.0"
    })

# [ENHANCED] Health check with component status
@app.route('/health')
def health():
    """Liveness probe - is the application running?"""
    checks = {
        'api': 'healthy',
        'database': 'unknown',
        'timestamp': time.time()
    }
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('SELECT 1')
        release_db_connection(conn)  # ✅ Return to pool!
        checks['database'] = 'connected'
        status = 200
    except Exception as e:
        checks['database'] = f'disconnected: {str(e)}'
        status = 503  # Service Unavailable
    
    return jsonify(checks), status

# [NEW] Readiness probe - can this pod receive traffic?
@app.route('/ready')
def readiness():
    """Readiness probe - is the pod ready to handle requests?"""
    try:
        conn = get_db_connection()
        release_db_connection(conn)  # ✅ Return to pool!
        return jsonify({'ready': True}), 200
    except:
        return jsonify({'ready': False}), 503

# [NEW] Prometheus metrics endpoint
@app.route('/metrics')
def metrics():
    """Prometheus-compatible metrics endpoint for monitoring systems"""
    UPTIME.set(time.time() - start_time)  # Update uptime gauge
    update_gauges()  # Refresh product/order counts from DB
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

# [NEW] Simple business metrics endpoint (JSON format)
@app.route('/api/metrics')
def api_metrics():
    """JSON metrics endpoint for quick health checks"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM products')
        products_total = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM orders')
        orders_total = cur.fetchone()[0]
        cur.close()
        release_db_connection(conn)  # ✅ Return to pool!
        
        return jsonify({
            "products_total": products_total,
            "orders_total": orders_total,
            "uptime_seconds": round(time.time() - start_time, 2),
            "status": "healthy"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ========== PRODUCTS ==========
@app.route('/api/products', methods=['GET'])
def get_products():
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT * FROM products ORDER BY id')
        products = cur.fetchall()
        cur.close()
        return jsonify({"products": products})
    finally:
        release_db_connection(conn)  # ✅ RETURNS TO POOL

@app.route('/api/products/<int:id>', methods=['GET'])
def get_product(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM products WHERE id = %s', (id,))
    product = cur.fetchone()
    cur.close()
    conn.close()
    if product:
        return jsonify(product)
    return jsonify({"error": "Product not found"}), 404

@app.route('/api/products', methods=['POST'])
def create_product():
    data = request.get_json()
    
    if isinstance(data, list):
        created_products = []
        conn = get_db_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            for item in data:
                cur.execute(
                    'INSERT INTO products (name, description, price, stock) VALUES (%s, %s, %s, %s) RETURNING *',
                    (item['name'], item.get('description', ''), item['price'], item.get('stock', 0))
                )
                new_product = cur.fetchone()
                created_products.append(dict(new_product))
            conn.commit()
            return jsonify({"products": created_products, "count": len(created_products)}), 201
        except Exception as e:
            conn.rollback()
            return jsonify({"error": str(e)}), 400
        finally:
            cur.close()
            conn.close()
    else:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            'INSERT INTO products (name, description, price, stock) VALUES (%s, %s, %s, %s) RETURNING *',
            (data['name'], data.get('description', ''), data['price'], data.get('stock', 0))
        )
        new_product = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return jsonify(new_product), 201

@app.route('/api/products/<int:id>', methods=['PUT'])
def update_product(id):
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute('SELECT * FROM products WHERE id = %s', (id,))
        existing = cur.fetchone()
        if not existing:
            return jsonify({"error": "Product not found"}), 404
        
        name = data.get('name', existing['name'])
        description = data.get('description', existing['description'])
        price = data.get('price', existing['price'])
        stock = data.get('stock', existing['stock'])
        
        if price is None or name is None:
            return jsonify({"error": "Name and price cannot be null"}), 400
        
        cur.execute(
            'UPDATE products SET name=%s, description=%s, price=%s, stock=%s WHERE id=%s RETURNING *',
            (name, description, price, stock, id)
        )
        updated = cur.fetchone()
        conn.commit()
        return jsonify(updated)
        
    except psycopg2.Error as e:
        conn.rollback()
        return jsonify({"error": f"Database error: {str(e)}"}), 500
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/api/products/<int:id>', methods=['DELETE'])
def delete_product(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute('SELECT * FROM products WHERE id = %s', (id,))
    if not cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"error": "Product not found"}), 404
    
    cur.execute('SELECT COUNT(*) as order_count FROM order_items WHERE product_id = %s', (id,))
    result = cur.fetchone()
    if result['order_count'] > 0:
        cur.close()
        conn.close()
        return jsonify({"error": "Cannot delete product - used in existing orders"}), 400
    
    cur.execute('DELETE FROM products WHERE id = %s RETURNING id', (id,))
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"message": f"Product {id} deleted", "id": deleted['id']})

# ========== ORDERS ==========
@app.route('/api/orders', methods=['GET'])
def get_orders():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM orders ORDER BY created_at DESC')
    orders = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({"orders": orders, "count": len(orders)})

@app.route('/api/orders/<int:id>', methods=['GET'])
def get_order(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute('SELECT * FROM orders WHERE id = %s', (id,))
    order = cur.fetchone()
    
    if not order:
        cur.close()
        conn.close()
        return jsonify({"error": "Order not found"}), 404
    
    cur.execute('''
        SELECT oi.*, p.name as product_name 
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = %s
    ''', (id,))
    items = cur.fetchall()
    
    cur.close()
    conn.close()
    return jsonify({"order": order, "items": items})

@app.route('/api/orders', methods=['POST'])
def create_order():
    data = request.get_json()
    
    if isinstance(data, list):
        created_orders = []
        errors = []
        for index, order_data in enumerate(data):
            try:
                order = _process_single_order(order_data)
                created_orders.append(order)
            except Exception as e:
                errors.append({"index": index, "error": str(e)})
        
        if errors:
            return jsonify({"orders": created_orders, "errors": errors}), 207
        return jsonify({"orders": created_orders, "count": len(created_orders)}), 201
    else:
        try:
            order = _process_single_order(data)
            return jsonify(order), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 400

def _process_single_order(data):
    """Process a single order with inventory tracking"""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if 'items' not in data or not data['items']:
                raise ValueError("Order must contain items")
            if 'customer_email' not in data:
                raise ValueError("Order must have customer_email")
            
            total = 0
            for item in data['items']:
                cur.execute("SELECT price, stock FROM products WHERE id = %s", (item['product_id'],))
                product = cur.fetchone()
                if not product:
                    raise ValueError(f"Product {item['product_id']} not found")
                if product['stock'] < item['quantity']:
                    raise ValueError(f"Insufficient stock for product {item['product_id']}")
                total += product['price'] * item['quantity']
            
            cur.execute("""
                INSERT INTO orders (customer_email, total_amount, status)
                VALUES (%s, %s, 'pending')
                RETURNING *;
            """, (data['customer_email'], total))
            order = cur.fetchone()
            
            for item in data['items']:
                cur.execute("""
                    INSERT INTO order_items (order_id, product_id, quantity, price_at_time)
                    VALUES (%s, %s, %s, (SELECT price FROM products WHERE id = %s));
                """, (order['id'], item['product_id'], item['quantity'], item['product_id']))
                
                cur.execute("""
                    UPDATE products SET stock = stock - %s WHERE id = %s;
                """, (item['quantity'], item['product_id']))
                
                cur.execute("""
                    INSERT INTO inventory_logs (product_id, quantity_change, reason)
                    VALUES (%s, %s, %s);
                """, (item['product_id'], -item['quantity'], f'Order {order["id"]} placed'))
            
            conn.commit()
            return dict(order)
            
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# ========== USERS ==========
@app.route('/api/users', methods=['GET'])
def get_users():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('''
        SELECT 
            u.id, u.username, u.email, u.created_at,
            COUNT(o.id) as total_orders,
            COALESCE(SUM(o.total_amount), 0) as total_spent
        FROM users u
        LEFT JOIN orders o ON u.id = o.user_id
        GROUP BY u.id
        ORDER BY u.id
    ''')
    users = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({"users": users})

# [ENHANCED] Configure JSON logging with request tracking
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

@app.before_request
def start_timer():
    g.start = time.time()

@app.after_request
def log_request(response):
    """Log request details and track in Prometheus metrics"""
    if hasattr(g, 'start'):
        duration = time.time() - g.start
        
        # [NEW] Track request in Prometheus
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.path,
            status=response.status_code
        ).inc()  # Increment counter
        
        REQUEST_DURATION.labels(
            method=request.method,
            endpoint=request.path
        ).observe(duration)  # Record duration
        
        # Log to stdout (collected by Kubernetes)
        log_data = {
            'method': request.method,
            'path': request.path,
            'status': response.status_code,
            'duration_ms': round(duration * 1000, 2),
            'remote_addr': request.remote_addr
        }
        logger.info(json.dumps(log_data))
    return response

@app.errorhandler(Exception)
def handle_error(error):
    logger.error(f"Error: {str(error)}", exc_info=True)
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
