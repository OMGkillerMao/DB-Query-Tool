"""One-command "execute + export" CLI for the Database Query Tool.

Combines the two manual steps (run a query, save the result as a file) into
a single command so the flow can be triggered from the terminal or from a
Makefile target without touching the web UI.

Usage:
    python scripts/export_query.py --db sales --sql "SELECT * FROM users" \
        --format csv --limit 100000
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Allow `from app...` imports when run as `python scripts/export_query.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select  # noqa: E402

from app.database import engine, init_db  # noqa: E402
from app.models.database import DatabaseConnection  # noqa: E402
from app.services.database_service import database_service  # noqa: E402
from app.services.export_service import (  # noqa: E402
    ExportFormat,
    build_filename,
    format_export,
)
from app.services.sql_validator import SqlValidationError  # noqa: E402

DEFAULT_EXPORT_DIR = Path(__file__).resolve().parent.parent / "exports"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Execute a SQL query and export the result as CSV or JSON.",
    )
    parser.add_argument("--db", required=True, help="Database connection name")
    parser.add_argument("--sql", required=True, help="SQL SELECT query to execute and export")
    parser.add_argument(
        "--format",
        choices=["csv", "json"],
        default="csv",
        help="Export format (default: csv)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100_000,
        help="Row limit when the SQL has no LIMIT clause (default: 100000)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path (default: backend/exports/<db>_<timestamp>.<ext>)",
    )
    return parser.parse_args()


def load_connection(name: str) -> DatabaseConnection | None:
    """Load a saved connection from the SQLite app database."""
    init_db()
    with Session(engine) as session:
        statement = select(DatabaseConnection).where(DatabaseConnection.name == name)
        return session.exec(statement).first()


async def run(args: argparse.Namespace) -> int:
    """Execute the 3-step workflow: get result -> format -> write file."""
    try:
        export_format = ExportFormat(args.format)
    except ValueError:
        print(f"Unsupported format: {args.format}")
        return 2

    connection = load_connection(args.db)
    if not connection:
        print(f"Database connection '{args.db}' not found.")
        print("Add it first via the web UI or the /api/v1/dbs endpoints.")
        return 1

    print(f"[1/3] Executing query on '{args.db}' ...")
    try:
        result, execution_time_ms = await database_service.execute_query(
            db_type=connection.db_type,
            name=connection.name,
            url=connection.url,
            sql=args.sql,
            limit=args.limit,
        )
    except SqlValidationError as e:
        print(f"SQL validation failed: {e}")
        return 1
    except Exception as e:
        print(f"Query execution failed: {e}")
        return 1

    print(f"      -> {result.row_count} rows in {execution_time_ms}ms")

    print(f"[2/3] Formatting as {export_format.value.upper()} ...")
    content = format_export(result.columns, result.rows, export_format)

    output_path = (
        Path(args.output)
        if args.output
        else DEFAULT_EXPORT_DIR / build_filename(args.db, export_format)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[3/3] Writing {output_path} ...")
    output_path.write_text(content, encoding="utf-8")

    # Close the pool while the event loop is still open, otherwise aiomysql
    # emits a "RuntimeError: Event loop is closed" during interpreter shutdown.
    await database_service.close_connection(connection.db_type, connection.name)

    print(f"Done. Exported {result.row_count} rows to {output_path}")
    return 0


def main() -> int:
    """Entry point."""
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    sys.exit(main())
