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
    AdminUser.metadata.create_all(engine, tables=[AdminUser.__table__, OperationLog.__table__, ExamHistory.__table__])
    older, newer = datetime(2026, 11, 26), datetime(2026, 11, 27, 23)
    operations = {1: "login", 2: "logout", 3: "create"}
    grades = {2: "高三", 4: ""}
    with Session(engine) as session, session.begin():
        session.add_all(
            OperationLog(id=i, username="admin-a" if i % 2 else "admin-b",
                         operation=operations.get(i, "update_api_keys"), target_type="user",
                         target_name="A%_" if i % 2 else "ABC", created_at=newer if i % 2 else older)
            for i in range(1, 1201)
        )
        session.add_all(
            ExamHistory(id=i, name=f"考试{i}", grade=grades.get(i, "高一" if i % 2 else "高二"), total_score=100,
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers()) as http:
        yield http
    engine.dispose()


def headers(user="admin-a"):
    return {"Authorization": f"Bearer {user}"}


def ids(body, key):
    return [row["id"] for row in body[key]]


async def test_logs_full_count_stable_pages_and_concurrent_admins(client):
    async def page(user, number):
        return (await client.get(LOGS, headers=headers(user), params={
            "page": number, "sort": "created_at:asc", "f.username": user[-2:],
            "f.operation": "update_api_keys", "f.target_type": "user",
        })).json()

    first, second, other = await asyncio.gather(page("admin-a", 1), page("admin-a", 2), page("admin-b", 1))
    assert first["total"] == second["total"] == 598
    assert other["total"] == 599
    assert first["total_pages"] == 12
    assert ids(first, "logs") + ids(second, "logs") == list(range(1199, 999, -2))
    assert ids(other, "logs") == list(range(1200, 1100, -2))
    literal = await client.get(LOGS, params={"f.target_name": "%_", "f.created_at": "..2026-11-27"})
    assert literal.json()["total"] == 600


async def test_history_filters_before_pagination_and_preserves_zero(client):
    params = {"sort": "score_rate:asc", "f.grade": "高一", "f.score_rate": "..10", "f.exam_date": "..2026-11-27"}
    first = (await client.get(HISTORY, params=params)).json()
    second = (await client.get(HISTORY, params={**params, "offset": 50})).json()
    assert first["total"] == second["total"] == 60
    assert ids(first, "data") + ids(second, "data") == list(range(119, 0, -2))
    assert first["data"][0]["average_score"] == first["data"][0]["score_rate"] == 0


@pytest.mark.parametrize("path,items,field,total,unmatched", [
    (LOGS, "logs", "operation", 1200, {"f.operation": "delete"}),
    (HISTORY, "data", "grade", 120, {"f.name": "无匹配"}),
])
async def test_ordering_and_empty_filter(client, path, items, field, total, unmatched):
    default = (await client.get(path)).json()
    assert default["total"] == total and len(default[items]) == 50
    assert all(row["created_at"].startswith("2026-11-27") for row in default[items])
    filtered = (await client.get(path, params=unmatched)).json()
    assert filtered["has_data"] is True and filtered[items] == [] and filtered["total"] == 0

    if path == LOGS:
        params, expected, blanks = {"f.operation": "login,logout,create"}, ["login", "logout", "create"], []
    else:
        params, expected, blanks = {"limit": 120}, ["高一"] * 60 + ["高二"] * 58 + ["高三"], [""]
    for direction, step in (("asc", 1), ("desc", -1)):
        body = (await client.get(path, params={**params, "sort": f"{field}:{direction}"})).json()
        assert [row[field] for row in body[items]] == expected[::step] + blanks, direction


@pytest.mark.parametrize("path,params,user,status", [
    (LOGS, {"f.operation": "missing"}, "admin-a", 422),
    (HISTORY, {"f.grade": "高四"}, "admin-a", 422),
    (LOGS, None, "", 401),
    ("/api/auth/users", None, "editor", 403),
    (HISTORY, None, "", 200),
])
async def test_list_status(client, path, params, user, status):
    assert (await client.get(path, params=params, headers=headers(user))).status_code == status
