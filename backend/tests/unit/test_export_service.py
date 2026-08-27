"""Unit tests for the data export service (CSV / JSON formatting)."""

import json
from datetime import datetime

import pytest

from app.models.schemas import ExportFormat
from app.services.export_service import (
    build_filename,
    format_export,
    get_extension,
    get_media_type,
    iter_csv,
    iter_json,
)


@pytest.fixture
def sample_columns():
    return [
        {"name": "id", "dataType": "integer"},
        {"name": "name", "dataType": "character varying"},
        {"name": "created_at", "dataType": "timestamp"},
    ]


@pytest.fixture
def sample_rows():
    return [
        {"id": 1, "name": "Alice", "created_at": datetime(2026, 8, 12, 10, 30, 0)},
        {"id": 2, "name": 'Bob, "the" \n builder', "created_at": None},
    ]


def test_get_media_type_and_extension():
    assert get_media_type(ExportFormat.CSV).startswith("text/csv")
    assert get_media_type(ExportFormat.JSON).startswith("application/json")
    assert get_extension(ExportFormat.CSV) == "csv"
    assert get_extension(ExportFormat.JSON) == "json"


def test_build_filename():
    name = build_filename("sales", ExportFormat.CSV)
    assert name.endswith(".csv")
    assert name.startswith("sales_")
    assert ":" not in name  # timestamp must be filesystem-safe


def test_csv_formatting(sample_columns, sample_rows):
    content = format_export(sample_columns, sample_rows, ExportFormat.CSV)

    # UTF-8 BOM for Excel compatibility
    assert content.startswith("\ufeff")

    lines = content.lstrip("\ufeff").strip().split("\n")
    assert lines[0] == "id,name,created_at"

    # RFC 4180 escaping: comma, quotes and newlines wrapped + doubled quotes
    # (assert on raw content because the embedded newline splits the lines)
    assert '"Bob, ""the"" \n builder"' in content
    # None -> empty string (row ends with the empty third column)
    assert content.rstrip().endswith('builder",')
    # datetime -> ISO 8601
    assert "2026-08-12T10:30:00" in content


def test_csv_uses_iter_chunks(sample_columns, sample_rows):
    chunks = list(iter_csv(sample_columns, sample_rows))
    assert len(chunks) == 3  # header + 2 rows
    assert all(isinstance(c, str) for c in chunks)
    assert "".join(chunks) == format_export(sample_columns, sample_rows, ExportFormat.CSV)


def test_json_formatting(sample_columns, sample_rows):
    content = format_export(sample_columns, sample_rows, ExportFormat.JSON)

    parsed = json.loads(content)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["id"] == 1
    assert parsed[0]["created_at"] == "2026-08-12T10:30:00"  # datetime -> ISO string
    assert parsed[1]["created_at"] is None


def test_json_keeps_unicode(sample_columns):
    rows = [{"name": "中文名字", "id": 1}]
    content = format_export(sample_columns, rows, ExportFormat.JSON)
    assert "中文名字" in content  # ensure_ascii=False


def test_json_uses_iter_chunks(sample_columns, sample_rows):
    chunks = list(iter_json(sample_columns, sample_rows))
    content = "".join(chunks)
    assert content.startswith("[\n")
    assert content.rstrip().endswith("]")
    assert json.loads(content) is not None
