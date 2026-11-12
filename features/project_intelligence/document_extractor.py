"""Extract plain text from uploaded PDF and DOCX project documents.

The module never executes document content, never writes uploads to disk and
never raises raw parser exceptions to the caller. Every call returns a
structured result:

    {
        "status": "success" | "error",
        "text": str,
        "error": str | None,
        "metadata": {
            "filename": str,
            "extension": str,
            "characters": int,
            "pages": int | None,
        },
    }

The optional parsers are imported lazily so the rest of the application can
start even when ``pypdf`` or ``python-docx`` is not installed.
"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import Any

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 50
MAX_TEXT_CHARACTERS = 60_000
SUPPORTED_EXTENSIONS = (".pdf", ".docx")

_DEFAULT_FILENAME = "document"


def sanitize_filename(filename: str) -> str:
    """Return only the final path component of an untrusted filename."""
    raw = str(filename or "")
    # Treat both Windows and POSIX separators as separators regardless of host.
    candidate = raw.replace("\\", "/").split("/")[-1]
    candidate = candidate.replace("\x00", "").strip()
    return candidate or _DEFAULT_FILENAME


def _metadata(
    filename: str,
    extension: str,
    characters: int = 0,
    pages: int | None = None,
) -> dict[str, Any]:
    return {
        "filename": sanitize_filename(filename),
        "extension": extension,
        "characters": characters,
        "pages": pages,
    }


def _result(status: str, text: str, error: str | None, metadata: dict[str, Any]) -> dict[str, Any]:
    return {"status": status, "text": text, "error": error, "metadata": metadata}


def _error(
    message: str,
    filename: str,
    extension: str,
    characters: int = 0,
    pages: int | None = None,
) -> dict[str, Any]:
    return _result("error", "", message, _metadata(filename, extension, characters, pages))


def _success(
    text: str,
    filename: str,
    extension: str,
    pages: int | None = None,
) -> dict[str, Any]:
    return _result("success", text, None, _metadata(filename, extension, len(text), pages))


def normalize_text(raw: str) -> str:
    """Normalize whitespace so extracted text is stable and compact."""
    text = str(raw or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\x00", "")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _too_long_error(filename: str, extension: str, characters: int, pages: int | None) -> dict[str, Any]:
    return _error(
        "The extracted text is too long "
        f"({characters:,} characters; limit is {MAX_TEXT_CHARACTERS:,}). "
        "Please upload a shorter document or paste only the requirement section.",
        filename,
        extension,
        characters,
        pages,
    )


def _extract_pdf(file_bytes: bytes, filename: str) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return _error(
            "PDF extraction is unavailable because the 'pypdf' package is not installed.",
            filename,
            ".pdf",
        )

    try:
        reader = PdfReader(BytesIO(file_bytes))
    except Exception:
        return _error(
            "The PDF could not be read. It may be corrupt or not a valid PDF file.",
            filename,
            ".pdf",
        )

    try:
        if getattr(reader, "is_encrypted", False):
            return _error(
                "The PDF is encrypted or password-protected and cannot be read.",
                filename,
                ".pdf",
            )

        pages = reader.pages
        page_count = len(pages)

        if page_count > MAX_PDF_PAGES:
            return _error(
                f"The PDF has {page_count} pages; the limit is {MAX_PDF_PAGES}.",
                filename,
                ".pdf",
                pages=page_count,
            )

        chunks: list[str] = []
        for page in pages:
            try:
                chunks.append(page.extract_text() or "")
            except Exception:
                # A single unreadable page must not hide the rest of the document.
                chunks.append("")

        text = normalize_text("\n".join(chunks))

        if not text:
            return _error(
                "No extractable text was found. The PDF may be scanned or image-only; "
                "OCR is not supported.",
                filename,
                ".pdf",
                pages=page_count,
            )

        if len(text) > MAX_TEXT_CHARACTERS:
            return _too_long_error(filename, ".pdf", len(text), page_count)

        return _success(text, filename, ".pdf", page_count)
    except Exception:
        return _error(
            "The PDF could not be processed. It may be corrupt or unsupported.",
            filename,
            ".pdf",
        )


def _extract_docx(file_bytes: bytes, filename: str) -> dict[str, Any]:
    try:
        import docx
    except ImportError:
        return _error(
            "DOCX extraction is unavailable because the 'python-docx' package is not installed.",
            filename,
            ".docx",
        )

    try:
        document = docx.Document(BytesIO(file_bytes))
    except Exception:
        return _error(
            "The DOCX file could not be read. It may be corrupt or not a valid DOCX file.",
            filename,
            ".docx",
        )

    try:
        parts: list[str] = [
            paragraph.text for paragraph in document.paragraphs if paragraph.text
        ]

        # Requirement documents frequently put skills and headcounts in tables,
        # so table cell text is part of the extractable content.
        for table in document.tables:
            for row in table.rows:
                cells = [normalize_text(cell.text) for cell in row.cells]
                cells = [cell for cell in cells if cell]
                if cells:
                    parts.append(" | ".join(cells))

        text = normalize_text("\n".join(parts))

        if not text:
            return _error(
                "No extractable text was found in the DOCX file.",
                filename,
                ".docx",
            )

        if len(text) > MAX_TEXT_CHARACTERS:
            return _too_long_error(filename, ".docx", len(text), None)

        return _success(text, filename, ".docx", None)
    except Exception:
        return _error(
            "The DOCX file could not be processed. It may be corrupt or unsupported.",
            filename,
            ".docx",
        )


def extract_document(file_bytes: bytes, filename: str) -> dict[str, Any]:
    """Validate an upload and return its extracted plain text."""
    safe_name = sanitize_filename(filename)
    extension = Path(safe_name).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        return _error(
            "Unsupported file type. Upload a .pdf or .docx document.",
            safe_name,
            extension,
        )

    if not file_bytes:
        return _error("The uploaded file is empty.", safe_name, extension)

    if len(file_bytes) > MAX_UPLOAD_BYTES:
        limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        return _error(
            f"The uploaded file is larger than the {limit_mb} MB limit.",
            safe_name,
            extension,
        )

    if extension == ".pdf":
        return _extract_pdf(file_bytes, safe_name)

    return _extract_docx(file_bytes, safe_name)


# Alias used by callers that prefer a text-oriented name.
extract_text = extract_document
