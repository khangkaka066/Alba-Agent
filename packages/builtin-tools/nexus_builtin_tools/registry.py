"""Scoped native tools available to Crew agents and NexusGen function callers."""
from __future__ import annotations

import asyncio
import csv
import html
import http.client
import io
import ipaddress
import math
import json
import re
import socket
import ssl
import struct
import sqlite3
import urllib.parse
import zipfile
import zlib
from functools import partial
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


@dataclass
class ToolContext:
    tenant_id: str
    workspace_id: str
    run_id: str
    artifact_root: Path
    enabled_ids: frozenset[str] | None = None
    rag_query: Callable[[str], Awaitable[Any]] | None = None
    shell: Callable[[str, int], Awaitable[Any]] | None = None
    browser: Callable[[str, dict[str, str]], Awaitable[Any]] | None = None
    computer: Callable[[str, dict[str, Any]], Awaitable[Any]] | None = None
    media: Callable[[str, dict[str, Any]], Awaitable[Any]] | None = None
    workflow_delegate: Callable[[str, dict[str, Any]], Awaitable[Any]] | None = None
    database_urls: dict[str, str] = field(default_factory=dict)
    search_credentials: dict[str, str] = field(default_factory=dict)
    boundary_guard: Callable[[str, str], Awaitable[None]] | None = None
    activity_sink: Callable[[dict[str, Any]], Awaitable[None]] | None = None
    authorize_tool: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="allow")
    payload: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class ToolDescriptor:
    id: str
    name: str
    description: str
    category: str


TOOLS = (
    ToolDescriptor("web_search", "Web Search & News", "Search multiple sources with provider-key or public-search fallback.", "research"),
    ToolDescriptor("web_scraper", "Smart Web Scraper", "Extract readable text, tables, and links from a public URL.", "research"),
    ToolDescriptor("document_parser", "Document Parser", "Parse a run artifact and extract text and table structure.", "documents"),
    ToolDescriptor("report_exporter", "Report Exporter", "Save Markdown, HTML, CSV, XLSX, PDF, or DOCX deliverables.", "documents"),
    ToolDescriptor("chart_generator", "Chart Generator", "Render a validated line, bar, or scatter chart from numeric data.", "data"),
    ToolDescriptor("safe_sql", "Safe SQL Query", "Run bounded read-only analytics against configured SQLite/PostgreSQL sources.", "data"),
    ToolDescriptor("http_webhook", "HTTP Webhook Client", "Call an authorized external HTTP endpoint with a bounded request.", "integrations"),
    ToolDescriptor("sandbox_shell", "Sandbox Shell & Files", "Execute a command inside the assigned isolated computer.", "computer"),
    ToolDescriptor("view_file_numbered", "View File with Line Numbers", "Read a bounded, numbered range from the computer workspace.", "computer"),
    ToolDescriptor("surgical_file_edit", "Exact File Edit", "Replace one exact block, check supported syntax, snapshot and publish a diff.", "computer"),
    ToolDescriptor("fast_workspace_search", "Workspace Code Search", "Search literal text in workspace files filtered by path glob.", "computer"),
    ToolDescriptor("start_background_process", "Start Background Process", "Start a supervised server or watcher and discover its preview ports.", "computer"),
    ToolDescriptor("get_process_logs", "Read Process Log", "Read the bounded journal of a process in this computer.", "computer"),
    ToolDescriptor("stop_process", "Stop Process", "Stop one supervised process without ending the workflow.", "computer"),
    ToolDescriptor("list_running_processes", "List Processes", "Inspect the current computer's processes, ports and working directory.", "computer"),
    ToolDescriptor("browser_automation", "Browser Automation", 'Use the isolated browser. Payload: {"action":"navigate","arguments":{"url":"http://127.0.0.1:8765/index.html"}}. Actions: navigate(url), click(selector), fill(selector,value), extract(selector), screenshot. Returns page text for extract; screenshots stay on the screen stream.', "computer"),
    ToolDescriptor("media_generation", "Media Generation", "Request image, audio, or video generation from the configured provider gateway.", "media"),
    ToolDescriptor("knowledge_rag", "Knowledge Base RAG", "Search the current tenant's knowledge bases with citations.", "knowledge"),
    ToolDescriptor("peer_workflow", "Peer Workflow Delegation", "Invoke a published workflow in the current workspace.", "orchestration"),
)


def _resolve_public_url(url: str) -> tuple[urllib.parse.ParseResult, tuple[str, ...]]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTP(S) URLs are supported")
    try:
        addresses = tuple(dict.fromkeys(str(item[4][0]) for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)))
    except OSError as error:
        raise ValueError("URL host could not be resolved") from error
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise PermissionError("Requests to private, loopback, or reserved network addresses are blocked")
    # The caller connects to one of these vetted addresses directly to prevent DNS rebinding.
    return parsed, addresses


def _http(url: str, *, method: str = "GET", data: bytes | None = None, headers: dict[str, str] | None = None, timeout: int = 15) -> bytes:
    parsed, addresses = _resolve_public_url(url)
    host = parsed.hostname
    if host is None:
        raise ValueError("URL hostname is missing")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    address = addresses[0]
    request_path = urllib.parse.urlunparse(("", "", parsed.path or "/", parsed.params, parsed.query, ""))
    class PinnedHTTPConnection(http.client.HTTPConnection):
        def connect(self) -> None:
            source_address = cast(Any, self).__dict__.get("source_address")
            self.sock = socket.create_connection((address, port), self.timeout, source_address)
    class PinnedHTTPSConnection(http.client.HTTPSConnection):
        def connect(self) -> None:
            source_address = cast(Any, self).__dict__.get("source_address")
            raw = socket.create_connection((address, port), self.timeout, source_address)
            self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
    connection: http.client.HTTPConnection = PinnedHTTPSConnection(host, port, timeout=max(1, min(timeout, 30))) if parsed.scheme == "https" else PinnedHTTPConnection(host, port, timeout=max(1, min(timeout, 30)))
    try:
        request_headers = {key: value for key, value in (headers or {}).items() if key.lower() not in {"host", "connection", "content-length", "transfer-encoding"}}
        connection.request(method, request_path, body=data, headers={**request_headers, "Host": parsed.netloc, "Connection": "close"})
        response = connection.getresponse()
        if response.status in {301, 302, 303, 307, 308}:
            location = response.getheader("Location", "")
            _resolve_public_url(urllib.parse.urljoin(url, location))
            raise ValueError("Redirects are disabled; call the validated destination directly")
        if response.status >= 400:
            raise ValueError(f"HTTP request failed with status {response.status}")
        if response.getheader("Content-Length", "0").isdigit() and int(response.getheader("Content-Length", "0")) > 5_000_000:
            raise ValueError("HTTP response is too large")
        content = response.read(5_000_001)
        if len(content) > 5_000_000:
            raise ValueError("HTTP response exceeds 5 MB")
        return content
    finally:
        connection.close()


def _html_text(content: bytes) -> dict[str, Any]:
    text = content.decode("utf-8", errors="replace")
    text = re.sub(r"(?is)<(script|style|nav|footer|header|aside)\b.*?>.*?</\1\s*>", " ", text)
    links = re.findall(r'''(?is)<a\b[^>]*href=["']([^"']+)["'][^>]*>(.*?)</a\s*>''', text)
    tables = re.findall(r"(?is)<table\b.*?</table\s*>", text)
    clean = re.sub(r"(?is)<br\s*/?>|</p\s*>|</h[1-6]\s*>|</tr\s*>", "\n", text)
    clean = re.sub(r"(?is)<[^>]+>", " ", clean)
    clean = html.unescape(re.sub(r"[ \t\r\f\v]+", " ", clean))
    clean = re.sub(r"\n\s*\n+", "\n\n", clean).strip()
    return {"markdown": clean[:100_000], "tables_html": tables[:20], "links": [{"href": href, "text": re.sub(r"<[^>]+>", "", label).strip()} for href, label in links[:100]]}


def _png_chart(path: Path, labels: list[Any], values: list[float], kind: str, title: str) -> None:
    width, height = 960, 560
    pixels = bytearray([255, 255, 255] * width * height)
    def point(x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < width and 0 <= y < height:
            offset = (y * width + x) * 3
            pixels[offset:offset+3] = bytes(color)
    def line(x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        dx, sx = abs(x1-x0), 1 if x0 < x1 else -1
        dy, sy = -abs(y1-y0), 1 if y0 < y1 else -1
        error = dx + dy
        while True:
            point(x0, y0, color)
            if x0 == x1 and y0 == y1: break
            twice = 2 * error
            if twice >= dy: error += dy; x0 += sx
            if twice <= dx: error += dx; y0 += sy
    left, top, right, bottom = 72, 54, width-32, height-74
    for grid in range(1, 5):
        y = bottom - (bottom-top)*grid//5
        line(left, y, right, y, (229, 232, 238))
    line(left, top, left, bottom, (70, 77, 90)); line(left, bottom, right, bottom, (70, 77, 90))
    low, high = min(0.0, min(values)), max(1.0, max(values))
    span = high-low or 1
    xs = [left + (right-left)*(i+1)//(len(values)+1) for i in range(len(values))]
    ys = [bottom - int((value-low)/span*(bottom-top)) for value in values]
    blue = (80, 93, 220)
    if kind == "bar":
        slot = (right-left)//len(values)
        for x, y in zip(xs, ys):
            for bx in range(x-slot//3, x+slot//3):
                for by in range(y, bottom): point(bx, by, blue)
    elif kind == "line":
        for first, second in zip(zip(xs, ys), zip(xs[1:], ys[1:])): line(*first, *second, blue)
    for x, y in zip(xs, ys):
        for dx in range(-4,5):
            for dy in range(-4,5):
                if dx*dx+dy*dy <= 16: point(x+dx, y+dy, blue)
    def chunk(kind_bytes: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind_bytes + data + struct.pack(">I", zlib.crc32(kind_bytes+data) & 0xffffffff)
    raw = b"".join(b"\0" + pixels[y*width*3:(y+1)*width*3] for y in range(height))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 2, 0, 0, 0)) + chunk(b"tEXt", b"Title\0" + title[:150].encode("utf-8", errors="replace")) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")
    path.write_bytes(png)


class BuiltinToolRegistry:
    def __init__(self, context: ToolContext) -> None:
        self.context = context
        self._handlers: dict[str, Callable[[dict[str, Any]], Awaitable[Any]]] = {
            "web_search": self._web_search, "web_scraper": self._web_scraper,
            "document_parser": self._document_parser, "report_exporter": self._report_exporter,
            "chart_generator": self._chart_generator, "safe_sql": self._safe_sql,
            "http_webhook": self._http_webhook, "sandbox_shell": self._sandbox_shell,
            "browser_automation": self._browser, "media_generation": self._media,
            "knowledge_rag": self._rag, "peer_workflow": self._delegate,
        }

        for operation in ("view_file_numbered", "surgical_file_edit", "fast_workspace_search", "start_background_process", "get_process_logs", "stop_process", "list_running_processes"):
            self._handlers[operation] = partial(self._computer, operation)

    async def _computer(self, operation: str, payload: dict[str, Any]) -> Any:
        if self.context.computer is None:
            raise RuntimeError("Interactive computer tools are not configured for this run")
        return await self.context.computer(operation, payload)

    def descriptors(self) -> tuple[ToolDescriptor, ...]:
        return TOOLS

    async def run(self, tool_id: str, payload: dict[str, Any]) -> Any:
        if tool_id not in self._handlers:
            raise LookupError("Unknown built-in tool")
        if self.context.enabled_ids is not None and tool_id not in self.context.enabled_ids:
            raise PermissionError("This built-in tool is disabled in the workspace")
        if self.context.authorize_tool is not None:
            await self.context.authorize_tool(tool_id, payload)
        descriptor = next(item for item in TOOLS if item.id == tool_id)
        arguments = payload.get("arguments", payload)
        detail = ""
        if isinstance(arguments, dict):
            detail = " · ".join(str(arguments[key])[:180] for key in ("action", "path", "selector", "query", "url", "filename") if arguments.get(key))
        if tool_id in {"sandbox_shell", "start_background_process"}:
            detail = str(payload.get("command", "")).splitlines()[0][:180] if payload.get("command") else ""
        detail = re.sub(r"(?i)(?:sk-[\w-]+|(?:api[_-]?key|token|password)\s*[=:]\s*[^\s;,]+)", "[redacted]", detail)
        event = {"call_id": str(uuid4()), "tool": descriptor.name, "detail": detail}
        if self.context.activity_sink is not None:
            await self.context.activity_sink({**event, "phase": "started"})
        try:
            result = await self._handlers[tool_id](payload)
        except Exception:
            if self.context.activity_sink is not None:
                await self.context.activity_sink({**event, "phase": "failed"})
            raise
        if self.context.activity_sink is not None:
            parts = []
            if isinstance(result, dict):
                for key in ("stdout", "stderr", "summary", "result"):
                    value = result.get(key)
                    if isinstance(value, (str, int, float)) and str(value).strip():
                        parts.append(str(value))
            output = "\n".join(parts)[:4000]
            output = re.sub(r"(?i)(?:sk-[\w-]+|(?:api[_-]?key|token|password)\s*[=:]\s*[^\s;,]+)", "[redacted]", output)
            await self.context.activity_sink({**event, "phase": "completed", "output": output})
        return result

    async def _web_search(self, p: dict[str, Any]) -> dict[str, Any]:
        query = str(p.get("query", "")).strip()
        if not query or len(query) > 500:
            raise ValueError("query is required and must be under 500 characters")
        key = self.context.search_credentials.get("serper")
        provider = str(p.get("provider", ""))
        if key or provider == "serper":
            if not key: raise ValueError("Search provider credential is not configured")
            raw = await asyncio.to_thread(_http, "https://google.serper.dev/search", method="POST", data=json.dumps({"q": query}).encode(), headers={"X-API-KEY": str(key), "Content-Type": "application/json"})
            return cast(dict[str, Any], json.loads(raw))
        key = self.context.search_credentials.get("tavily")
        if key or provider == "tavily":
            if not key: raise ValueError("Search provider credential is not configured")
            raw = await asyncio.to_thread(_http, "https://api.tavily.com/search", method="POST", data=json.dumps({"api_key": str(key), "query": query, "max_results": 8}).encode(), headers={"Content-Type": "application/json"})
            return cast(dict[str, Any], json.loads(raw))
        # Public HTML fallback; isolate parsing to result links/snippets and bound body size.
        raw = await asyncio.to_thread(_http, "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query), headers={"User-Agent": "NexusStudio/1.0"})
        return _html_text(raw)

    async def _web_scraper(self, p: dict[str, Any]) -> dict[str, Any]:
        url = str(p.get("url", ""))
        try:
            raw = await asyncio.to_thread(_http, url, headers={"User-Agent": "NexusStudio/1.0"})
        except PermissionError:
            raise
        except OSError:
            if self.context.browser is None:
                raise
            rendered = await self.context.browser("navigate", {"url": url})
            if not isinstance(rendered, bytes):
                raise RuntimeError("Configured browser hook did not return extracted page bytes")
            raw = rendered
        return _html_text(raw)

    def _path(self, name: str) -> Path:
        candidate = (self.context.artifact_root / name).resolve()
        if self.context.artifact_root.resolve() not in candidate.parents:
            raise ValueError("Artifact path must remain in this run's directory")
        return candidate

    async def _document_parser(self, p: dict[str, Any]) -> dict[str, Any]:
        path = self._path(str(p.get("path", "")))
        if not path.is_file() or path.stat().st_size > 20_000_000: raise ValueError("Document is missing or exceeds 20 MB")
        suffix = path.suffix.lower()
        if suffix in {".csv"}:
            csv_rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
            return {"columns": csv_rows[0] if csv_rows else [], "rows": csv_rows[1:1001], "row_count_sampled": min(max(len(csv_rows)-1, 0),1000)}
        if suffix == ".json": return {"data": json.loads(path.read_text(encoding="utf-8"))}
        if suffix in {".md", ".markdown", ".txt"}: return {"text": path.read_text(encoding="utf-8", errors="replace")[:500_000]}
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError as error: raise RuntimeError("PDF support is not installed") from error
            return {"text": "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)[:500_000]}
        if suffix == ".docx":
            try:
                from docx import Document
            except ImportError as error: raise RuntimeError("DOCX support is not installed") from error
            doc = Document(str(path))
            return {"text": "\n".join(item.text for item in doc.paragraphs), "tables": [[[cell.text for cell in row.cells] for row in table.rows] for table in doc.tables]}
        if suffix == ".xlsx":
            try: from openpyxl import load_workbook  # type: ignore[import-untyped]
            except ImportError:
                from xml.etree import ElementTree
                with zipfile.ZipFile(path) as archive:
                    shared: list[str] = []
                    if "xl/sharedStrings.xml" in archive.namelist():
                        shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                        shared = ["".join(text.text or "" for text in item.iter() if text.tag.endswith("}t")) for item in shared_root]
                    sheet_files = sorted(name for name in archive.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name))
                    sheets: dict[str, list[list[Any]]] = {}
                    for index, sheet_name in enumerate(sheet_files, 1):
                        root = ElementTree.fromstring(archive.read(sheet_name)); rows: list[list[Any]] = []
                        for row in root.iter():
                            if not row.tag.endswith("}row"): continue
                            values: list[Any] = []
                            for cell in row:
                                if not cell.tag.endswith("}c"): continue
                                value = next((child.text for child in cell if child.tag.endswith("}v")), "")
                                if cell.attrib.get("t") == "s" and value: value = shared[int(value)]
                                values.append(value)
                            rows.append(values)
                        sheets[f"Sheet{index}"] = rows[:1000]
                    return {"sheets": sheets}
            workbook = load_workbook(str(path), read_only=True, data_only=True)
            return {"sheets": {sheet.title: list(sheet.iter_rows(values_only=True))[:1000] for sheet in workbook.worksheets}}
        raise ValueError("Supported document formats: PDF, DOCX, XLSX, CSV, JSON, Markdown, TXT")

    async def _report_exporter(self, p: dict[str, Any]) -> dict[str, str]:
        fmt = str(p.get("format", "markdown")).lower()
        name = str(p.get("filename", "report"))
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", name): raise ValueError("Invalid artifact filename")
        content = p.get("content", "")
        path = self._path(f"{name}.{fmt if fmt != 'markdown' else 'md'}")
        path.parent.mkdir(parents=True, exist_ok=True)
        if fmt in {"markdown", "md"}: path.write_text(str(content), encoding="utf-8")
        elif fmt == "html": path.write_text("<!doctype html><meta charset=utf-8><article>" + html.escape(str(content)).replace("\n", "<br>") + "</article>", encoding="utf-8")
        elif fmt == "csv":
            rows = p.get("rows", [])
            if not isinstance(rows, list) or len(rows) > 10000: raise ValueError("CSV rows must be a bounded list")
            with path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.writer(file); writer.writerows(rows)
        elif fmt == "xlsx":
            spreadsheet_rows = p.get("rows", [])
            if not isinstance(spreadsheet_rows, list) or len(spreadsheet_rows) > 10000: raise ValueError("XLSX rows must be a bounded list")
            try:
                from openpyxl import Workbook
            except ImportError:
                def colname(index: int) -> str:
                    result = ""
                    while index:
                        index, remainder = divmod(index - 1, 26); result = chr(65 + remainder) + result
                    return result
                cells = []
                for row_index, values in enumerate(spreadsheet_rows, 1):
                    if not isinstance(values, (list, tuple)): raise ValueError("Each spreadsheet row must be an array")
                    cells.append(f'<row r="{row_index}">' + "".join(f'<c r="{colname(col_index)}{row_index}" t="inlineStr"><is><t>{html.escape(str(value))}</t></is></c>' for col_index, value in enumerate(values, 1)) + "</row>")
                with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
                    archive.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
                    archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Report" sheetId="1" r:id="rId1"/></sheets></workbook>')
                    archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
                    archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(cells) + "</sheetData></worksheet>")
            else:
                workbook = Workbook(); sheet = workbook.active
                for row in spreadsheet_rows: sheet.append(row)
                workbook.save(str(path))
        elif fmt == "docx":
            try: from docx import Document
            except ImportError:
                with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
                    archive.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
                    paragraphs = "".join("<w:p><w:r><w:t xml:space=\"preserve\">" + html.escape(line) + "</w:t></w:r></w:p>" for line in str(content).splitlines())
                    archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + paragraphs + '<w:sectPr/></w:body></w:document>')
            else:
                doc = Document(); doc.add_paragraph(str(content)); doc.save(str(path))
        elif fmt == "pdf":
            lines = str(content).splitlines()[:1000]
            escaped_lines = [line[:120].replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
            text = "BT /F1 10 Tf 48 750 Td 14 TL " + " ".join("(" + line + ") Tj T*" for line in escaped_lines) + " ET"
            stream = text.encode("latin-1", errors="replace")
            objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>", b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
            output = bytearray(b"%PDF-1.4\n"); offsets = [0]
            for index, obj in enumerate(objects, 1): offsets.append(len(output)); output.extend(f"{index} 0 obj\n".encode()+obj+b"\nendobj\n")
            xref = len(output); output.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
            for offset in offsets[1:]: output.extend(f"{offset:010d} 00000 n \n".encode())
            output.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()); path.write_bytes(output)
        else: raise ValueError("Format must be Markdown, HTML, CSV, XLSX, PDF, or DOCX")
        return {"artifact": str(path.relative_to(self.context.artifact_root.resolve())), "format": fmt}

    async def _chart_generator(self, p: dict[str, Any]) -> dict[str, str]:
        kind = str(p.get("kind", "bar"))
        if kind not in {"bar", "line", "scatter"}: raise ValueError("Chart kind must be bar, line, or scatter")
        labels, values = p.get("labels"), p.get("values")
        if not isinstance(labels, list) or not isinstance(values, list) or not 1 <= len(values) <= 2000 or len(labels) != len(values): raise ValueError("Chart labels and values must be same-sized bounded arrays")
        numbers = [float(value) for value in values]
        if any(not __import__("math").isfinite(value) for value in numbers): raise ValueError("Chart data must be finite numbers")
        path = self._path(str(p.get("filename", "chart.png")))
        if path.suffix.lower() != ".png": raise ValueError("Chart output must be PNG")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import matplotlib  # type: ignore[import-not-found]
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt  # type: ignore[import-not-found]
        except ImportError:
            _png_chart(path, labels, numbers, kind, str(p.get("title", "")))
        else:
            figure, axis = plt.subplots(figsize=(10, 6), dpi=160)
            if kind == "bar": axis.bar(labels, numbers)
            elif kind == "line": axis.plot(labels, numbers, marker="o")
            else: axis.scatter(labels, numbers)
            axis.set_title(str(p.get("title", ""))[:160]); axis.grid(axis="y", alpha=.2); figure.tight_layout()
            figure.savefig(path, dpi=240, bbox_inches="tight"); plt.close(figure)
        return {"artifact": str(path.relative_to(self.context.artifact_root.resolve()))}

    async def _safe_sql(self, p: dict[str, Any]) -> dict[str, Any]:
        database = str(p.get("database") or "workspace"); query = str(p.get("query", "")).strip()
        if database == "workspace" and database not in self.context.database_urls:
            workspace_root = self.context.artifact_root.parent
            workspace_root.mkdir(parents=True, exist_ok=True)
            database_path = workspace_root / "workspace_analytics.sqlite"
            connection = sqlite3.connect(database_path)
            try:
                connection.execute("CREATE TABLE IF NOT EXISTS nexus_imports (source_path TEXT PRIMARY KEY, modified_ns INTEGER NOT NULL, table_name TEXT NOT NULL)")
                for path in sorted((*workspace_root.glob("*"), *workspace_root.glob("*/*")))[:200]:
                    if path.is_symlink() or not path.is_file() or path.suffix.lower() not in {".csv", ".xlsx"} or path.stat().st_size > 10_000_000:
                        continue
                    relative = str(path.relative_to(workspace_root))
                    modified = path.stat().st_mtime_ns
                    prior = connection.execute("SELECT modified_ns FROM nexus_imports WHERE source_path = ?", (relative,)).fetchone()
                    if prior is not None and prior[0] == modified:
                        continue
                    table = "data_" + re.sub(r"[^a-z0-9_]", "_", path.stem.lower())[:50] + "_" + __import__("hashlib").sha256(str(path.relative_to(workspace_root)).encode()).hexdigest()[:8]
                    if path.suffix.lower() == ".csv":
                        with path.open("r", encoding="utf-8-sig", newline="") as file:
                            rows = list(__import__("itertools").islice(csv.reader(file), 10001))
                    else:
                        try:
                            from openpyxl import load_workbook  # type: ignore[import-not-found, unused-ignore]
                        except ImportError as error:
                            raise RuntimeError("XLSX import requires openpyxl in the API image") from error
                        workbook = load_workbook(path, read_only=True, data_only=True)
                        rows = [["" if item is None else str(item) for item in row] for row in __import__("itertools").islice(workbook.active.values, 10001)] if workbook.active else []
                        workbook.close()
                    if not rows or not rows[0] or len(rows[0]) > 100:
                        continue
                    columns = [f"column_{index + 1}" for index in range(len(rows[0]))]
                    connection.execute(f'DROP TABLE IF EXISTS "{table}"')
                    connection.execute(f'CREATE TABLE "{table}" ({", ".join(f"{column} TEXT" for column in columns)})')
                    connection.executemany(f'INSERT INTO "{table}" VALUES ({", ".join("?" for _ in columns)})',
                        [tuple(str(value) for value in row[:len(columns)]) + ("",) * max(0, len(columns) - len(row)) for row in rows[1:10001]])
                    connection.execute("INSERT OR REPLACE INTO nexus_imports VALUES (?, ?, ?)", (relative, modified, table))
                connection.commit()
            finally:
                connection.close()
            self.context.database_urls[database] = f"sqlite:{database_path}"
        if database not in self.context.database_urls: raise PermissionError("Database is not configured for this workspace")
        if not re.match(r"(?is)^(select|with|pragma\s+table_info)\b", query) or ";" in query.rstrip(";") or re.search(r"(?i)\b(insert|update|delete|drop|alter|attach|detach|create|vacuum|copy|grant|revoke)\b", query): raise PermissionError("Only a single read-only SQL statement is permitted")
        limit = min(max(int(p.get("limit", 100)), 1), 1000)
        url = self.context.database_urls[database]
        if url.startswith("sqlite:"):
            dbpath = url.partition(":")[2].removeprefix("//")
            connection = sqlite3.connect(f"file:{dbpath}?mode=ro", uri=True)
            try:
                cursor = connection.execute(f"SELECT * FROM ({query}) AS nexus_limited LIMIT {limit}")
                return {"columns": [d[0] for d in cursor.description or ()], "rows": cursor.fetchall()}
            finally: connection.close()
        if url.startswith(("postgresql+asyncpg://", "postgresql://")):
            from sqlalchemy.ext.asyncio import create_async_engine
            engine = create_async_engine(url, connect_args={"server_settings": {"default_transaction_read_only": "on"}})
            try:
                async with engine.connect() as async_connection:
                    result = await async_connection.exec_driver_sql(f"SELECT * FROM ({query}) AS nexus_limited LIMIT {limit}")
                    return {"columns": list(result.keys()), "rows": [list(row) for row in result.fetchall()]}
            finally: await engine.dispose()
        raise ValueError("Only configured SQLite and PostgreSQL databases are supported")

    async def _http_webhook(self, p: dict[str, Any]) -> dict[str, Any]:
        method = str(p.get("method", "GET")).upper()
        if method not in {"GET", "POST", "PUT"}: raise ValueError("Webhook method must be GET, POST, or PUT")
        if method in {"POST", "PUT"}:
            if self.context.boundary_guard is None:
                raise PermissionError("External write requests require a human approval gate")
            await self.context.boundary_guard("external_action", f"{method} {p.get('url', '')}")
        url = str(p.get("url", "")); headers = p.get("headers", {})
        if not isinstance(headers, dict) or any(k.lower() in {"host", "content-length", "connection"} for k in headers): raise ValueError("Invalid webhook headers")
        body = json.dumps(p.get("body", {})).encode() if method in {"POST", "PUT"} else None
        raw = await asyncio.to_thread(_http, url, method=method, data=body, headers={**{str(k): str(v) for k,v in headers.items()}, "Content-Type": "application/json"}, timeout=int(p.get("timeout", 15)))
        return {"body": raw.decode("utf-8", errors="replace")[:100_000]}

    async def _sandbox_shell(self, p: dict[str, Any]) -> Any:
        if self.context.shell is None: raise RuntimeError("No isolated computer is assigned to this run")
        command = str(p.get("command", ""))
        if not command or len(command) > 4000: raise ValueError("Command is required and must be under 4000 characters")
        if p.get("background"):
            return await self._computer("start_background_process", p)
        return await self.context.shell(command, min(max(int(p.get("timeout", 30)), 1), 300))

    async def _browser(self, p: dict[str, Any]) -> Any:
        if self.context.browser is None: raise RuntimeError("Browser automation is not configured")
        action = str(p.get("action", "navigate")); args = p.get("arguments", p)
        if action not in {"navigate", "click", "fill", "screenshot", "extract"} or not isinstance(args, dict): raise ValueError("Unsupported browser action")
        result = await self.context.browser(action, {str(k): str(v) for k,v in args.items() if str(k) not in {"human", "approved", "action", "timeout_seconds"}})
        if isinstance(result, dict) and "frame_png_base64" in result:
            # Screen frames travel on the UI stream, not as base64 text in every model observation.
            return {**{key: value for key, value in result.items() if key != "frame_png_base64"}, "frame_available": True}
        return result

    async def _media(self, p: dict[str, Any]) -> Any:
        if self.context.media is None: raise RuntimeError("No media generation provider is configured")
        kind = str(p.get("kind", "image"))
        if kind not in {"image", "audio", "tts", "video"}: raise ValueError("Media kind must be image, audio, tts, or video")
        return await self.context.media(kind, p)

    async def _rag(self, p: dict[str, Any]) -> Any:
        if self.context.rag_query is None: raise RuntimeError("Knowledge retrieval is not configured")
        query = str(p.get("query", ""))
        if not query: raise ValueError("query is required")
        return await self.context.rag_query(query)

    async def _delegate(self, p: dict[str, Any]) -> Any:
        if self.context.workflow_delegate is None: raise RuntimeError("Workflow delegation is not configured")
        workflow_id = str(p.get("workflow_id", ""))
        if not workflow_id: raise ValueError("workflow_id is required")
        return await self.context.workflow_delegate(workflow_id, dict(p.get("inputs", {})))

    def nexusai_tools(self) -> list[Any]:
        """Return native BaseTool objects when the optional runtime is installed."""
        try: from crewai.tools import BaseTool
        except ImportError: return []
        registry = self
        try: owner_loop = asyncio.get_running_loop()
        except RuntimeError: owner_loop = None
        class MediaToolInput(BaseModel):
            kind: str
            prompt: str
            filename: str = "generated_media"
            model: str | None = None
            aspect_ratio: str = "16:9"
            enhance_prompt: bool = True
        class ReportToolInput(BaseModel):
            content: str
            filename: str = "report"
            format: str = "markdown"
        class NativeTool(BaseTool):
            args_schema: type[BaseModel] = ToolInput
            tool_id: str = ""
            async def _arun(self, **arguments: Any) -> str:
                payload = arguments.get("payload") if self.tool_id not in {"media_generation", "report_exporter"} else arguments
                if not isinstance(payload, dict):
                    payload = arguments
                return json.dumps(await registry.run(self.tool_id, payload), default=str)
            def _run(self, **arguments: Any) -> str:
                try: current_loop = asyncio.get_running_loop()
                except RuntimeError: current_loop = None
                if owner_loop is not None and owner_loop.is_running():
                    if current_loop is owner_loop:
                        raise RuntimeError("Synchronous tool execution cannot block its owning event loop")
                    return asyncio.run_coroutine_threadsafe(self._arun(**arguments), owner_loop).result(timeout=900)
                if current_loop is None:
                    return asyncio.run(self._arun(**arguments))
                raise RuntimeError("Use the asynchronous tool interface from an active event loop")
        schemas: dict[str, type[BaseModel]] = {"media_generation": MediaToolInput, "report_exporter": ReportToolInput}
        return [NativeTool(name=item.id, description=f"{item.name}: {item.description}",
                           tool_id=item.id, args_schema=schemas.get(item.id, ToolInput)) for item in TOOLS]

    def nexusgen_tools(self, tool_ids: Iterable[str] | None = None) -> list[Any]:
        """Return native FunctionTool objects when NexusGen is installed."""
        try: from autogen_core.tools import FunctionTool
        except ImportError: return []
        def handler_for(tool_id: str) -> Callable[[dict[str, Any]], Awaitable[str]]:
            async def invoke(payload: dict[str, Any]) -> str:
                return json.dumps(await self.run(tool_id, payload), default=str)
            return invoke
        result = []
        requested = set(tool_ids) if tool_ids is not None else {item.id for item in TOOLS}
        if "sandbox_shell" in requested:
            requested.update({"view_file_numbered", "surgical_file_edit", "fast_workspace_search", "start_background_process", "get_process_logs", "stop_process", "list_running_processes"})
        unknown = requested - {item.id for item in TOOLS}
        if unknown:
            raise LookupError(f"Unknown built-in tool IDs: {sorted(unknown)}")
        if self.context.enabled_ids is not None:
            requested &= self.context.enabled_ids
        for descriptor in TOOLS:
            if descriptor.id not in requested:
                continue
            result.append(FunctionTool(handler_for(descriptor.id), description=descriptor.description, name=descriptor.id))
        return result
