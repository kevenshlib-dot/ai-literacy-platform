"""Material parsing service - extracts text from different file formats."""
import io
import json
import logging
import posixpath
import tempfile
import zipfile
from abc import ABC, abstractmethod
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

TEXT_ENCODINGS = ("utf-8-sig", "gb18030")
UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")


def _is_likely_utf16(file_data: bytes) -> bool:
    if file_data.startswith(UTF16_BOMS):
        return True

    if len(file_data) < 4:
        return False

    even_nuls = file_data[0::2].count(0)
    odd_nuls = file_data[1::2].count(0)
    half_len = max(1, len(file_data) // 2)
    return (even_nuls / half_len) > 0.3 or (odd_nuls / half_len) > 0.3


def _text_score(text: str) -> int:
    score = 0
    for ch in text:
        code = ord(ch)
        if ch == "\x00":
            score -= 20
        elif ch in ("\n", "\r", "\t"):
            score += 1
        elif 32 <= code <= 126:
            score += 2
        elif 0x3000 <= code <= 0x303F or 0x3400 <= code <= 0x9FFF:
            score += 2
        elif ch == "\ufffd":
            score -= 10
        elif code < 32:
            score -= 10
        else:
            score -= 4
    return score


def decode_text_bytes(file_data: bytes) -> str:
    """Decode text content with a few common encodings used in uploaded files."""
    last_error: UnicodeDecodeError | None = None
    candidates: list[str] = []

    for encoding in TEXT_ENCODINGS:
        try:
            candidates.append(file_data.decode(encoding))
        except UnicodeDecodeError as exc:
            last_error = exc

    if _is_likely_utf16(file_data):
        for encoding in ("utf-16", "utf-16-le", "utf-16-be"):
            try:
                candidates.append(file_data.decode(encoding))
            except UnicodeDecodeError as exc:
                last_error = exc

    if candidates:
        return max(candidates, key=lambda text: _text_score(sanitize_text(text)))

    if last_error:
        logger.warning("Falling back to utf-8 replacement decoding: %s", last_error)

    return file_data.decode("utf-8", errors="replace")


def sanitize_text(text: str) -> str:
    """Remove control chars that PostgreSQL text fields cannot store."""
    if not text:
        return text

    cleaned = text.replace("\x00", "")
    return "".join(
        ch for ch in cleaned
        if ch in ("\n", "\r", "\t") or ord(ch) >= 32
    )


class BaseParser(ABC):
    """Base class for all format parsers."""

    @abstractmethod
    def parse(self, file_data: bytes, filename: str) -> str:
        """Extract text content from file data. Returns extracted text."""
        raise NotImplementedError


class PDFParser(BaseParser):
    def parse(self, file_data: bytes, filename: str) -> str:
        try:
            return self._parse_with_pymupdf(file_data)
        except Exception as exc:
            logger.warning(
                "PyMuPDF PDF parsing failed for %s, falling back to PyPDF2: %s",
                filename,
                exc,
            )
            return self._parse_with_pypdf2(file_data)

    def _parse_with_pymupdf(self, file_data: bytes) -> str:
        import pymupdf

        text_parts = []
        with pymupdf.open(stream=file_data, filetype="pdf") as document:
            for page in document:
                text = page.get_text("text")
                if text and text.strip():
                    text_parts.append(text.strip())
        return "\n\n".join(text_parts)

    def _parse_with_pypdf2(self, file_data: bytes) -> str:
        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(file_data))
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text.strip())
        return "\n\n".join(text_parts)


class WordParser(BaseParser):
    def parse(self, file_data: bytes, filename: str) -> str:
        from docx import Document
        doc = Document(io.BytesIO(file_data))
        text_parts = []
        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text.strip())
        return "\n\n".join(text_parts)


def extract_text_from_html(html_text: str) -> str:
    from html.parser import HTMLParser as StdHTMLParser

    class TextExtractor(StdHTMLParser):
        def __init__(self):
            super().__init__()
            self.texts = []
            self._skip = False

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self._skip = True

        def handle_endtag(self, tag):
            if tag in ("script", "style"):
                self._skip = False

        def handle_data(self, data):
            if not self._skip and data.strip():
                self.texts.append(data.strip())

    extractor = TextExtractor()
    extractor.feed(html_text)
    return "\n".join(extractor.texts)


class MarkdownParser(BaseParser):
    def parse(self, file_data: bytes, filename: str) -> str:
        return decode_text_bytes(file_data)


class HTMLParser(BaseParser):
    def parse(self, file_data: bytes, filename: str) -> str:
        return extract_text_from_html(decode_text_bytes(file_data))

class EPUBParser(BaseParser):
    """Extract text content from EPUB files by following the OPF spine."""

    def parse(self, file_data: bytes, filename: str) -> str:
        try:
            return self._parse_with_ebooklib(file_data, filename)
        except Exception as exc:
            logger.warning(
                "EbookLib parsing failed for %s, falling back to built-in EPUB parser: %s",
                filename,
                exc,
            )
            return self._parse_with_native_epub(file_data, filename)

    def _parse_with_ebooklib(self, file_data: bytes, filename: str) -> str:
        from ebooklib import ITEM_DOCUMENT, epub

        with tempfile.NamedTemporaryFile(suffix=".epub") as temp_file:
            temp_file.write(file_data)
            temp_file.flush()

            book = epub.read_epub(temp_file.name)
            text_parts = []
            for spine_entry in book.spine:
                if isinstance(spine_entry, tuple):
                    item_id = spine_entry[0]
                else:
                    item_id = spine_entry

                if not item_id:
                    continue

                item = book.get_item_with_id(item_id)
                if item is None or item.get_type() != ITEM_DOCUMENT:
                    continue

                chapter_text = extract_text_from_html(decode_text_bytes(item.get_content()))
                if chapter_text.strip():
                    text_parts.append(chapter_text.strip())

        if not text_parts:
            raise ValueError(f"EPUB 未提取到正文文本: {filename}")

        return "\n\n".join(text_parts)

    def _parse_with_native_epub(self, file_data: bytes, filename: str) -> str:
        with zipfile.ZipFile(io.BytesIO(file_data)) as archive:
            container_root = ET.fromstring(archive.read("META-INF/container.xml"))
            rootfile = container_root.find(".//{*}rootfile")
            if rootfile is None:
                raise ValueError(f"EPUB 缺少 rootfile: {filename}")

            opf_path = rootfile.attrib.get("full-path")
            if not opf_path:
                raise ValueError(f"EPUB OPF 路径缺失: {filename}")

            package_root = ET.fromstring(archive.read(opf_path))
            manifest = {}
            for item in package_root.findall(".//{*}manifest/{*}item"):
                item_id = item.attrib.get("id")
                href = item.attrib.get("href")
                if item_id and href:
                    manifest[item_id] = {
                        "href": href,
                        "media_type": item.attrib.get("media-type", ""),
                    }

            spine_refs = [
                itemref.attrib.get("idref")
                for itemref in package_root.findall(".//{*}spine/{*}itemref")
                if itemref.attrib.get("idref")
            ]
            if not spine_refs:
                raise ValueError(f"EPUB 缺少 spine 内容: {filename}")

            base_dir = posixpath.dirname(opf_path)
            text_parts = []
            for item_id in spine_refs:
                manifest_item = manifest.get(item_id)
                if not manifest_item:
                    continue

                href = manifest_item["href"]
                media_type = manifest_item["media_type"]
                if not (
                    media_type in {"application/xhtml+xml", "text/html"}
                    or href.lower().endswith((".xhtml", ".html", ".htm"))
                ):
                    continue

                chapter_path = posixpath.normpath(posixpath.join(base_dir, href))
                try:
                    chapter_data = archive.read(chapter_path)
                except KeyError:
                    logger.warning("Missing EPUB chapter resource: %s", chapter_path)
                    continue

                chapter_text = extract_text_from_html(decode_text_bytes(chapter_data))
                if chapter_text.strip():
                    text_parts.append(chapter_text.strip())

            if not text_parts:
                raise ValueError(f"EPUB 未提取到正文文本: {filename}")

            return "\n\n".join(text_parts)


class CSVParser(BaseParser):
    def parse(self, file_data: bytes, filename: str) -> str:
        return decode_text_bytes(file_data)


class JSONParser(BaseParser):
    def parse(self, file_data: bytes, filename: str) -> str:
        data = json.loads(decode_text_bytes(file_data))
        return json.dumps(data, ensure_ascii=False, indent=2)


class ImageParser(BaseParser):
    """Placeholder for OCR-based image parsing (PaddleOCR)."""
    def parse(self, file_data: bytes, filename: str) -> str:
        logger.info(f"Image parsing placeholder for {filename} - requires PaddleOCR")
        return f"[图片素材: {filename} - 待OCR处理]"


class VideoParser(BaseParser):
    """Placeholder for video transcription (Whisper)."""
    def parse(self, file_data: bytes, filename: str) -> str:
        logger.info(f"Video parsing placeholder for {filename} - requires Whisper")
        return f"[视频素材: {filename} - 待转录处理]"


class AudioParser(BaseParser):
    """Placeholder for audio ASR (Whisper)."""
    def parse(self, file_data: bytes, filename: str) -> str:
        logger.info(f"Audio parsing placeholder for {filename} - requires Whisper")
        return f"[音频素材: {filename} - 待ASR处理]"


# Parser registry
PARSERS: dict[str, BaseParser] = {
    "pdf": PDFParser(),
    "word": WordParser(),
    "epub": EPUBParser(),
    "markdown": MarkdownParser(),
    "html": HTMLParser(),
    "csv": CSVParser(),
    "json": JSONParser(),
    "image": ImageParser(),
    "video": VideoParser(),
    "audio": AudioParser(),
}


def get_parser(format: str) -> BaseParser:
    parser = PARSERS.get(format)
    if not parser:
        raise ValueError(f"不支持的解析格式: {format}")
    return parser


def parse_material(file_data: bytes, filename: str, format: str) -> str:
    """Parse a material file and return extracted text."""
    parser = get_parser(format)
    return sanitize_text(parser.parse(file_data, filename))


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks for vectorization."""
    sanitized_text = sanitize_text(text)
    if not sanitized_text:
        return []

    chunks = []
    start = 0
    while start < len(sanitized_text):
        end = start + chunk_size
        chunk = sanitized_text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap

    return chunks
