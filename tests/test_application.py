#!/usr/bin/env python3
"""
Application integration tests against database
"""
import requests
import psycopg2
import pytest
import time

API_URL = "http://localhost:5000"

@pytest.fixture(scope="module")
def wait_for_api():
    """Wait for API to be ready"""
    max_retries = 30
    for i in range(max_retries):
        try:
            requests.get(f"{API_URL}/health", timeout=2)
            return
        except:
            time.sleep(1)
    raise Exception("API not available")

def test_api_health(wait_for_api):
    """Test API connectivity"""
    response = requests.get(f"{API_URL}/health")
    assert response.status_code == 200
    assert response.json()['status'] == 'healthy'

def test_create_product(wait_for_api):
    """Test product creation (writes to DB)"""
    payload = {
        "name": "DevOps T-Shirt",
        "price": 29.99,
        "stock": 50,
        "sku": "DEV-001"
    }
    response = requests.post(f"{API_URL}/products", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data['name'] == payload['name']
    assert 'id' in data

def test_order_workflow(wait_for_api):
    """Test complete order flow"""
    # Create product first
    product = requests.post(f"{API_URL}/products", json={
        "name": "Kubernetes Sticker",
        "price": 5.00,
        "stock": 100,
        "sku": "K8S-001"
    }).json()
    
    # Create order
    order_payload = {
        "customer_email": "devops@example.com",
        "items": [
            {"product_id": product['id'], "quantity": 2}
        ]
    }
    order = requests.post(f"{API_URL}/orders", json=order_payload).json()
    
    assert order['total_amount'] == 10.00  # 2 * $5.00
    assert order['status'] == 'pending'
    
    # Verify in database
    conn = psycopg2.connect(
        host="localhost", port="5432", database="ecommerce",
        user="ecommerce", password="devops123"
    )
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM orders WHERE id = %s", (order['id'],))
        db_order = cur.fetchone()
        assert db_order is not None
    conn.close()