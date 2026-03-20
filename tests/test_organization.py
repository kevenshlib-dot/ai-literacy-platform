"""Tests for multi-tenant organization management (T030)."""
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.main import app
from app.core.database import Base, get_db
from app.core.config import settings
from app.services.user_service import init_roles
from app.services.organization_service import _generate_slug


# ---- Unit Tests ----

def test_generate_slug():
    assert _generate_slug("北京大学") == "北京大学"
    assert _generate_slug("Test Org") == "test-org"
    assert _generate_slug("AI 素养中心!") == "ai-素养中心"


# ---- Integration Tests ----

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
        # Drop and recreate to handle schema changes
        await conn.execute(text("DROP TABLE IF EXISTS organizations CASCADE"))
        await conn.run_sync(Base.metadata.create_all)
        # Add org_id column to users if missing
        await conn.execute(text("""
            DO $$ BEGIN
                ALTER TABLE users ADD COLUMN org_id UUID REFERENCES organizations(id);
            EXCEPTION WHEN duplicate_column THEN NULL;
            END $$;
        """))
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE organizations CASCADE"))
        # await conn.execute(text("TRUNCATE TABLE users CASCADE"))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        await init_roles(session)
        await session.commit()
    await engine.dispose()
    yield


def get_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def register_user(client, role="admin"):
    import uuid
    unique = uuid.uuid4().hex[:8]
    resp = await client.post("/api/v1/auth/register", json={
        "username": f"user_{unique}",
        "email": f"{unique}@test.com",
        "password": "password123",
        "role": role,
    })
    data = resp.json()
    return data["access_token"], data["user"]["id"]


@pytest.mark.asyncio
async def test_create_organization():
    async with get_client() as client:
        token, _ = await register_user(client, "admin")
        resp = await client.post("/api/v1/organizations", json={
            "name": "测试机构",
            "description": "一个测试机构",
            "contact_email": "test@org.com",
        }, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "测试机构"
    assert data["slug"] == "测试机构"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_create_duplicate_org():
    async with get_client() as client:
        token, _ = await register_user(client, "admin")
        headers = {"Authorization": f"Bearer {token}"}
        await client.post("/api/v1/organizations", json={"name": "重复机构"}, headers=headers)
        resp = await client.post("/api/v1/organizations", json={"name": "重复机构"}, headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_organizations():
    async with get_client() as client:
        token, _ = await register_user(client, "admin")
        headers = {"Authorization": f"Bearer {token}"}
        await client.post("/api/v1/organizations", json={"name": "机构A"}, headers=headers)
        await client.post("/api/v1/organizations", json={"name": "机构B"}, headers=headers)

        resp = await client.get("/api/v1/organizations", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_get_organization():
    async with get_client() as client:
        token, _ = await register_user(client, "admin")
        headers = {"Authorization": f"Bearer {token}"}
        create_resp = await client.post("/api/v1/organizations",
                                        json={"name": "详情机构", "description": "测试描述"},
                                        headers=headers)
        org_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/organizations/{org_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["description"] == "测试描述"


@pytest.mark.asyncio
async def test_update_organization():
    async with get_client() as client:
        token, _ = await register_user(client, "admin")
        headers = {"Authorization": f"Bearer {token}"}
        create_resp = await client.post("/api/v1/organizations",
                                        json={"name": "更新机构"},
                                        headers=headers)
        org_id = create_resp.json()["id"]

        resp = await client.put(f"/api/v1/organizations/{org_id}",
                               json={"description": "已更新"},
                               headers=headers)
    assert resp.status_code == 200
    assert resp.json()["updated"] is True


@pytest.mark.asyncio
async def test_add_member_to_org():
    async with get_client() as client:
        token, admin_id = await register_user(client, "admin")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post("/api/v1/organizations",
                                        json={"name": "成员机构"},
                                        headers=headers)
        org_id = create_resp.json()["id"]

        # Create an examinee user
        ex_token, ex_id = await register_user(client, "examinee")

        resp = await client.post(f"/api/v1/organizations/{org_id}/members/{ex_id}",
                                headers=headers)
    assert resp.status_code == 200
    assert resp.json()["org_name"] == "成员机构"


@pytest.mark.asyncio
async def test_list_members():
    async with get_client() as client:
        token, _ = await register_user(client, "admin")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post("/api/v1/organizations",
                                        json={"name": "列表机构"},
                                        headers=headers)
        org_id = create_resp.json()["id"]

        _, user_id = await register_user(client, "examinee")
        await client.post(f"/api/v1/organizations/{org_id}/members/{user_id}", headers=headers)

        resp = await client.get(f"/api/v1/organizations/{org_id}/members", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_remove_member():
    async with get_client() as client:
        token, _ = await register_user(client, "admin")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post("/api/v1/organizations",
                                        json={"name": "移除机构"},
                                        headers=headers)
        org_id = create_resp.json()["id"]

        _, user_id = await register_user(client, "examinee")
        await client.post(f"/api/v1/organizations/{org_id}/members/{user_id}", headers=headers)

        resp = await client.delete(f"/api/v1/organizations/{org_id}/members/{user_id}",
                                   headers=headers)
    assert resp.status_code == 200
    assert resp.json()["removed"] is True


@pytest.mark.asyncio
async def test_org_stats():
    async with get_client() as client:
        token, _ = await register_user(client, "admin")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post("/api/v1/organizations",
                                        json={"name": "统计机构"},
                                        headers=headers)
        org_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/organizations/{org_id}/stats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["member_count"] == 0
    assert data["name"] == "统计机构"


@pytest.mark.asyncio
async def test_update_org_config():
    async with get_client() as client:
        token, _ = await register_user(client, "admin")
        headers = {"Authorization": f"Bearer {token}"}

        create_resp = await client.post("/api/v1/organizations",
                                        json={"name": "配置机构"},
                                        headers=headers)
        org_id = create_resp.json()["id"]

        resp = await client.put(f"/api/v1/organizations/{org_id}/config",
                               json={"theme": "dark", "logo": "custom.png"},
                               headers=headers)
    assert resp.status_code == 200
    assert resp.json()["config"]["theme"] == "dark"


@pytest.mark.asyncio
async def test_data_isolation():
    """Members of different orgs should be isolated."""
    async with get_client() as client:
        token, _ = await register_user(client, "admin")
        headers = {"Authorization": f"Bearer {token}"}

        # Create two orgs
        org_a = (await client.post("/api/v1/organizations",
                                   json={"name": "机构甲"},
                                   headers=headers)).json()["id"]
        org_b = (await client.post("/api/v1/organizations",
                                   json={"name": "机构乙"},
                                   headers=headers)).json()["id"]

        # Add users to different orgs
        _, user_a = await register_user(client, "examinee")
        _, user_b = await register_user(client, "examinee")
        await client.post(f"/api/v1/organizations/{org_a}/members/{user_a}", headers=headers)
        await client.post(f"/api/v1/organizations/{org_b}/members/{user_b}", headers=headers)

        # Check isolation
        members_a = (await client.get(f"/api/v1/organizations/{org_a}/members",
                                      headers=headers)).json()
        members_b = (await client.get(f"/api/v1/organizations/{org_b}/members",
                                      headers=headers)).json()

    assert len(members_a) == 1
    assert len(members_b) == 1
    assert members_a[0]["id"] != members_b[0]["id"]
