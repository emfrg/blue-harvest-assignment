from fastapi.testclient import TestClient

from app.main import app


def test_health():
    """Check that /health returns 200 and an 'ok' status without identity."""
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
