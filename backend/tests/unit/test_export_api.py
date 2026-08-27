"""Unit tests for the export API endpoint."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_session
from app.main import app
from app.models.database import ConnectionStatus, DatabaseConnection
from app.models.schemas import QueryColumn, QueryResult
from app.services.sql_validator import SqlValidationError


@pytest.fixture
def test_session():
    """Create an in-memory SQLite session for testing."""
    engine = create_engine(
        "sqlite:///file:test_export_db?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False, "uri": True},
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def client(test_session):
    """Create TestClient with test database session."""

    def get_test_session():
        return test_session

    app.dependency_overrides[get_session] = get_test_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def sample_connection(test_session):
    """Create a sample database connection."""
    conn = DatabaseConnection(
        name="test_db",
        url="postgresql://user:pass@localhost/testdb",
        description="Test database",
        status=ConnectionStatus.ACTIVE,
        last_connected_at=datetime.now(UTC).replace(tzinfo=None),
    )
    test_session.add(conn)
    test_session.commit()
    test_session.refresh(conn)
    return conn


def _fake_result():
    return QueryResult(
        columns=[
            QueryColumn(name="id", dataType="integer"),
            QueryColumn(name="name", dataType="character varying"),
        ],
        rows=[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
        rowCount=2,
        executionTimeMs=10,
        sql="SELECT id, name FROM users",
    )


def test_export_csv_success(client, sample_connection):
    with patch(
        "app.api.v1.export.execute_query_with_service",
        new_callable=AsyncMock,
        return_value=_fake_result(),
    ):
        response = client.post(
            "/api/v1/dbs/test_db/export",
            json={"sql": "SELECT id, name FROM users", "format": "csv"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["content-disposition"].endswith('.csv"')
    assert response.headers["x-export-row-count"] == "2"
    assert response.text.startswith("\ufeff")
    assert "id,name" in response.text
    assert "Alice" in response.text


def test_export_json_success(client, sample_connection):
    with patch(
        "app.api.v1.export.execute_query_with_service",
        new_callable=AsyncMock,
        return_value=_fake_result(),
    ):
        response = client.post(
            "/api/v1/dbs/test_db/export",
            json={"sql": "SELECT id, name FROM users", "format": "json"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-disposition"].endswith('.json"')
    parsed = json.loads(response.text)
    assert len(parsed) == 2
    assert parsed[0]["name"] == "Alice"


def test_export_format_defaults_to_csv(client, sample_connection):
    with patch(
        "app.api.v1.export.execute_query_with_service",
        new_callable=AsyncMock,
        return_value=_fake_result(),
    ):
        response = client.post(
            "/api/v1/dbs/test_db/export",
            json={"sql": "SELECT id, name FROM users"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")


def test_export_connection_not_found(client):
    response = client.post(
        "/api/v1/dbs/unknown_db/export",
        json={"sql": "SELECT 1", "format": "csv"},
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_export_sql_validation_error(client, sample_connection):
    with patch(
        "app.api.v1.export.execute_query_with_service",
        new_callable=AsyncMock,
        side_effect=SqlValidationError("Only SELECT statements are allowed"),
    ):
        response = client.post(
            "/api/v1/dbs/test_db/export",
            json={"sql": "DELETE FROM users", "format": "csv"},
        )

    assert response.status_code == 400
    assert "Only SELECT" in response.json()["detail"]


def test_export_execution_error(client, sample_connection):
    with patch(
        "app.api.v1.export.execute_query_with_service",
        new_callable=AsyncMock,
        side_effect=RuntimeError("connection refused"),
    ):
        response = client.post(
            "/api/v1/dbs/test_db/export",
            json={"sql": "SELECT * FROM missing", "format": "csv"},
        )

    assert response.status_code == 500
    assert "failed" in response.json()["detail"]
