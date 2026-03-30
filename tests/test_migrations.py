#!/usr/bin/env python3
"""
Database migration tests
Tests that migrations run correctly and maintain data integrity
"""
import pytest
import psycopg2
import os
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'database': os.getenv('DB_NAME', 'ecommerce'),
    'user': os.getenv('DB_USER', 'ecommerce'),
    'password': os.getenv('DB_PASSWORD', 'devops123')
}

@pytest.fixture
def db_conn():
    """Database connection fixture"""
    conn = psycopg2.connect(**DB_CONFIG)
    yield conn
    conn.close()

def test_products_table_exists(db_conn):
    """Verify products table was created by migration"""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'products'
            );
        """)
        assert cur.fetchone()[0], "Products table should exist"

def test_products_has_required_columns(db_conn):
    """Verify products table has correct schema"""
    with db_conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'products'
            ORDER BY ordinal_position;
        """)
        columns = {row['column_name']: row['data_type'] for row in cur.fetchall()}
        
        assert 'id' in columns
        assert 'name' in columns
        assert 'price' in columns
        assert columns['price'] in ['numeric', 'decimal']

def test_foreign_key_constraints(db_conn):
    """Verify referential integrity constraints"""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT tc.constraint_name, kcu.column_name, ccu.table_name AS foreign_table
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_name = 'order_items';
        """)
        constraints = cur.fetchall()
        assert len(constraints) > 0, "Order items should have FK constraints"

def test_index_performance(db_conn):
    """Verify indexes exist for query performance"""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE tablename IN ('orders', 'order_items')
              AND indexname LIKE 'idx_%';
        """)
        indexes = cur.fetchall()
        index_names = [idx[0] for idx in indexes]
        
        assert 'idx_orders_status' in index_names
        assert 'idx_order_items_order_id' in index_names

def test_data_integrity_on_rollback(db_conn):
    """Test that transactions maintain integrity (simulates rollback scenario)"""
    with db_conn.cursor() as cur:
        # Start transaction
        cur.execute("BEGIN;")
        
        try:
            # Insert test product
            cur.execute("""
                INSERT INTO products (name, price, stock, sku) 
                VALUES ('Test Product', 99.99, 100, 'TEST-001')
                RETURNING id;
            """)
            product_id = cur.fetchone()[0]
            
            # Insert order
            cur.execute("""
                INSERT INTO orders (customer_email, total_amount, status)
                VALUES ('test@example.com', 99.99, 'completed')
                RETURNING id;
            """)
            order_id = cur.fetchone()[0]
            
            # Insert order item
            cur.execute("""
                INSERT INTO order_items (order_id, product_id, quantity, price_at_time)
                VALUES (%s, %s, 1, 99.99);
            """, (order_id, product_id))
            
            # Verify data exists
            cur.execute("SELECT COUNT(*) FROM order_items WHERE order_id = %s", (order_id,))
            count = cur.fetchone()[0]
            assert count == 1
            
            # Rollback (simulates failed migration)
            cur.execute("ROLLBACK;")
            
        except Exception as e:
            cur.execute("ROLLBACK;")
            raise e

if __name__ == '__main__':
    pytest.main([__file__, '-v'])