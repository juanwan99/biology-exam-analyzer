from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from auth_router import get_db, hash_password, router
from models import AdminUser, OperationLog


@pytest.fixture
async def client():
    engine = create_engine("sqlite://")
    AdminUser.metadata.create_all(engine, tables=[AdminUser.__table__, OperationLog.__table__])
    with Session(engine) as session:
        password_hash = hash_password("test-password")
        for day, role in enumerate(("admin", "editor"), start=1):
            user = AdminUser(username=role, role=role, password_hash=password_hash)
            session.add(OperationLog(user=user, username=role, operation="update",
                                     target_type="user", created_at=datetime(2025, 1, day)))
        session.commit()

        async def override_get_db():
            return SimpleNamespace(add=session.add, execute=AsyncMock(side_effect=session.execute),
                                   commit=AsyncMock(side_effect=session.commit))

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = override_get_db
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            yield http
    engine.dispose()


async def login(client, role):
    response = await client.post("/api/auth/login", json={"username": role, "password": "test-password"})
    assert response.status_code == 200
    assert response.json()["user"]["role"] == role
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.mark.parametrize("role, status", [("editor", 403), (None, 401)])
async def test_logs_reject_non_admin(client, role, status):
    headers = await login(client, role) if role else {}
    response = await client.get("/api/auth/logs", headers=headers)
    assert response.status_code == status


async def test_admin_can_read_logs_and_paginate(client):
    headers = await login(client, "admin")
    response = await client.get("/api/auth/logs", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 3
    logs = response.json()["logs"]
    assert [(log["username"], log["operation"]) for log in logs] == [
        ("admin", "login"), ("editor", "update"), ("admin", "update"),
    ]
    second_page = await client.get("/api/auth/logs", headers=headers, params={"page": 2, "page_size": 2})
    assert second_page.status_code == 200
    assert second_page.json()["logs"] == logs[2:]


async def test_admin_can_read_empty_logs(client):
    headers = await login(client, "admin")
    response = await client.get("/api/auth/logs", headers=headers, params={"operation": "delete"})
    assert response.status_code == 200
    assert (response.json()["total"], response.json()["logs"]) == (0, [])
