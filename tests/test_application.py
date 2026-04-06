#!/usr/bin/env python3
"""
Application integration tests against database
"""
import requests
import psycopg2
import pytest
import time
import os

API_URL = os.getenv('API_URL', 'http://localhost:8080')  # Changed to 8080 for port-forward

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
        "description": "Test product"  # Changed from sku to match your schema
    }
    response = requests.post(f"{API_URL}/api/products", json=payload)  # Fixed: /api/products
    assert response.status_code == 201
    data = response.json()
    assert data['name'] == payload['name']
    assert 'id' in data

def test_order_workflow(wait_for_api):
    """Test complete order flow"""
    # Create product first
    product = requests.post(f"{API_URL}/api/products", json={
        "name": "Kubernetes Sticker",
        "price": 5.00,
        "stock": 100,
        "description": "K8s sticker"
    }).json()
    
    # Create order
    order_payload = {
        "customer_email": "devops@example.com",
        "items": [
            {"product_id": product['id'], "quantity": 2}
        ]
    }
    order_response = requests.post(f"{API_URL}/api/orders", json=order_payload)  # Fixed: /api/orders
    assert order_response.status_code == 201
    order = order_response.json()
    
    assert order['total_amount'] == 10.00  # 2 * $5.00
    assert order['status'] == 'pending'
    
    # Verify stock decreased
    product_check = requests.get(f"{API_URL}/api/products/{product['id']}")
    assert product_check.json()['stock'] == 98  # 100 - 2

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
