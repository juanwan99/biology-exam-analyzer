"""B0 Schema Contract 验证脚本。

用法: docker exec biology_backend python scripts/verify_schema.py
"""
import sys
import os

# 确保 /app (项目根) 在 sys.path 中，以便 import database
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import subprocess

REQUIRED_TABLES = [
    "exercise_bank", "exercise_sources", "knowledge_points",
    "textbook_pages", "textbook_chunks", "textbook_versions",
    "admin_users", "operation_logs", "resources",
    "exam_history", "question_performance", "difficulty_mapping", "score_prediction",
]

REQUIRED_COUNTS = {
    "exercise_bank": 701,
    "textbook_chunks": 1734,
}


def verify_with_sqlalchemy():
    """Strategy A: async SQLAlchemy (matches project database.py)."""
    import asyncio
    from sqlalchemy import text
    from database import async_session

    async def _verify():
        errors = []
        async with async_session() as db:
            result = await db.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            ))
            existing = {row[0] for row in result}
            for t in REQUIRED_TABLES:
                if t not in existing:
                    errors.append(f"MISSING TABLE: {t}")
                else:
                    r2 = await db.execute(text(f"SELECT COUNT(*) FROM {t}"))
                    count = r2.scalar()
                    print(f"  {t}: {count} rows")

            for table, expected in REQUIRED_COUNTS.items():
                if table in existing:
                    r = await db.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = r.scalar()
                    if count < expected:
                        errors.append(
                            f"COUNT REGRESSION: {table} = {count}, "
                            f"expected >= {expected}"
                        )
        return errors

    return asyncio.run(_verify())


def verify_with_psql():
    """Strategy B: psql CLI via subprocess."""
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://biology:biology123@biology_postgres:5432/biology_edu",
    )
    parts = db_url.replace("postgresql://", "").split("@")
    user_pass = parts[0]
    host_rest = parts[1]
    user = user_pass.split(":")[0]
    password = user_pass.split(":")[1] if ":" in user_pass else ""
    host_port, dbname = host_rest.split("/", 1)
    host = host_port.split(":")[0]
    port = host_port.split(":")[1] if ":" in host_port else "5432"

    env = os.environ.copy()
    env["PGPASSWORD"] = password

    def psql_query(sql):
        cmd = [
            "psql", "-h", host, "-p", port, "-U", user,
            "-d", dbname, "-t", "-A", "-c", sql,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, env=env, timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"psql error: {result.stderr.strip()}")
        return result.stdout.strip()

    errors = []
    raw = psql_query(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public'"
    )
    existing = set(raw.split("\n")) if raw else set()

    for t in REQUIRED_TABLES:
        if t not in existing:
            errors.append(f"MISSING TABLE: {t}")
        else:
            count = int(psql_query(f"SELECT COUNT(*) FROM {t}"))
            print(f"  {t}: {count} rows")

    for table, expected in REQUIRED_COUNTS.items():
        if table in existing:
            count = int(psql_query(f"SELECT COUNT(*) FROM {table}"))
            if count < expected:
                errors.append(
                    f"COUNT REGRESSION: {table} = {count}, "
                    f"expected >= {expected}"
                )

    return errors


def main():
    print("Schema Contract Verification")
    print("=" * 40)

    errors = None

    # Strategy A: SQLAlchemy
    try:
        from sqlalchemy import text  # noqa: F401
        from database import async_session  # noqa: F401
        print("[strategy: SQLAlchemy async]")
        errors = verify_with_sqlalchemy()
    except ImportError as e:
        print(f"[SQLAlchemy/database not available ({e}), trying psql...]")

    # Strategy B: psql subprocess
    if errors is None:
        try:
            print("[strategy: psql subprocess]")
            errors = verify_with_psql()
        except Exception as e:
            print(f"[psql subprocess failed: {e}]")

    if errors is None:
        print("\nSCHEMA CONTRACT: ERROR")
        print("  No working DB strategy. Install sqlalchemy+asyncpg or psql.")
        sys.exit(2)

    if errors:
        print("\nSCHEMA CONTRACT: FAIL")
        for e in errors:
            print(f"  FAIL: {e}")
        sys.exit(1)
    else:
        print("\nSCHEMA CONTRACT: PASS")
        print(f"  All {len(REQUIRED_TABLES)} tables verified.")
        sys.exit(0)


if __name__ == "__main__":
    main()
