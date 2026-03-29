import csv
import re
from io import BytesIO, StringIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, File, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import verify_password, get_password_hash
from app.api.deps import get_current_user, require_role
from app.models.user import User, Role
from app.schemas.user import UserCreate, UserResponse, PasswordReset
from app.services.auth_service import invalidate_user_tokens, revoke_user_auth_sessions
from app.services.user_service import (
    create_user, update_password, get_user_by_username, get_user_by_email, get_user_by_id,
    soft_delete_user, restore_user, list_deleted_users,
)

router = APIRouter(prefix="/users", tags=["用户管理"])


class AdminResetPassword(BaseModel):
    new_password: str


class AdminUpdateUser(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    organization: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[str] = None


def _user_response(user: User) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "organization": user.organization,
        "role": user.role.name.value if user.role else "unknown",
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def _user_response_archive(user: User) -> dict:
    resp = _user_response(user)
    resp["is_deleted"] = user.is_deleted
    resp["deleted_at"] = user.deleted_at.isoformat() if user.deleted_at else None
    return resp


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    resp = {
        "id": str(current_user.id),
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "phone": current_user.phone,
        "organization": current_user.organization,
        "role": current_user.role.name.value,
        "is_active": current_user.is_active,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "show_on_leaderboard": current_user.show_on_leaderboard,
    }
    return resp


@router.post("/me/reset-password")
async def reset_password(
    body: PasswordReset,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码错误",
        )
    await update_password(db, current_user, body.new_password)
    invalidate_user_tokens(current_user)
    await revoke_user_auth_sessions(db, current_user.id)
    return {"code": 200, "message": "密码修改成功"}


# ---- Admin user management ----

@router.get("")
async def list_users(
    role: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    archive: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """List all users (admin only). Pass archive=true for deleted users."""
    if archive:
        users, total = await list_deleted_users(
            db, keyword=keyword, role=role, skip=skip, limit=limit,
        )
        return {
            "total": total,
            "items": [_user_response_archive(u) for u in users],
        }

    query = select(User).options(selectinload(User.role)).order_by(User.created_at.desc())
    count_q = select(func.count(User.id))

    # Exclude soft-deleted users in normal mode
    query = query.where(User.is_deleted == False)
    count_q = count_q.where(User.is_deleted == False)

    conditions = []
    if role:
        query = query.join(Role).where(Role.name == role)
        count_q = count_q.join(Role).where(Role.name == role)
    if is_active is not None:
        conditions.append(User.is_active == is_active)
    if keyword:
        conditions.append(
            User.username.ilike(f"%{keyword}%") | User.email.ilike(f"%{keyword}%") |
            User.full_name.ilike(f"%{keyword}%")
        )

    if conditions:
        for cond in conditions:
            query = query.where(cond)
            count_q = count_q.where(cond)

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.offset(skip).limit(limit))
    users = list(result.scalars().all())

    return {
        "total": total,
        "items": [_user_response(u) for u in users],
    }


@router.post("")
async def create_user_admin(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Create a new user (admin only)."""
    if await get_user_by_username(db, body.username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    if await get_user_by_email(db, body.email):
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    user = await create_user(
        db,
        username=body.username,
        email=body.email,
        password=body.password,
        role_name=body.role,
        full_name=body.full_name,
        phone=body.phone,
        organization=body.organization,
    )
    await db.commit()
    return _user_response(user)


_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')

# Column name mapping: Chinese → English
_COL_MAP = {
    '用户名': 'username', 'username': 'username',
    '邮箱': 'email', 'email': 'email',
}


def _parse_rows(file_data: bytes, filename: str) -> list[dict]:
    """Parse XLS or CSV file into list of {username, email} dicts."""
    ext = (filename.rsplit('.', 1)[-1] if '.' in filename else '').lower()

    if ext == 'xlsx':
        import openpyxl
        wb = openpyxl.load_workbook(BytesIO(file_data), read_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        header_raw = next(rows_iter, None)
        if not header_raw:
            return []
        header = [str(c).strip().lower() if c else '' for c in header_raw]
        data_rows = [[str(c).strip() if c else '' for c in row] for row in rows_iter]
        wb.close()
    elif ext == 'csv':
        text = file_data.decode('utf-8-sig')
        reader = csv.reader(StringIO(text))
        header_raw = next(reader, None)
        if not header_raw:
            return []
        header = [c.strip().lower() for c in header_raw]
        data_rows = [[c.strip() for c in row] for row in reader]
    else:
        raise ValueError(f"不支持的文件格式: .{ext}，请上传 .xlsx 或 .csv 文件")

    # Map column indices
    col_indices = {}
    for idx, h in enumerate(header):
        mapped = _COL_MAP.get(h)
        if mapped:
            col_indices[mapped] = idx

    if 'username' not in col_indices or 'email' not in col_indices:
        raise ValueError("文件缺少必需列：username（用户名）和 email（邮箱）")

    result = []
    for row in data_rows:
        username = row[col_indices['username']] if col_indices['username'] < len(row) else ''
        email = row[col_indices['email']] if col_indices['email'] < len(row) else ''
        if username or email:  # skip fully empty rows
            result.append({'username': username, 'email': email})
    return result


@router.post("/batch-import")
async def batch_import_users(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Batch import examinee users from XLS/CSV file (admin only).
    Required columns: username, email. Password defaults to 'abcdefg'."""
    file_data = await file.read()
    if not file_data:
        raise HTTPException(status_code=400, detail="文件为空")

    try:
        rows = _parse_rows(file_data, file.filename or 'unknown.csv')
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not rows:
        raise HTTPException(status_code=400, detail="文件中没有数据行")

    DEFAULT_PASSWORD = "abcdefg"
    successful = 0
    errors = []
    seen_usernames = set()
    seen_emails = set()

    for idx, row in enumerate(rows, start=2):  # row 2 = first data row (1 is header)
        username = row['username']
        email = row['email']

        # Validate username
        if not username:
            errors.append({"row": idx, "username": username, "email": email, "error": "用户名不能为空"})
            continue
        if username in seen_usernames:
            errors.append({"row": idx, "username": username, "email": email, "error": "文件中用户名重复"})
            continue

        # Validate email
        if not email:
            errors.append({"row": idx, "username": username, "email": email, "error": "邮箱不能为空"})
            continue
        if not _EMAIL_RE.match(email):
            errors.append({"row": idx, "username": username, "email": email, "error": "邮箱格式不正确"})
            continue
        if email.lower() in seen_emails:
            errors.append({"row": idx, "username": username, "email": email, "error": "文件中邮箱重复"})
            continue

        # Check database uniqueness
        if await get_user_by_username(db, username):
            errors.append({"row": idx, "username": username, "email": email, "error": "用户名已存在"})
            seen_usernames.add(username)
            continue
        if await get_user_by_email(db, email):
            errors.append({"row": idx, "username": username, "email": email, "error": "邮箱已被注册"})
            seen_emails.add(email.lower())
            continue

        # Create user
        try:
            await create_user(
                db,
                username=username,
                email=email,
                password=DEFAULT_PASSWORD,
                role_name="examinee",
            )
            successful += 1
            seen_usernames.add(username)
            seen_emails.add(email.lower())
        except Exception as e:
            errors.append({"row": idx, "username": username, "email": email, "error": str(e)})

    await db.commit()
    return {
        "successful": successful,
        "failed": len(errors),
        "errors": errors,
    }


@router.put("/{user_id}")
async def update_user(
    user_id: str,
    body: AdminUpdateUser,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Update user info (admin only)."""
    import uuid as _uuid
    user = await get_user_by_id(db, _uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if body.full_name is not None:
        user.full_name = body.full_name
    if body.phone is not None:
        user.phone = body.phone
    if body.organization is not None:
        user.organization = body.organization
    if body.is_active is not None:
        if body.is_active is False and user.id == current_user.id:
            raise HTTPException(status_code=400, detail="不能禁用自己的账号")
        if body.is_active is False:
            invalidate_user_tokens(user)
            await revoke_user_auth_sessions(db, user.id)
        user.is_active = body.is_active
    if body.role is not None:
        from app.services.user_service import get_or_create_role
        role = await get_or_create_role(db, body.role)
        user.role_id = role.id

    await db.commit()
    await db.refresh(user, ["role"])
    return _user_response(user)


@router.post("/{user_id}/reset-password")
async def admin_reset_password(
    user_id: str,
    body: AdminResetPassword,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Reset a user's password (admin only)."""
    import uuid as _uuid
    user = await get_user_by_id(db, _uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="密码长度不能少于6个字符")

    await update_password(db, user, body.new_password)
    invalidate_user_tokens(user)
    await revoke_user_auth_sessions(db, user.id)
    await db.commit()
    return {"message": "密码重置成功"}


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Soft-delete a user (admin only)."""
    import uuid as _uuid

    target = await get_user_by_id(db, _uuid.UUID(user_id))
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")
    if target.role and target.role.name.value == "admin":
        raise HTTPException(status_code=400, detail="不能删除管理员账号")

    invalidate_user_tokens(target)
    await revoke_user_auth_sessions(db, target.id)
    result = await soft_delete_user(db, _uuid.UUID(user_id))
    if not result:
        raise HTTPException(status_code=400, detail="删除失败，用户可能已被删除")

    await db.commit()
    return {"message": f"用户 {target.username} 已删除"}


@router.post("/{user_id}/restore")
async def restore_deleted_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Restore a soft-deleted user (admin only)."""
    import uuid as _uuid

    target = await get_user_by_id(db, _uuid.UUID(user_id))
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not target.is_deleted:
        raise HTTPException(status_code=400, detail="该用户未被删除，无需恢复")

    result = await restore_user(db, _uuid.UUID(user_id))
    if not result:
        raise HTTPException(status_code=400, detail="恢复失败")

    await db.commit()
    return {"message": f"用户 {target.username} 已恢复"}


@router.get("/{user_id}/scores")
async def get_user_scores(
    user_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    """Get a user's exam history and scores (admin only)."""
    import uuid as _uuid
    from app.models.answer import AnswerSheet
    from app.models.exam import Exam
    from app.models.score import Score

    uid = _uuid.UUID(user_id)
    user = await get_user_by_id(db, uid)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    result = await db.execute(
        select(AnswerSheet, Exam.title, Score)
        .join(Exam, AnswerSheet.exam_id == Exam.id)
        .outerjoin(Score, Score.answer_sheet_id == AnswerSheet.id)
        .where(AnswerSheet.user_id == uid)
        .order_by(AnswerSheet.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = result.all()

    count_result = await db.execute(
        select(func.count(AnswerSheet.id)).where(AnswerSheet.user_id == uid)
    )
    total = count_result.scalar() or 0

    items = []
    for sheet, exam_title, score in rows:
        items.append({
            "answer_sheet_id": str(sheet.id),
            "exam_id": str(sheet.exam_id),
            "exam_title": exam_title,
            "status": sheet.status.value if hasattr(sheet.status, 'value') else sheet.status,
            "start_time": sheet.start_time.isoformat() if sheet.start_time else None,
            "submit_time": sheet.submit_time.isoformat() if sheet.submit_time else None,
            "total_score": score.total_score if score else None,
            "max_score": score.max_score if score else None,
            "level": score.level if score else None,
            "scored_at": score.scored_at.isoformat() if score and score.scored_at else None,
        })

    return {"total": total, "items": items}


# Role-based dashboard placeholders
@router.get(
    "/admin/dashboard",
    dependencies=[Depends(require_role(["admin"]))],
)
async def admin_dashboard():
    return {"code": 200, "message": "Admin dashboard", "data": {}}


@router.get(
    "/organizer/stats",
    dependencies=[Depends(require_role(["admin", "organizer"]))],
)
async def organizer_stats():
    return {"code": 200, "message": "Organizer stats", "data": {}}


@router.get(
    "/reviewer/tasks",
    dependencies=[Depends(require_role(["admin", "reviewer"]))],
)
async def reviewer_tasks():
    return {"code": 200, "message": "Reviewer tasks", "data": {}}
