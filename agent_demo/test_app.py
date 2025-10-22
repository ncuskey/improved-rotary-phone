import pytest
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_check_isbn_valid(client):
    response = client.post('/isbn-check', json={'isbn': '978-0-306-40615-7'})
    assert response.status_code == 200
    assert response.json == {'valid': True}

def test_check_isbn_invalid(client):
    response = client.post('/isbn-check', json={})
    assert response.status_code == 400

# --- Tests for the new /calculate-score endpoint ---

def test_calculate_score_valid_isbn(client):
    """Test with a valid ISBN-13 number."""
    # ISBN for "The Pragmatic Programmer"
    response = client.post('/calculate-score', json={'isbn': '9780201616224'})
    assert response.status_code == 200
    assert response.json == {'score': 1.0}

def test_calculate_score_valid_isbn_with_hyphens(client):
    """Test with a valid ISBN-13 containing hyphens."""
    response = client.post('/calculate-score', json={'isbn': '978-3-16-148410-0'})
    assert response.status_code == 200
    assert response.json == {'score': 1.0}

def test_calculate_score_invalid_checksum(client):
    """Test with an ISBN-13 that has an incorrect checksum digit."""
    response = client.post('/calculate-score', json={'isbn': '978-3-16-148410-1'}) # Correct checksum is 0
    assert response.status_code == 200
    assert response.json == {'score': 0.0}

def test_calculate_score_invalid_length(client):
    """Test with a number that is not 13 digits long."""
    response = client.post('/calculate-score', json={'isbn': '1234567890'})
    assert response.status_code == 200
    assert response.json == {'score': 0.0}

def test_calculate_score_non_numeric(client):
    """Test with an ISBN-13 containing non-numeric characters."""
    response = client.post('/calculate-score', json={'isbn': '978-3-16-148410-X'}) # 'X' is not valid in ISBN-13
    assert response.status_code == 200
    assert response.json == {'score': 0.0}

def test_calculate_score_missing_isbn_key(client):
    """Test when the 'isbn' key is missing from the JSON payload."""
    response = client.post('/calculate-score', json={'title': 'A Book'})
    assert response.status_code == 200
    assert response.json == {'score': 0.0}

def test_calculate_score_empty_payload(client):
    """Test with an empty JSON payload."""
    response = client.post('/calculate-score', json={})
    assert response.status_code == 200
    assert response.json == {'score': 0.0}

def test_calculate_score_not_json(client):
    """Test a request with a non-JSON content type."""
    response = client.post('/calculate-score', data="not json", content_type="text/plain")
    assert response.status_code == 400
    assert 'error' in response.json
    assert response.json['error'] == 'Invalid input, JSON required'