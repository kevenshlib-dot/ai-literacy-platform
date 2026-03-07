"""Material parsing service - extracts text from different file formats."""
import io
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """Base class for all format parsers."""

    @abstractmethod
    def parse(self, file_data: bytes, filename: str) -> str:
        """Extract text content from file data. Returns extracted text."""
        raise NotImplementedError


class PDFParser(BaseParser):
    def parse(self, file_data: bytes, filename: str) -> str:
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


class MarkdownParser(BaseParser):
    def parse(self, file_data: bytes, filename: str) -> str:
        return file_data.decode("utf-8", errors="replace")


class HTMLParser(BaseParser):
    def parse(self, file_data: bytes, filename: str) -> str:
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
        extractor.feed(file_data.decode("utf-8", errors="replace"))
        return "\n".join(extractor.texts)


class CSVParser(BaseParser):
    def parse(self, file_data: bytes, filename: str) -> str:
        return file_data.decode("utf-8", errors="replace")


class JSONParser(BaseParser):
    def parse(self, file_data: bytes, filename: str) -> str:
        import json
        data = json.loads(file_data.decode("utf-8", errors="replace"))
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
    return parser.parse(file_data, filename)


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks for vectorization."""
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap

    return chunks
