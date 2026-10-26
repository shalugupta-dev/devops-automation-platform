
import pytest

from app import create_app, db


@pytest.fixture
def client(tmp_path):
    database_path = tmp_path / "test.db"

    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": (
            f"sqlite:///{database_path.as_posix()}"
        ),
    })

    with app.app_context():
        db.create_all()

    with app.test_client() as test_client:
        yield test_client

    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_home(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "DevOps Automation" in response.json["project"]


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json["status"] == "healthy"


def test_create_deployment(client):
    response = client.post(
        "/api/deployments",
        json={
            "project_name": "demo-api",
            "version": "v1",
        },
    )

    assert response.status_code == 201
    assert response.json["project_name"] == "demo-api"
    assert response.json["status"] == "queued"


def test_reject_missing_version(client):
    response = client.post(
        "/api/deployments",
        json={"project_name": "demo-api"},
    )

    assert response.status_code == 400


def test_reject_invalid_json(client):
    response = client.post(
        "/api/deployments",
        data="invalid",
        content_type="text/plain",
    )

    assert response.status_code == 400


def test_list_deployments(client):
    client.post(
        "/api/deployments",
        json={"project_name": "demo-api", "version": "v1"},
    )

    response = client.get("/api/deployments")

    assert response.status_code == 200
    assert len(response.json) == 1
