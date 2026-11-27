import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

import auth_router
import exercise_router
import prediction_router
import textbook_router
from database import get_db
from models import AdminUser, ExamHistory, OperationLog

LOGS = "/api/auth/logs"
HISTORY = "/api/prediction/history"
EXERCISES = "/api/exercises/list"
CHUNKS = "/api/textbook/contents/list"


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


@pytest.fixture
async def card_lists():
    app = FastAPI()
    app.include_router(exercise_router.router)
    app.include_router(textbook_router.router)
    queries = []
    chunk = (12, None, "bx1", 1, "教材正文", None, None, datetime(2026, 11, 27), None)

    async def db():
        async def execute(stmt):
            compiled = stmt.compile(dialect=postgresql.dialect())
            queries.append((" ".join(str(compiled).split()), list(compiled.params.values())))
            empty = "%无匹配%" in compiled.params.values()
            result = Mock()
            result.scalar.return_value = 0 if empty else 42
            result.fetchall.return_value = [] if empty else [chunk]
            result.scalars.return_value.unique.return_value.all.return_value = []
            return result

        yield SimpleNamespace(execute=execute)

    app.dependency_overrides[get_db] = db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, queries


@pytest.mark.parametrize("path,sort,expression,bindings,stable", [
    (EXERCISES, "year:desc", "AS INTEGER) DESC", ["year"], "exercise_bank.id DESC"),
    (EXERCISES, "year:asc", "AS INTEGER) ASC", ["year"], "exercise_bank.id DESC"),
    (EXERCISES, "question_type:asc", "CASE exercise_bank.question_type", ["单选题", 0, "多选题", 1, "填空题", 2, "简答题", 3], "exercise_bank.id DESC"),
    (EXERCISES, "exam_source:asc", 'COLLATE "zh-Hans-CN-x-icu" ASC', ["exam_source", ""], "exercise_bank.id DESC"),
    (EXERCISES, "created_at:desc", "exercise_bank.created_at DESC", [], "exercise_bank.id DESC"),
    (CHUNKS, "page_num:asc", "textbook_chunks.page_num ASC", [], "textbook_chunks.id ASC"),
    (CHUNKS, "page_num:desc", "textbook_chunks.page_num DESC", [], "textbook_chunks.id ASC"),
    (CHUNKS, "created_at:desc", "textbook_chunks.created_at DESC", [], "textbook_chunks.id ASC"),
])
async def test_card_ordering_applies_to_each_page(card_lists, path, sort, expression, bindings, stable):
    http, queries = card_lists
    for page, offset in [(1, 0), (2, 20)]:
        response = await http.get(path, params={"sort": sort, "page": page, "page_size": 20})
        assert response.status_code == 200
        body = response.json()
        assert (body["total"], body["page"], body["page_size"], body["total_pages"]) == (42, page, 20, 3)
        count, rows = queries[-2:]
        assert "ORDER BY" not in count[0] and count[1] == []
        order = rows[0].partition("ORDER BY ")[2].partition(" LIMIT ")[0]
        assert expression in order
        assert order.endswith(f"NULLS LAST, {stable}")
        assert rows[1] == bindings + [20, offset]


@pytest.mark.parametrize("path,expected_order", [
    (EXERCISES, ["exercise_bank.id DESC"]),
    # Chunks retain ID DESC by default and append the stable key ID ASC.
    (CHUNKS, ["textbook_chunks.id DESC", "textbook_chunks.id ASC"]),
])
async def test_card_default_unknown_sort_and_roles(card_lists, path, expected_order):
    http, queries = card_lists
    default, unknown = await asyncio.gather(http.get(path), http.get(
        path, params={"sort": "unknown:asc"}, headers=headers("editor"),
    ))
    assert default.status_code == unknown.status_code == 200
    assert default.json() == unknown.json()
    orders = [
        sql.split("ORDER BY ")[1].split(" LIMIT ")[0].split(", ")
        for sql, _ in queries if "ORDER BY " in sql
    ]
    assert orders == [expected_order, expected_order]
    if path == CHUNKS:
        assert default.json()["items"] == [{
            "id": 12, "page_id": None, "book_id": "bx1", "chunk_index": 1, "content": "教材正文",
            "page_num": None, "chapter_info": None, "created_at": "2026-11-27T00:00:00", "book_name": None,
        }]


@pytest.mark.parametrize("path,params,predicates,values,empty_pages", [
    (EXERCISES, {"question_type": "单选题", "year": 2024, "source_type": "高考", "difficulty_min": 0,
                 "difficulty_max": 0.6, "tag": "细胞", "keyword": "无匹配"},
     ["exercise_bank.question_type =", "competency_scores->>'year' = '2024'", "exercise_sources.source_type =",
      "exercise_bank.difficulty_level >=", "exercise_bank.difficulty_level <=", "ANY (exercise_bank.tags)",
      "exercise_bank.content ILIKE"], ["单选题", 0, 0.6, "细胞", "%无匹配%", "高考"], 0),
    (CHUNKS, {"book_id": "bx1", "keyword": "无匹配"}, ["textbook_chunks.book_id =", "textbook_chunks.chunk_content ILIKE"],
     ["bx1", "%无匹配%"], 1),
])
async def test_card_legacy_filters_affect_rows_and_count(card_lists, path, params, predicates, values, empty_pages):
    http, queries = card_lists
    assert (await http.get(path, params={**params, "sort": "created_at:desc"})).json() == {
        **({"success": True} if path == CHUNKS else {}),
        "items": [], "total": 0, "page": 1, "page_size": 50 if path == CHUNKS else 20, "total_pages": empty_pages,
    }
    count, rows = queries
    for sql, binds in (count, rows):
        where = sql.partition(" WHERE ")[2].partition(" ORDER BY ")[0]
        assert all(predicate in where for predicate in predicates)
        assert binds[:len(values)] == values


async def test_invalid_card_year_filter_is_422(card_lists):
    http, queries = card_lists
    response = await http.get(EXERCISES, params={"f.year": "abc"})
    assert response.status_code == 422
    assert response.json() == {"detail": "筛选值无效（year）"}
    assert queries == []
