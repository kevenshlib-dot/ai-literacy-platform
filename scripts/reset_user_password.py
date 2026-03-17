"""Reset a user's password from the command line."""

import argparse
import asyncio
import getpass
import sys

from app.core.database import async_session
from app.services.user_service import get_user_by_username, update_password


class PasswordResetError(Exception):
    """Raised when password reset preconditions are not met."""


async def reset_password_by_username(db, username: str, new_password: str) -> None:
    """Reset a user's password by username."""
    username = (username or "").strip()
    if not username:
        raise PasswordResetError("用户名不能为空")

    if len(new_password or "") < 6:
        raise PasswordResetError("密码长度不能少于6个字符")

    user = await get_user_by_username(db, username)
    if not user:
        raise PasswordResetError("用户不存在")

    await update_password(db, user, new_password)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="重置指定用户名的密码")
    parser.add_argument("--username", required=True, help="需要重置密码的用户名")
    parser.add_argument(
        "--password",
        help="新密码；不传时会在终端安全输入",
    )
    return parser.parse_args()


async def _run_cli(username: str, password: str | None) -> int:
    new_password = password or getpass.getpass("请输入新密码: ")
    if not password:
        confirm = getpass.getpass("请再次输入新密码: ")
        if new_password != confirm:
            print("两次输入的密码不一致", file=sys.stderr)
            return 1

    async with async_session() as db:
        try:
            await reset_password_by_username(db, username, new_password)
            await db.commit()
        except PasswordResetError as exc:
            await db.rollback()
            print(str(exc), file=sys.stderr)
            return 1
        except Exception:
            await db.rollback()
            raise

    print(f"用户 {username} 的密码已重置")
    return 0


def main() -> int:
    args = _parse_args()
    return asyncio.run(_run_cli(args.username, args.password))


if __name__ == "__main__":
    raise SystemExit(main())
