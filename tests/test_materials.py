import io
import zipfile

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles


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
        # await conn.execute(text("TRUNCATE TABLE users CASCADE"))
        await conn.execute(text("TRUNCATE TABLE materials CASCADE"))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await init_roles(session)
        await session.commit()
    await engine.dispose()
    yield


def get_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def register_user(client, role="organizer"):
    """Helper to register a user and return auth token."""
    import uuid
    unique = uuid.uuid4().hex[:8]
    resp = await client.post("/api/v1/auth/register", json={
        "username": f"user_{unique}",
        "email": f"{unique}@test.com",
        "password": "password123",
        "role": role,
    })
    return resp.json()["access_token"]


def build_test_epub_bytes() -> bytes:
    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
    content_opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>EPUB测试</dc:title>
  </metadata>
  <manifest>
    <item id="chapter2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter1"/>
    <itemref idref="chapter2"/>
  </spine>
</package>
"""
    chapter1 = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body><h1>第一章</h1><p>这是EPUB第一章内容。</p></body>
</html>
"""
    chapter2 = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body><h1>第二章</h1><p>这是EPUB第二章内容。</p></body>
</html>
"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", container_xml)
        archive.writestr("OEBPS/content.opf", content_opf)
        archive.writestr("OEBPS/chapter1.xhtml", chapter1)
        archive.writestr("OEBPS/chapter2.xhtml", chapter2)
    return buf.getvalue()


# ---- Upload Tests ----

@pytest.mark.asyncio
async def test_upload_pdf():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.post(
            "/api/v1/materials",
            files={"file": ("test.pdf", b"%PDF-1.4 fake content", "application/pdf")},
            data={"title": "测试PDF素材"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "测试PDF素材"
    assert data["format"] == "pdf"
    assert data["status"] == "uploaded"
    assert data["file_size"] > 0


@pytest.mark.asyncio
async def test_upload_word():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.post(
            "/api/v1/materials",
            files={"file": ("doc.docx", b"fake docx content", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"title": "Word文档", "category": "教材"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
    assert resp.json()["format"] == "word"
    assert resp.json()["category"] == "教材"


@pytest.mark.asyncio
async def test_upload_epub():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.post(
            "/api/v1/materials",
            files={"file": ("book.epub", build_test_epub_bytes(), "application/epub+zip")},
            data={"title": "EPUB电子书"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
    assert resp.json()["format"] == "epub"


@pytest.mark.asyncio
async def test_upload_image():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.post(
            "/api/v1/materials",
            files={"file": ("photo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 100, "image/png")},
            data={"title": "测试图片", "tags": "AI,图片素材"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["format"] == "image"
    assert data["tags"] == ["AI", "图片素材"]


@pytest.mark.asyncio
async def test_upload_csv():
    async with get_client() as client:
        token = await register_user(client, "admin")
        csv_content = b"name,score\nAlice,95\nBob,87"
        resp = await client.post(
            "/api/v1/materials",
            files={"file": ("data.csv", csv_content, "text/csv")},
            data={"title": "成绩数据"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
    assert resp.json()["format"] == "csv"


@pytest.mark.asyncio
async def test_upload_unsupported_format():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.post(
            "/api/v1/materials",
            files={"file": ("app.exe", b"binary stuff", "application/octet-stream")},
            data={"title": "不支持的文件"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 400
    assert "不支持" in resp.json()["detail"]


# ---- Permission Tests ----

@pytest.mark.asyncio
async def test_upload_forbidden_for_examinee():
    async with get_client() as client:
        token = await register_user(client, "examinee")
        resp = await client.post(
            "/api/v1/materials",
            files={"file": ("test.pdf", b"content", "application/pdf")},
            data={"title": "无权上传"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 403


# ---- Batch Upload Tests ----

@pytest.mark.asyncio
async def test_batch_upload_triggers_parse(monkeypatch):
    scheduled_material_ids = []

    async def fake_trigger_parse(material_id):
        scheduled_material_ids.append(str(material_id))

    monkeypatch.setattr(
        "app.api.v1.endpoints.materials.trigger_parse",
        fake_trigger_parse,
    )

    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.post(
            "/api/v1/materials/batch",
            files=[
                ("files", ("a.pdf", b"pdf content", "application/pdf")),
                ("files", ("b.csv", b"x,y\n1,2", "text/csv")),
            ],
            data={"category": "批量上传"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["uploaded"] == 2
    assert data["failed"] == 0
    assert len(scheduled_material_ids) == 2
    assert set(scheduled_material_ids) == {item["id"] for item in data["materials"]}


# ---- List / Query Tests ----

@pytest.mark.asyncio
async def test_list_materials():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        # Upload first
        await client.post(
            "/api/v1/materials",
            files={"file": ("list_test.pdf", b"content", "application/pdf")},
            data={"title": "列表测试素材"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # List
        resp = await client.get(
            "/api/v1/materials",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["data"]) >= 1


@pytest.mark.asyncio
async def test_list_materials_with_keyword():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        await client.post(
            "/api/v1/materials",
            files={"file": ("search.pdf", b"content", "application/pdf")},
            data={"title": "特殊搜索关键词素材"},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = await client.get(
            "/api/v1/materials?keyword=特殊搜索",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


# ---- Get / Download / Delete Tests ----

@pytest.mark.asyncio
async def test_get_material_by_id():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        upload = await client.post(
            "/api/v1/materials",
            files={"file": ("get_test.pdf", b"content", "application/pdf")},
            data={"title": "详情测试"},
            headers={"Authorization": f"Bearer {token}"},
        )
        mid = upload.json()["id"]
        resp = await client.get(
            f"/api/v1/materials/{mid}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["title"] == "详情测试"


@pytest.mark.asyncio
async def test_get_material_not_found():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        resp = await client.get(
            "/api/v1/materials/00000000-0000-0000-0000-000000000000",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_material():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        upload = await client.post(
            "/api/v1/materials",
            files={"file": ("dl_test.pdf", b"downloadable content", "application/pdf")},
            data={"title": "下载测试"},
            headers={"Authorization": f"Bearer {token}"},
        )
        mid = upload.json()["id"]
        resp = await client.get(
            f"/api/v1/materials/{mid}/download",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert "download_url" in resp.json()


@pytest.mark.asyncio
async def test_delete_material():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        upload = await client.post(
            "/api/v1/materials",
            files={"file": ("del_test.pdf", b"to be deleted", "application/pdf")},
            data={"title": "删除测试"},
            headers={"Authorization": f"Bearer {token}"},
        )
        mid = upload.json()["id"]
        resp = await client.delete(
            f"/api/v1/materials/{mid}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_parsed_material():
    async with get_client() as client:
        token = await register_user(client, "organizer")
        upload = await client.post(
            "/api/v1/materials",
            files={"file": ("parsed.md", b"# AI\n\n" + "knowledge " * 200, "text/markdown")},
            data={"title": "已解析素材删除"},
            headers={"Authorization": f"Bearer {token}"},
        )
        mid = upload.json()["id"]

        parse_resp = await client.post(
            f"/api/v1/materials/{mid}/parse",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert parse_resp.status_code == 200
        assert parse_resp.json()["parsed"] is True

        resp = await client.delete(
            f"/api/v1/materials/{mid}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_forbidden_for_examinee():
    async with get_client() as client:
        org_token = await register_user(client, "organizer")
        upload = await client.post(
            "/api/v1/materials",
            files={"file": ("exam_del.pdf", b"content", "application/pdf")},
            data={"title": "考生无法删除"},
            headers={"Authorization": f"Bearer {org_token}"},
        )
        mid = upload.json()["id"]
        exam_token = await register_user(client, "examinee")
        resp = await client.delete(
            f"/api/v1/materials/{mid}",
            headers={"Authorization": f"Bearer {exam_token}"},
        )
    assert resp.status_code == 403
