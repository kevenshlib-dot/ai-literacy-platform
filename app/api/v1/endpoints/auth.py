from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.schemas.user import UserCreate, UserLogin, TokenData, RegisterResponse, UserResponse
from app.services.auth_service import (
    create_auth_session,
    get_access_token_issue_time,
    get_auth_session_by_refresh_token,
    get_refresh_cookie_max_age,
    is_auth_session_usable,
    revoke_auth_session,
    rotate_auth_session,
)
from app.services.user_service import (
    authenticate_user,
    create_user,
    get_user_by_username,
    get_user_by_email,
)

router = APIRouter(prefix="/auth", tags=["认证"])

# Roles that require admin approval before activation
APPROVAL_REQUIRED_ROLES = {"organizer", "reviewer"}


def _build_user_response(user) -> UserResponse:
    return UserResponse(
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


def _set_refresh_cookie(response: Response, refresh_token: str, expires_at) -> None:
    response.set_cookie(
        key=settings.AUTH_REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
        max_age=get_refresh_cookie_max_age(expires_at),
        expires=expires_at,
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.AUTH_REFRESH_COOKIE_NAME,
        httponly=True,
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
        path="/",
    )


def _unauthorized_refresh_response(detail: str) -> JSONResponse:
    response = JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": detail},
    )
    _clear_refresh_cookie(response)
    return response


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: UserCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
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

    user_resp = _build_user_response(user)

    if needs_approval:
        return RegisterResponse(
            user=user_resp,
            needs_approval=True,
            message="注册成功，请等待管理员审批通知",
        )

    auth_session, refresh_token = await create_auth_session(db, user.id)
    token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.name.value},
        issued_at=get_access_token_issue_time(user),
    )
    _set_refresh_cookie(response, refresh_token, auth_session.expires_at)

    return RegisterResponse(
        access_token=token,
        user=user_resp,
        message="注册成功",
    )


@router.post("/login", response_model=TokenData)
async def login(
    body: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
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

    auth_session, refresh_token = await create_auth_session(db, user.id)
    token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.name.value},
        issued_at=get_access_token_issue_time(user),
    )
    _set_refresh_cookie(response, refresh_token, auth_session.expires_at)

    return TokenData(
        access_token=token,
        user=_build_user_response(user),
    )


@router.post("/refresh", response_model=TokenData)
async def refresh_access_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    refresh_token = request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    if not refresh_token:
        return _unauthorized_refresh_response("Refresh token missing")

    auth_session = await get_auth_session_by_refresh_token(db, refresh_token)
    if not auth_session:
        return _unauthorized_refresh_response("Refresh token invalid")
    if not is_auth_session_usable(auth_session):
        await revoke_auth_session(db, auth_session)
        return _unauthorized_refresh_response("Refresh token expired")

    user = auth_session.user
    if user is None:
        await revoke_auth_session(db, auth_session)
        return _unauthorized_refresh_response("User not found")
    if not user.is_active or getattr(user, "is_deleted", False):
        await revoke_auth_session(db, auth_session)
        return _unauthorized_refresh_response("User inactive")

    auth_session, rotated_refresh_token = await rotate_auth_session(db, auth_session)
    _set_refresh_cookie(response, rotated_refresh_token, auth_session.expires_at)

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.name.value},
        issued_at=get_access_token_issue_time(user),
    )
    return TokenData(
        access_token=access_token,
        user=_build_user_response(user),
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    refresh_token = request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    if refresh_token:
        auth_session = await get_auth_session_by_refresh_token(db, refresh_token)
        if auth_session:
            await revoke_auth_session(db, auth_session)

    _clear_refresh_cookie(response)
    return {"message": "退出登录成功"}
