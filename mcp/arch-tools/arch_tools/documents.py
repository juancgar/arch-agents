"""Text extraction for the paper index: Markdown, plain text and PDF (with page offsets)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from .chunking import Heading, markdown_headings, plain_headings

TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
PDF_SUFFIXES = {".pdf"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | PDF_SUFFIXES


class ExtractionError(Exception):
    pass


@dataclass
class Document:
    path: Path
    kind: str  # "md" | "txt" | "pdf"
    text: str
    title: str
    headings: list[Heading] = field(default_factory=list)
    page_starts: list[int] = field(default_factory=list)  # PDF: offset of each page's first character


def _title_from_filename(path: Path) -> str:
    return re.sub(r"[_\-]+", " ", path.stem).strip() or path.name


def _front_matter_title(text: str) -> str | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4, 8192)
    if end == -1:
        return None
    m = re.search(r"(?m)^title:\s*(.+?)\s*$", text[4:end])
    if not m:
        return None
    return m.group(1).strip().strip("\"'") or None


def _read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("latin-1")
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")


def extract_markdown(path: Path) -> Document:
    text = _read_text_file(path)
    headings = markdown_headings(text)
    title = _front_matter_title(text)
    if not title:
        top = next((h for h in headings if h.level == 1), None)
        title = top.title if top else _title_from_filename(path)
    return Document(path, "md", text, title, headings)


def extract_plain(path: Path) -> Document:
    text = _read_text_file(path)
    headings = sorted(markdown_headings(text) + plain_headings(text), key=lambda h: h.offset)
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    title = first.lstrip("# ").strip() if 0 < len(first) <= 150 else _title_from_filename(path)
    return Document(path, "txt", text, title, headings)


_PDF_NOISE_LINE = re.compile(
    r"^(arxiv:|published as|accepted (at|to)|under review|preprint|proceedings|workshop|journal|vol\.|"
    r"copyright|©|\d+$)",
    re.IGNORECASE,
)


def _clean_pdf_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # de-hyphenate line breaks
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _plausible_pdf_title(title: str | None) -> bool:
    if not title:
        return False
    t = title.strip()
    if len(t) < 8 or len(t) > 300 or not re.search(r"[A-Za-z]{3}", t):
        return False
    lowered = t.lower()
    if lowered in {"untitled", "title", "paper", "article", "manuscript"}:
        return False
    if lowered.endswith((".pdf", ".dvi", ".doc", ".docx", ".tex", ".ps")) or lowered.startswith("microsoft word"):
        return False
    return True


def extract_pdf(path: Path) -> Document:
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    from pypdf import PdfReader  # imported lazily: only the index subcommand needs it

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001 - pypdf raises a variety of errors
                raise ExtractionError(f"encrypted PDF: {exc}") from exc
        pages = []
        for page in reader.pages:
            try:
                pages.append(_clean_pdf_text(page.extract_text() or ""))
            except Exception:  # noqa: BLE001 - one bad page must not drop the document
                pages.append("")
        meta_title = None
        try:
            meta_title = reader.metadata.title if reader.metadata else None
        except Exception:  # noqa: BLE001
            meta_title = None
    except ExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"unreadable PDF: {type(exc).__name__}: {exc}") from exc

    text_parts: list[str] = []
    page_starts: list[int] = []
    offset = 0
    for page_text in pages:
        page_starts.append(offset)
        text_parts.append(page_text)
        offset += len(page_text) + 2
    text = "\n\n".join(text_parts)

    title = " ".join(str(meta_title).split()) if _plausible_pdf_title(meta_title) else None
    if not title and pages:
        for line in pages[0].splitlines()[:15]:
            line = line.strip()
            if len(line.split()) >= 3 and len(line) <= 200 and "@" not in line and not _PDF_NOISE_LINE.match(line):
                title = line
                break
    return Document(path, "pdf", text, title or _title_from_filename(path), plain_headings(text), page_starts)


def extract_document(path: Path) -> Document:
    suffix = path.suffix.lower()
    if suffix in PDF_SUFFIXES:
        return extract_pdf(path)
    if suffix in {".md", ".markdown"}:
        return extract_markdown(path)
    if suffix == ".txt":
        return extract_plain(path)
    raise ExtractionError(f"unsupported file type: {suffix}")
