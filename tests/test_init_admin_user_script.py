from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts.init_admin_user import AdminInitError, init_admin_user


@pytest.mark.asyncio
async def test_init_admin_user_creates_admin_when_missing(monkeypatch):
    db = object()
    created_user = SimpleNamespace(
        username="admin",
        email="admin@example.com",
        is_active=True,
        role=SimpleNamespace(name=SimpleNamespace(value="admin")),
    )

    init_roles = AsyncMock()
    get_user_by_username = AsyncMock(return_value=None)
    get_user_by_email = AsyncMock(return_value=None)
    create_user = AsyncMock(return_value=created_user)

    monkeypatch.setattr("scripts.init_admin_user.init_roles", init_roles)
    monkeypatch.setattr(
        "scripts.init_admin_user.get_user_by_username",
        get_user_by_username,
    )
    monkeypatch.setattr("scripts.init_admin_user.get_user_by_email", get_user_by_email)
    monkeypatch.setattr("scripts.init_admin_user.create_user", create_user)

    user = await init_admin_user(
        db,
        username="admin",
        email="admin@example.com",
        password="admin123",
    )

    init_roles.assert_awaited_once_with(db)
    get_user_by_username.assert_awaited_once_with(db, "admin")
    get_user_by_email.assert_awaited_once_with(db, "admin@example.com")
    create_user.assert_awaited_once_with(
        db,
        username="admin",
        email="admin@example.com",
        password="admin123",
        role_name="admin",
        is_active=True,
    )
    assert user is created_user


@pytest.mark.asyncio
async def test_init_admin_user_rejects_existing_username(monkeypatch):
    init_roles = AsyncMock()
    get_user_by_username = AsyncMock(return_value=SimpleNamespace(username="admin"))
    get_user_by_email = AsyncMock()
    create_user = AsyncMock()

    monkeypatch.setattr("scripts.init_admin_user.init_roles", init_roles)
    monkeypatch.setattr(
        "scripts.init_admin_user.get_user_by_username",
        get_user_by_username,
    )
    monkeypatch.setattr("scripts.init_admin_user.get_user_by_email", get_user_by_email)
    monkeypatch.setattr("scripts.init_admin_user.create_user", create_user)

    with pytest.raises(AdminInitError, match="用户名已存在"):
        await init_admin_user(
            object(),
            username="admin",
            email="admin@example.com",
            password="admin123",
        )

    get_user_by_email.assert_not_awaited()
    create_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_init_admin_user_rejects_existing_email(monkeypatch):
    init_roles = AsyncMock()
    get_user_by_username = AsyncMock(return_value=None)
    get_user_by_email = AsyncMock(return_value=SimpleNamespace(email="admin@example.com"))
    create_user = AsyncMock()

    monkeypatch.setattr("scripts.init_admin_user.init_roles", init_roles)
    monkeypatch.setattr(
        "scripts.init_admin_user.get_user_by_username",
        get_user_by_username,
    )
    monkeypatch.setattr("scripts.init_admin_user.get_user_by_email", get_user_by_email)
    monkeypatch.setattr("scripts.init_admin_user.create_user", create_user)

    with pytest.raises(AdminInitError, match="邮箱已被注册"):
        await init_admin_user(
            object(),
            username="admin",
            email="admin@example.com",
            password="admin123",
        )

    create_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_init_admin_user_rejects_short_password(monkeypatch):
    init_roles = AsyncMock()
    get_user_by_username = AsyncMock()
    get_user_by_email = AsyncMock()
    create_user = AsyncMock()

    monkeypatch.setattr("scripts.init_admin_user.init_roles", init_roles)
    monkeypatch.setattr(
        "scripts.init_admin_user.get_user_by_username",
        get_user_by_username,
    )
    monkeypatch.setattr("scripts.init_admin_user.get_user_by_email", get_user_by_email)
    monkeypatch.setattr("scripts.init_admin_user.create_user", create_user)

    with pytest.raises(AdminInitError, match="密码长度不能少于6个字符"):
        await init_admin_user(
            object(),
            username="admin",
            email="admin@example.com",
            password="123",
        )

    init_roles.assert_not_awaited()
    get_user_by_username.assert_not_awaited()
    get_user_by_email.assert_not_awaited()
    create_user.assert_not_awaited()
