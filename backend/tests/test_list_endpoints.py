import asyncio
from datetime import datetime
from unittest.mock import AsyncMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import auth_router
import prediction_router
from database import get_db
from models import AdminUser, ExamHistory, OperationLog

LOGS = "/api/auth/logs"
HISTORY = "/api/prediction/history"


@pytest.fixture
async def client(monkeypatch):
    engine = create_engine("sqlite://")
    for model in (AdminUser, OperationLog, ExamHistory):
        model.__table__.create(engine)
    older, newer = datetime(2026, 11, 26), datetime(2026, 11, 27, 23)
    with Session(engine) as session, session.begin():
        session.add_all(
            OperationLog(id=i, username="admin-a" if i % 2 else "admin-b",
                         operation="update_api_keys", target_type="user",
                         target_name="A%_" if i % 2 else "ABC", created_at=newer if i % 2 else older)
            for i in range(1, 1201)
        )
        session.add_all(
            ExamHistory(id=i, name=f"考试{i}", grade="高一" if i % 2 else "高二", total_score=100,
                        average_score=0 if i % 2 else 50, score_rate=0 if i % 2 else 0.5,
                        exam_date=newer, created_at=newer if i % 2 else older)
            for i in range(1, 121)
        )

    async def db():
        with Session(engine) as session:
            yield AsyncMock(execute=AsyncMock(side_effect=session.execute))

    users = {key: {"username": key, "role": role} for key, role in
             [("admin-a", "admin"), ("admin-b", "admin"), ("editor", "editor")]}
    monkeypatch.setattr(auth_router, "get_current_user", users.get)
    app = FastAPI()
    app.include_router(auth_router.router)
    app.include_router(prediction_router.router)
    app.dependency_overrides[get_db] = db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    engine.dispose()


def headers(user="admin-a"):
    return {"Authorization": f"Bearer {user}"}


def ids(body, key):
    return [row["id"] for row in body[key]]


async def test_logs_full_count_stable_pages_and_concurrent_admins(client):
    async def page(user, number):
        response = await client.get(LOGS, headers=headers(user), params={
            "page": number, "sort": "created_at:asc", "f.username": user[-2:],
            "f.operation": "update_api_keys", "f.target_type": "user",
        })
        assert response.status_code == 200
        return response.json()

    first, second, other = await asyncio.gather(page("admin-a", 1), page("admin-a", 2), page("admin-b", 1))
    assert first["total"] == second["total"] == other["total"] == 600
    assert first["total_pages"] == 12
    assert ids(first, "logs") + ids(second, "logs") == list(range(1199, 999, -2))
    assert ids(other, "logs") == list(range(1200, 1100, -2))
    literal = await client.get(LOGS, headers=headers(), params={"f.target_name": "%_", "f.created_at": "..2026-11-27"})
    assert literal.json()["total"] == 600


async def test_history_filters_before_pagination_and_preserves_zero(client):
    params = {"sort": "score_rate:asc", "f.grade": "高一", "f.score_rate": "..10", "f.exam_date": "..2026-11-27"}
    first = (await client.get(HISTORY, params=params)).json()
    second = (await client.get(HISTORY, params={**params, "offset": 50})).json()
    assert first["total"] == second["total"] == 60
    assert ids(first, "data") + ids(second, "data") == list(range(119, 0, -2))
    assert first["data"][0]["average_score"] == first["data"][0]["score_rate"] == 0


@pytest.mark.parametrize("path,key,total", [(LOGS, "logs", 1200), (HISTORY, "data", 120)])
async def test_default_descending(client, path, key, total):
    default = (await client.get(path, headers=headers())).json()
    assert default["total"] == total and len(default[key]) == 50
    assert all(row["created_at"].startswith("2026-11-27") for row in default[key])
    field = "username" if path == LOGS else "name"
    filtered = (await client.get(path, headers=headers(), params={f"f.{field}": "无匹配"})).json()
    assert filtered["has_data"] is True and filtered["total"] == 0


@pytest.mark.parametrize("path,key,value", [
    (LOGS, "operation", "missing"), (LOGS, "created_at", "invalid.."),
    (HISTORY, "grade", "高四"), (HISTORY, "average_score", "bad.."), (HISTORY, "exam_date", "bad.."),
])
async def test_invalid_list_values(client, path, key, value):
    response = await client.get(path, headers=headers(), params={f"f.{key}": value})
    assert response.status_code == 422


async def test_existing_roles(client):
    assert (await client.get(LOGS)).status_code == 401
    assert (await client.get(LOGS, headers=headers("editor"))).status_code == 200
    assert (await client.get("/api/auth/users", headers=headers("editor"))).status_code == 403
    assert (await client.get(HISTORY)).status_code == 200
