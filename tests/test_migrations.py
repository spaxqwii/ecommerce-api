#!/usr/bin/env python3
"""
Database migration tests
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
    """Verify products table exists"""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'products'
            );
        """)
        assert cur.fetchone()[0], "Products table should exist"

def test_orders_table_exists(db_conn):
    """Verify orders table exists"""
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'orders'
            );
        """)
        assert cur.fetchone()[0], "Orders table should exist"

def test_products_has_required_columns(db_conn):
    """Verify products table has correct columns"""
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
        assert 'stock' in columns

def test_can_insert_product(db_conn):
    """Test basic CRUD works"""
    with db_conn.cursor() as cur:
        cur.execute("""
            INSERT INTO products (name, price, stock, description)
            VALUES ('Test Product', 99.99, 10, 'Test')
            RETURNING id;
        """)
        product_id = cur.fetchone()[0]
        db_conn.commit()
        
        assert product_id is not None
        
        # Cleanup
        cur.execute("DELETE FROM products WHERE id = %s", (product_id,))
        db_conn.commit()

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
