"""Initialize an admin user from the command line."""

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import async_session
from app.services.user_service import (
    create_user,
    get_user_by_email,
    get_user_by_username,
    init_roles,
)


class AdminInitError(Exception):
    """Raised when admin initialization preconditions are not met."""


async def init_admin_user(db, username: str, email: str, password: str):
    """Create an admin user if the username and email are both unused."""
    username = (username or "").strip()
    email = (email or "").strip()

    if not username:
        raise AdminInitError("用户名不能为空")
    if not email:
        raise AdminInitError("邮箱不能为空")
    if len(password or "") < 6:
        raise AdminInitError("密码长度不能少于6个字符")

    await init_roles(db)

    if await get_user_by_username(db, username):
        raise AdminInitError("用户名已存在")
    if await get_user_by_email(db, email):
        raise AdminInitError("邮箱已被注册")

    return await create_user(
        db,
        username=username,
        email=email,
        password=password,
        role_name="admin",
        is_active=True,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="初始化管理员用户")
    parser.add_argument("--username", required=True, help="管理员用户名")
    parser.add_argument("--email", required=True, help="管理员邮箱")
    parser.add_argument(
        "--password",
        help="管理员密码；不传时会在终端安全输入",
    )
    return parser.parse_args()


async def _run_cli(username: str, email: str, password: str | None) -> int:
    new_password = password or getpass.getpass("请输入管理员密码: ")
    if not password:
        confirm = getpass.getpass("请再次输入管理员密码: ")
        if new_password != confirm:
            print("两次输入的密码不一致", file=sys.stderr)
            return 1

    async with async_session() as db:
        try:
            await init_admin_user(
                db,
                username=username,
                email=email,
                password=new_password,
            )
            await db.commit()
        except AdminInitError as exc:
            await db.rollback()
            print(str(exc), file=sys.stderr)
            return 1
        except Exception:
            await db.rollback()
            raise

    print(f"管理员用户 {username} 已创建")
    return 0


def main() -> int:
    args = _parse_args()
    return asyncio.run(_run_cli(args.username, args.email, args.password))


if __name__ == "__main__":
    raise SystemExit(main())
