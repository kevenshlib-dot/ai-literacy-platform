import io
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.services.parsing_service import (
    parse_material, chunk_text,
    PDFParser, WordParser, MarkdownParser, HTMLParser, CSVParser, JSONParser,
)


# ---- Unit Tests for Parsers ----

def test_markdown_parser():
    text = parse_material(b"# Hello\n\nThis is **markdown**.", "test.md", "markdown")
    assert "Hello" in text
    assert "markdown" in text


def test_html_parser():
    html = b"<html><body><h1>Title</h1><p>Content here</p><script>var x=1;</script></body></html>"
    text = parse_material(html, "page.html", "html")
    assert "Title" in text
    assert "Content here" in text
    assert "var x" not in text  # Script content should be excluded


def test_csv_parser():
    csv_data = b"name,age\nAlice,30\nBob,25"
    text = parse_material(csv_data, "data.csv", "csv")
    assert "Alice" in text
    assert "Bob" in text


def test_json_parser():
    json_data = b'{"name": "test", "value": 42}'
    text = parse_material(json_data, "config.json", "json")
    assert "test" in text
    assert "42" in text


def test_image_parser_placeholder():
    text = parse_material(b"\x89PNG fake", "photo.png", "image")
    assert "图片素材" in text


def test_video_parser_placeholder():
    text = parse_material(b"fake video", "clip.mp4", "video")
    assert "视频素材" in text


def test_audio_parser_placeholder():
    text = parse_material(b"fake audio", "sound.mp3", "audio")
    assert "音频素材" in text


def test_unsupported_format():
    with pytest.raises(ValueError, match="不支持"):
        parse_material(b"data", "file.xyz", "xyz")


# ---- Chunking Tests ----

def test_chunk_text_basic():
    text = "A" * 1000
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) >= 2
    assert len(chunks[0]) == 500


def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_small():
    chunks = chunk_text("Short text", chunk_size=500, overlap=50)
    assert len(chunks) == 1
    assert chunks[0] == "Short text"


# ---- PDF Parser Test (with real PyPDF2) ----

def test_pdf_parser():
    """Create a minimal valid PDF and test parsing."""
    from PyPDF2 import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    parser = PDFParser()
    text = parser.parse(pdf_bytes, "blank.pdf")
    # Blank page may produce empty text
    assert isinstance(text, str)


# ---- Word Parser Test ----

def test_word_parser():
    """Create a minimal valid docx and test parsing."""
    from docx import Document
    doc = Document()
    doc.add_paragraph("第一段内容")
    doc.add_paragraph("第二段内容")
    buf = io.BytesIO()
    doc.save(buf)
    docx_bytes = buf.getvalue()

    parser = WordParser()
    text = parser.parse(docx_bytes, "test.docx")
    assert "第一段内容" in text
    assert "第二段内容" in text


# ---- Integration Tests: Parse API ----

async def override_get_db():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    await engine.dispose()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
async def setup_db():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE users CASCADE"))
        await conn.execute(text("TRUNCATE TABLE materials CASCADE"))
        await conn.execute(text("TRUNCATE TABLE knowledge_units CASCADE"))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await init_roles(session)
        await session.commit()
    await engine.dispose()
    yield


def get_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def register_user(client, role="organizer"):
    import uuid
    unique = uuid.uuid4().hex[:8]
    resp = await client.post("/api/v1/auth/register", json={
        "username": f"user_{unique}",
        "email": f"{unique}@test.com",
        "password": "password123",
        "role": role,
    })
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_manual_parse_markdown():
    """Upload a markdown file, trigger manual parse, check knowledge units."""
    async with get_client() as client:
        token = await register_user(client, "organizer")

        # Upload markdown
        md_content = ("# AI基础认知\n\n" + "人工智能是计算机科学的一个分支。" * 50 + "\n\n"
                      "## 机器学习\n\n" + "机器学习是AI的核心技术之一。" * 50)
        upload = await client.post(
            "/api/v1/materials",
            files={"file": ("ai_basics.md", md_content.encode(), "text/markdown")},
            data={"title": "AI基础教材"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert upload.status_code == 201
        mid = upload.json()["id"]

        # Trigger manual parse
        parse_resp = await client.post(
            f"/api/v1/materials/{mid}/parse",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert parse_resp.status_code == 200
        assert parse_resp.json()["parsed"] is True

        # Check knowledge units
        ku_resp = await client.get(
            f"/api/v1/materials/{mid}/knowledge-units",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert ku_resp.status_code == 200
        data = ku_resp.json()
        assert data["total_units"] > 0
        assert data["status"] == "parsed"


@pytest.mark.asyncio
async def test_manual_parse_word():
    """Upload a Word document, trigger parse, verify knowledge units."""
    from docx import Document
    doc = Document()
    doc.add_paragraph("AI伦理与治理概述")
    for i in range(10):
        doc.add_paragraph(f"第{i+1}条伦理准则：确保人工智能系统的公平性和透明性。" * 5)
    buf = io.BytesIO()
    doc.save(buf)
    docx_bytes = buf.getvalue()

    async with get_client() as client:
        token = await register_user(client, "organizer")
        upload = await client.post(
            "/api/v1/materials",
            files={"file": ("ethics.docx", docx_bytes,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"title": "AI伦理教材"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert upload.status_code == 201
        mid = upload.json()["id"]

        parse_resp = await client.post(
            f"/api/v1/materials/{mid}/parse",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert parse_resp.status_code == 200
        assert parse_resp.json()["parsed"] is True

        ku_resp = await client.get(
            f"/api/v1/materials/{mid}/knowledge-units",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert ku_resp.status_code == 200
        assert ku_resp.json()["total_units"] > 0


@pytest.mark.asyncio
async def test_parse_material_not_found():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.post(
            "/api/v1/materials/00000000-0000-0000-0000-000000000000/parse",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_auto_parse_on_upload():
    """Verify that uploading a CSV triggers background parsing automatically."""
    async with get_client() as client:
        token = await register_user(client, "organizer")
        upload = await client.post(
            "/api/v1/materials",
            files={"file": ("test.csv", b"a,b\n1,2", "text/csv")},
            data={"title": "自动解析素材"},
            headers={"Authorization": f"Bearer {token}"},
        )
        mid = upload.json()["id"]

        # Background parse runs after response; wait briefly
        import asyncio
        await asyncio.sleep(0.5)

        resp = await client.get(
            f"/api/v1/materials/{mid}/knowledge-units",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    # Auto-parsing should have created knowledge units
    assert resp.json()["total_units"] >= 1
