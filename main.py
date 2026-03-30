from flask import Flask, request, jsonify
import psycopg2
import os
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'ecommerce-db-postgresql'),
        port=os.getenv('DB_PORT', '5432'),
        database=os.getenv('DB_NAME', 'ecommerce'),
        user=os.getenv('DB_USER', 'ecommerce'),
        password=os.getenv('DB_PASSWORD', 'devops123')
    )

@app.route('/')
def home():
    return jsonify({
        "message": "Welcome to Ecommerce API",
        "status": "running",
        "version": "1.0"
    })

@app.route('/health')
def health():
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('SELECT 1')
        conn.close()
        return jsonify({'status': 'healthy', 'database': 'connected'})
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

# ========== PRODUCTS ==========
@app.route('/api/products', methods=['GET'])
def get_products():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM products ORDER BY id')
    products = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({"products": products})

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
    
    # Handle bulk creation (list of products)
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
    
    # Handle single product creation
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
    
    # Validate that we actually got data
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Check if product exists
        cur.execute('SELECT * FROM products WHERE id = %s', (id,))
        existing = cur.fetchone()
        if not existing:
            return jsonify({"error": "Product not found"}), 404
        
        # Use existing values as defaults if not provided
        name = data.get('name', existing['name'])
        description = data.get('description', existing['description'])
        price = data.get('price', existing['price'])
        stock = data.get('stock', existing['stock'])
        
        # Validate required fields aren't null
        if price is None or name is None:
            return jsonify({"error": "Name and price cannot be null"}), 400
        
        # Update product
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
    
    # Check if product exists
    cur.execute('SELECT * FROM products WHERE id = %s', (id,))
    if not cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"error": "Product not found"}), 404
    
    # Check if product is used in orders
    cur.execute('SELECT COUNT(*) as order_count FROM order_items WHERE product_id = %s', (id,))
    result = cur.fetchone()
    if result['order_count'] > 0:
        cur.close()
        conn.close()
        return jsonify({"error": "Cannot delete product - used in existing orders"}), 400
    
    # Delete product
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
    
    # Get order
    cur.execute('SELECT * FROM orders WHERE id = %s', (id,))
    order = cur.fetchone()
    
    if not order:
        cur.close()
        conn.close()
        return jsonify({"error": "Order not found"}), 404
    
    # Get order items
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
    
    # Handle bulk orders
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
            # Validate
            if 'items' not in data or not data['items']:
                raise ValueError("Order must contain items")
            if 'customer_email' not in data:
                raise ValueError("Order must have customer_email")
            
            # Calculate total and validate stock
            total = 0
            for item in data['items']:
                cur.execute("SELECT price, stock FROM products WHERE id = %s", (item['product_id'],))
                product = cur.fetchone()
                if not product:
                    raise ValueError(f"Product {item['product_id']} not found")
                if product['stock'] < item['quantity']:
                    raise ValueError(f"Insufficient stock for product {item['product_id']}")
                total += product['price'] * item['quantity']
            
            # Create order
            cur.execute("""
                INSERT INTO orders (customer_email, total_amount, status)
                VALUES (%s, %s, 'pending')
                RETURNING *;
            """, (data['customer_email'], total))
            order = cur.fetchone()
            
            # Create order items and update inventory
            for item in data['items']:
                # Add order item
                cur.execute("""
                    INSERT INTO order_items (order_id, product_id, quantity, price_at_time)
                    VALUES (%s, %s, %s, (SELECT price FROM products WHERE id = %s));
                """, (order['id'], item['product_id'], item['quantity'], item['product_id']))
                
                # Update product stock
                cur.execute("""
                    UPDATE products SET stock = stock - %s WHERE id = %s;
                """, (item['quantity'], item['product_id']))
                
                # Log inventory change
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)