"""API 请求/响应 Pydantic 模型。

每个 API 端点对应一组 Schema，命名约定:
- *Request:  请求体
- *Response: 响应体
"""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """JSON 登录请求 (/login 端点)。与 OAuth2 form (/token 端点) 并列存在。"""
    username: str = Field(..., min_length=1, examples=["admin"])
    password: str = Field(..., min_length=1, examples=["ChangeMeStrongly123!"])


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=6)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: int
    username: str
    role: str


class DefectInfo(BaseModel):
    type: str
    area: float
    box: list
    image_id: int | None = None


class RecordResponse(BaseModel):
    id: int
    image_count: int
    material: str | None
    floor: str | None
    has_extension: str | None
    report: str | None
    defects: list[DefectInfo]
    created_at: str | None


class StatisticsResponse(BaseModel):
    summary: dict
    defect_distribution: list[dict]
    material_distribution: list[dict]
    daily_trend: list[dict]


class HealthResponse(BaseModel):
    status: str
    database: str
    ollama: str
    models: dict
