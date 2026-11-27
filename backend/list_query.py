from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from math import isfinite
import re
from urllib.parse import unquote

from fastapi import HTTPException
from sqlalchemy import case, func
from sqlalchemy.sql import ColumnElement


@dataclass(frozen=True)
class ListColumn:
    type: str
    expr: ColumnElement
    values: tuple[str, ...] | dict[str, str] | None = None


def _predicate(column, value):
    expr = column.expr
    if column.type == "text":
        escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return [expr.ilike(f"%{escaped}%", escape="\\")] if value else []

    if column.type == "enum":
        # Each item is URI-encoded before joining, after the request decoding.
        items = [unquote(item, errors="strict") for item in value.split(",")]
        if any(item not in (column.values or ()) for item in items):
            raise ValueError
        return [expr.in_(items)]

    start, end = value.split("..")
    predicates = []
    for bound, upper in ((start, False), (end, True)):
        if not bound:
            continue
        if column.type == "date":
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", bound):
                raise ValueError
            bound = datetime.combine(date.fromisoformat(bound), time.max if upper else time.min)
        else:
            if not re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", bound):
                raise ValueError
            bound = Decimal(bound)
            if not isfinite(bound):
                raise ValueError
        predicates.append(expr <= bound if upper else expr >= bound)
    return predicates


def apply_list_query(stmt, count_stmt, params, columns, stable):
    """Use caller-supplied SQL expressions and append a unique pagination key."""
    predicates = []
    for param, value in params.items():
        if param.startswith("f.") and (column := columns.get(param[2:])) is not None:
            try:
                predicates.extend(_predicate(column, value))
            except (ValueError, InvalidOperation) as exc:
                raise HTTPException(422, detail=f"筛选值无效（{param[2:]}）") from exc

    key, _, direction = params.get("sort", "").rpartition(":")
    if key in columns and direction in ("asc", "desc"):
        column = columns[key]
        expr = column.expr
        if column.type == "text":
            expr = func.nullif(expr, "").collate("zh-Hans-CN-x-icu")
        elif column.type == "enum":
            expr = case({value: index for index, value in enumerate(column.values)}, value=expr)
        order = expr.asc() if direction == "asc" else expr.desc()
        stmt = stmt.order_by(None).order_by(order.nulls_last())
    return stmt.where(*predicates).order_by(stable), count_stmt.where(*predicates)
