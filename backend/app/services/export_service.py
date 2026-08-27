"""Data export service - format query results as CSV / JSON files.

Design notes:
- All formatters take the standardized ``columns`` / ``rows`` from
  ``adapters.base.QueryResult`` so the service stays database-agnostic.
- Serialization is streamed (generator based) so large result sets are
  written in chunks instead of building one giant string in memory.
- CSV follows RFC 4180 (escaping handled by the ``csv`` module) and is
  emitted with a UTF-8 BOM so Excel opens Chinese content correctly.
"""

import csv
import io
import json
import logging
from collections.abc import AsyncGenerator, Generator, Sequence
from datetime import date, datetime
from typing import Any

from app.models.schemas import ExportFormat

logger = logging.getLogger(__name__)


#: Media type per format, used in the HTTP response headers.
MEDIA_TYPES: dict[ExportFormat, str] = {
    ExportFormat.CSV: "text/csv; charset=utf-8",
    ExportFormat.JSON: "application/json; charset=utf-8",
}

#: File extension per format.
EXTENSIONS: dict[ExportFormat, str] = {
    ExportFormat.CSV: "csv",
    ExportFormat.JSON: "json",
}


def get_media_type(export_format: ExportFormat) -> str:
    """Get HTTP media type for a format."""
    return MEDIA_TYPES[export_format]


def get_extension(export_format: ExportFormat) -> str:
    """Get file extension for a format."""
    return EXTENSIONS[export_format]


def build_filename(database_name: str, export_format: ExportFormat) -> str:
    """Build a timestamped download filename.

    Example:
        >>> build_filename("sales", ExportFormat.CSV)
        'sales_2026-08-12T20-16-57.csv'
    """
    timestamp = datetime.now().isoformat(timespec="seconds").replace(":", "-")
    return f"{database_name}_{timestamp}.{get_extension(export_format)}"


def _csv_value(value: Any) -> Any:
    """Normalize a single value for CSV output.

    - None -> empty string (instead of the csv module's "None")
    - datetime/date -> ISO 8601 string
    """
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _json_value(value: Any) -> Any:
    """Normalize a single value for JSON output.

    Only converts types json.dumps cannot serialize natively
    (datetime stays as ISO string via ``default=str`` at dump time).
    """
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def iter_csv(
    columns: Sequence[dict[str, str]],
    rows: Sequence[dict[str, Any]],
) -> Generator[str, None, None]:
    """Yield CSV content in chunks.

    Args:
        columns: List of column dicts with at least a "name" key
        rows: List of row dicts keyed by column name

    Yields:
        CSV text chunks. The first chunk carries the UTF-8 BOM.
    """
    headers = [col["name"] for col in columns]

    # UTF-8 BOM so Excel displays UTF-8 (e.g. Chinese) correctly.
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")

    # Header row (BOM is prepended so the cursor position never touches it)
    writer.writerow(headers)
    yield "\ufeff" + buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)

    for row in rows:
        values = [_csv_value(row.get(header)) for header in headers]
        writer.writerow(values)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)


def iter_json(
    columns: Sequence[dict[str, str]],
    rows: Sequence[dict[str, Any]],
) -> Generator[str, None, None]:
    """Yield JSON array content in chunks (pretty-printed, UTF-8 safe).

    Args:
        columns: List of column dicts (kept for interface symmetry with iter_csv)
        rows: List of row dicts

    Yields:
        JSON text chunks forming a valid JSON array.
    """
    yield "[\n"

    for index, row in enumerate(rows):
        # Serialize each row independently so big datasets never sit in memory twice.
        serialized = json.dumps(
            {key: _json_value(value) for key, value in row.items()},
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        # Indent each row's lines by 2 spaces and add the list separator.
        indented = "\n".join(f"  {line}" for line in serialized.splitlines())
        separator = "," if index < len(rows) - 1 else ""
        yield f"{indented}{separator}\n"

    yield "]\n"


def format_export(
    columns: Sequence[dict[str, str]],
    rows: Sequence[dict[str, Any]],
    export_format: ExportFormat,
) -> str:
    """Format the full result set into a single string (non-streaming helper).

    Primarily used by the CLI and unit tests; the API endpoint uses the
    streaming generators instead.

    Args:
        columns: Column definitions
        rows: Result rows
        export_format: Target format

    Returns:
        Formatted content as a single string
    """
    if export_format == ExportFormat.CSV:
        return "".join(iter_csv(columns, rows))
    return "".join(iter_json(columns, rows))


async def stream_export(
    columns: Sequence[dict[str, str]],
    rows: Sequence[dict[str, Any]],
    export_format: ExportFormat,
) -> AsyncGenerator[str, None]:
    """Async adapter over the sync generators for FastAPI StreamingResponse."""
    if export_format == ExportFormat.CSV:
        generator: Generator[str, None, None] = iter_csv(columns, rows)
    else:
        generator = iter_json(columns, rows)
    for chunk in generator:
        yield chunk
