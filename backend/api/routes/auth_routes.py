"""认证路由 — /register, /token, /login, /token/refresh。"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from api.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from api.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from db import authenticate_user, create_user, get_db

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    user = create_user(db, body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        )
    return UserResponse(id=user.id, username=user.username, role=user.role.value)


@router.post("/token", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    role = user.role.value if hasattr(user.role, "value") else user.role
    token_data = {"sub": str(user.id), "username": user.username, "role": role}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
        role=role,
    )


@router.post("/login", response_model=TokenResponse)
def login_json(body: LoginRequest, db: Session = Depends(get_db)):
    """JSON 格式登录接口，方便 API 客户端使用。"""
    user = authenticate_user(db, body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    role = user.role.value if hasattr(user.role, "value") else user.role
    token_data = {"sub": str(user.id), "username": user.username, "role": role}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
        role=role,
    )


@router.post("/token/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
        )
    user_id = int(payload["sub"])
    user_data = {"sub": str(user_id), "username": payload["username"], "role": payload["role"]}
    return TokenResponse(
        access_token=create_access_token(user_data),
        refresh_token=create_refresh_token(user_data),
        role=payload["role"],
    )
