from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token
from app.schemas.user import UserCreate, UserLogin, TokenData, RegisterResponse, UserResponse
from app.services.user_service import (
    authenticate_user,
    create_user,
    get_user_by_username,
    get_user_by_email,
)

router = APIRouter(prefix="/auth", tags=["认证"])

# Roles that require admin approval before activation
APPROVAL_REQUIRED_ROLES = {"organizer", "reviewer"}


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(body: UserCreate, db: AsyncSession = Depends(get_db)):
    # Disallow registering as admin
    if body.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不允许注册管理员角色",
        )

    if await get_user_by_username(db, body.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )
    if await get_user_by_email(db, body.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已被注册",
        )

    needs_approval = body.role in APPROVAL_REQUIRED_ROLES

    user = await create_user(
        db,
        username=body.username,
        email=body.email,
        password=body.password,
        role_name=body.role,
        full_name=body.full_name,
        phone=body.phone,
        organization=body.organization,
        is_active=not needs_approval,
    )

    await db.commit()

    user_resp = UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        organization=user.organization,
        role=user.role.name.value,
        is_active=user.is_active,
        created_at=user.created_at,
    )

    if needs_approval:
        return RegisterResponse(
            user=user_resp,
            needs_approval=True,
            message="注册成功，请等待管理员审批通知",
        )

    token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.name.value},
    )

    return RegisterResponse(
        access_token=token,
        user=user_resp,
        message="注册成功",
    )


@router.post("/login", response_model=TokenData)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号待审批，请等待管理员通知",
        )

    token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.name.value},
    )

    return TokenData(
        access_token=token,
        user=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            phone=user.phone,
            organization=user.organization,
            role=user.role.name.value,
            is_active=user.is_active,
            created_at=user.created_at,
        ),
    )
