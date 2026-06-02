# API

## Purpose
FastAPI REST 接口层 — JWT 认证 + 巡检 + 对话 + 统计 + 健康检查。

## Requirements

### Requirement: JWT Authentication
API SHALL use JWT Bearer tokens for all protected endpoints, with 30-min access tokens and 7-day refresh tokens.

#### Scenario: Access without token
- **WHEN** client calls `/predict` without Authorization header
- **THEN** response SHALL be 401 Unauthorized

#### Scenario: Token refresh
- **WHEN** access token expires
- **THEN** client SHALL call `/token/refresh` with refresh token to get new access token

### Requirement: Dual Login Endpoints
API SHALL provide `/token` (OAuth2 form for Swagger UI) and `/login` (JSON for API clients).

### Requirement: Role-Based Access
API SHALL restrict `/admin/users` to admin role users.

#### Scenario: Regular user access admin endpoint
- **WHEN** user with role="user" calls `/admin/users`
- **THEN** response SHALL be 403 Forbidden

### Requirement: Thin Routing Layer
API layer SHALL only handle HTTP concerns (param parsing, auth, response formatting). Business logic SHALL be delegated to `llm/` or `services/`.

#### Scenario: Chat endpoint
- **WHEN** `/chat/send` is called
- **THEN** the endpoint SHALL decode images, validate permissions, then delegate to `llm/chat_core.run_chat()`

### Requirement: Chat Endpoints
API SHALL expose `/chat/send` (POST, text+optional image), `/chat/conversations` (GET list), `/chat/conversations/{id}` (GET detail), `/chat/conversations/{id}` (DELETE).

### Requirement: Health Check
API SHALL expose `/health` (GET, public) returning database connectivity, Ollama reachability, and model file presence.
