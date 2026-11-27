from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException
import pytest
from sqlalchemy import column, func, select, table
from sqlalchemy.dialects import postgresql

from list_query import ListColumn, apply_list_query

sample = table("sample", column("id"), column("name"), column("grade"), column("score"), column("logged"))


def compile_query(params):
    columns = {
        "name": ListColumn("text", sample.c.name),
        "grade": ListColumn("enum", sample.c.grade, ("高一", "A,B")),
        "logged": ListColumn("date", sample.c.logged),
        "score": ListColumn("number", sample.c.score),
    }
    rows, count = apply_list_query(
        select(sample).order_by(sample.c.logged.desc()),
        select(func.count(sample.c.id)), params, columns, sample.c.id.desc(),
    )
    return [stmt.compile(dialect=postgresql.dialect()) for stmt in (rows, count)]


def test_filter_bindings_and_default_order():
    rows, count = compile_query({
        "sort": "name:asc", "f.name": r"a%_\b", "f.grade": "高一,A%2CB",
        "f.logged": "..2026-11-27", "f.score": "-1.5e-2..", "f.unknown": "bad",
    })
    assert "ILIKE" in str(rows) and "ESCAPE" in str(rows)
    assert 'COLLATE "zh-Hans-CN-x-icu" ASC NULLS LAST, sample.id DESC' in str(rows)
    assert "ORDER BY" not in str(count)
    assert str(rows).split("WHERE ")[1].split(" ORDER BY")[0] == str(count).split("WHERE ")[1]
    assert list(count.params.values()) == [
        r"%a\%\_\\b%", ["高一", "A,B"], datetime(2026, 11, 27, 23, 59, 59, 999999), Decimal("-0.015"),
    ]

    rows, count = compile_query({"sort": "missing:desc", "f.missing": "bad"})
    assert str(rows).endswith("ORDER BY sample.logged DESC, sample.id DESC")
    assert "WHERE" not in str(count)


@pytest.mark.parametrize("key,value", [
    ("grade", "高一,高四"), ("logged", "2026-02-29.."), ("score", "NaN.."), ("score", "1..2..3"),
])
def test_bad_typed_filters_are_422(key, value):
    with pytest.raises(HTTPException, match="422"):
        compile_query({f"f.{key}": value})
