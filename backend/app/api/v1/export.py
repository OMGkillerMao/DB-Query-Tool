"""Data export API endpoints.

POST /api/v1/dbs/{name}/export re-executes the query server-side and
returns the result as a downloadable CSV / JSON file (streamed so large
result sets do not need to be held in memory twice).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from app.config import settings
from app.database import get_session
from app.models.database import DatabaseConnection
from app.models.query import QuerySource
from app.models.schemas import ExportRequest
from app.services.export_service import (
    build_filename,
    get_media_type,
    stream_export,
)
from app.services.query_wrapper import execute_query_with_service
from app.services.sql_validator import SqlValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/dbs", tags=["export"])


@router.post("/{name}/export")
async def export_query_results(
    name: str,
    input_data: ExportRequest,
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """
    Execute a SQL query and download the result as CSV or JSON.

    Args:
        name: Database connection name
        input_data: Export request (sql + format + optional limit)
        session: Database session

    Returns:
        StreamingResponse with the file content and attachment headers

    Raises:
        HTTPException 404: Connection not found
        HTTPException 400: SQL validation error
        HTTPException 500: Query execution / export failure
    """
    # Verify the connection exists
    statement = select(DatabaseConnection).where(DatabaseConnection.name == name)
    connection = session.exec(statement).first()

    if not connection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Database connection '{name}' not found",
        )

    # The SQL validator only applies the limit when the query has no LIMIT clause,
    # so exporting a query that already limits its rows keeps that behavior.
    effective_limit = input_data.limit or settings.query_default_limit

    # Execute the query server-side, reusing the standard execution chain
    # (API -> query wrapper -> DatabaseService -> adapter).
    try:
        result = await execute_query_with_service(
            session,
            name,
            connection.db_type,
            connection.url,
            input_data.sql,
            QuerySource.MANUAL,
            limit=effective_limit,
        )
    except SqlValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.exception("Export query failed for database '%s'", name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export query execution failed: {str(e)}",
        )

    columns = [{"name": col.name, "dataType": col.data_type} for col in result.columns]
    rows = result.rows
    export_format = input_data.format

    filename = build_filename(name, export_format)

    logger.info(
        "Exporting %d rows (%s) for database '%s'", len(rows), export_format.value, name
    )

    return StreamingResponse(
        stream_export(columns, rows, export_format),
        media_type=get_media_type(export_format),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Row-Count": str(len(rows)),
        },
    )
