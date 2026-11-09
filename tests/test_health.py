from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    """Check that /health returns 200 and an 'ok' status without identity.

    SPEC section 2, Access rules, defines this public health check.
    """
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
