/**
 * Query result export service.
 *
 * Delegates export to the backend endpoint (POST /api/v1/dbs/{name}/export)
 * so large result sets are streamed server-side instead of being built in
 * the browser. The response is a file download (Blob + <a> click).
 */

export type ExportFormat = "csv" | "json";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function getFilenameFromDisposition(disposition: string | null, fallback: string): string {
  if (!disposition) return fallback;
  const match = /filename="?([^"]+)"?/.exec(disposition);
  return match?.[1] || fallback;
}

function buildFallbackFilename(databaseName: string, format: ExportFormat): string {
  const timestamp = new Date()
    .toISOString()
    .replace(/[:.]/g, "-")
    .slice(0, 19);
  return `${databaseName}_${timestamp}.${format}`;
}

/**
 * Execute a query server-side and download the result as a file.
 *
 * @param databaseName  Database connection name
 * @param sql           SQL SELECT query to export
 * @param format        "csv" | "json"
 * @param limit         Optional row limit (only applies when SQL has no LIMIT)
 */
export async function exportQuery(
  databaseName: string,
  sql: string,
  format: ExportFormat,
  limit?: number
): Promise<{ filename: string; rowCount: number }> {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/dbs/${encodeURIComponent(databaseName)}/export`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sql, format, limit }),
    }
  );

  if (!response.ok) {
    let detail = `Export failed (HTTP ${response.status})`;
    try {
      const data = await response.json();
      detail = data?.detail || detail;
    } catch {
      // Non-JSON error body - keep the generic message.
    }
    throw new Error(detail);
  }

  const blob = await response.blob();
  const fallback = buildFallbackFilename(databaseName, format);
  const filename = getFilenameFromDisposition(
    response.headers.get("Content-Disposition"),
    fallback
  );
  const rowCount = Number(response.headers.get("X-Export-Row-Count")) || 0;

  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(link.href);

  return { filename, rowCount };
}
