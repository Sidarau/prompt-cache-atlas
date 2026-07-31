import pytest
import json
import sys
sys.path.insert(0, '.')

from app import app, hash_prompt, cosine_similarity

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health(client):
    rv = client.get('/api/health')
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert data['status'] == 'ok'
    assert 'cached_entries' in data

def test_workspaces(client):
    rv = client.get('/api/workspaces')
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert 'workspaces' in data
    assert isinstance(data['workspaces'], list)

def test_stats(client):
    rv = client.get('/api/stats?workspace=clawpanel')
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert 'total_cached' in data
    assert 'hit_rate_percent' in data
    assert 'tokens_saved' in data

def test_cache_check_hit(client):
    rv = client.post('/api/cache/check', json={
        'prompt': 'What are the 15 rules to reduce AI token consumption?',
        'workspace': 'clawpanel'
    })
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert data['cached'] == True
    assert 'response' in data

def test_cache_check_miss(client):
    rv = client.post('/api/cache/check', json={
        'prompt': 'Something completely unrelated xyz123',
        'workspace': 'clawpanel'
    })
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert data['cached'] == False
    assert 'prompt_hash' in data

def test_cache_store(client):
    rv = client.post('/api/cache/store', json={
        'prompt': 'Test prompt for pytest',
        'response': 'Test response',
        'tokens_in': 100,
        'tokens_out': 50,
        'workspace': 'test'
    })
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert data['stored'] == True

def test_sop_store_and_get(client):
    # Store SOP
    rv = client.post('/api/sop/store', json={
        'name': 'Test SOP',
        'content': 'This is a test SOP for pytest',
        'workspace': 'test'
    })
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert data['stored'] == True
    sop_hash = data['sop_hash']
    
    # Get SOP
    rv = client.get(f'/api/sop/get?hash={sop_hash}&workspace=test')
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert data['found'] == True
    assert 'content' in data

def test_hash_prompt():
    h1 = hash_prompt('test prompt')
    h2 = hash_prompt('test prompt')
    h3 = hash_prompt('different prompt')
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 32

def test_cosine_similarity():
    a = [1, 0, 0]
    b = [1, 0, 0]
    c = [0, 1, 0]
    assert cosine_similarity(a, b) == 1.0
    assert cosine_similarity(a, c) == 0.0
    assert 0 < cosine_similarity([1, 1, 0], [1, 0, 1]) < 1
