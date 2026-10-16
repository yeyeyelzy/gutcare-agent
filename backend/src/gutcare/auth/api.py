"""HTTP routes and DTOs for the frozen email account contract."""

from datetime import datetime
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from gutcare.auth.service import (
    AuthContext,
    ConsentDecisionData,
    ConsentType,
    PatientProfileData,
    TokenPair,
)
from gutcare.shared.errors import Problem

router = APIRouter(prefix="/api/v1")
bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")


class AuthServicePort(Protocol):
    def register(
        self,
        email_value: str,
        password: str,
        birth_year: int,
        privacy_policy_version: str,
        health_data_processing_consent: bool,
        health_data_processing_policy_version: str,
        source: str,
    ) -> UUID: ...

    def verify_email(self, raw_token: str, source: str) -> None: ...

    def login(self, email_value: str, password: str, source: str) -> TokenPair: ...

    def refresh(self, raw_refresh: str) -> TokenPair: ...

    def request_password_reset(self, email_value: str, source: str) -> UUID: ...

    def confirm_password_reset(self, raw_token: str, new_password: str, source: str) -> None: ...

    def authenticate_access_token(self, raw_access: str) -> AuthContext: ...

    def logout(self, context: AuthContext) -> None: ...

    def get_my_profile(self, context: AuthContext) -> PatientProfileData: ...

    def patch_my_profile(
        self,
        context: AuthContext,
        profile_version: int,
        changes: dict[str, str | int | None],
    ) -> PatientProfileData: ...

    def record_consent(
        self,
        context: AuthContext,
        consent_type: ConsentType,
        policy_version: str,
        granted: bool,
    ) -> ConsentDecisionData: ...

    def request_account_deletion(self, context: AuthContext) -> UUID: ...


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=12, max_length=128)
    birth_year: int = Field(ge=1900, le=2100)
    privacy_policy_version: str = Field(min_length=1, max_length=32)
    health_data_processing_consent: Literal[True]
    health_data_processing_policy_version: str = Field(min_length=1, max_length=32)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20)


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=1)


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20)
    new_password: str = Field(min_length=12, max_length=128)


class PatientProfileResponse(BaseModel):
    id: UUID
    nickname: str | None
    birth_year: int
    timezone: str
    profile_version: int

    @classmethod
    def from_domain(cls, value: PatientProfileData) -> "PatientProfileResponse":
        return cls(
            id=value.id,
            nickname=value.nickname,
            birth_year=value.birth_year,
            timezone=value.timezone,
            profile_version=value.profile_version,
        )


class PatientProfilePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", title="PatientProfilePatch")

    nickname: str | None = Field(default=None, max_length=64)
    birth_year: int = Field(default=None, ge=1900, le=2100)  # type: ignore[assignment]
    timezone: str = Field(default=None, min_length=1, max_length=64)  # type: ignore[assignment]
    profile_version: int = Field(ge=1)


class ConsentDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", title="ConsentDecision")

    consent_type: Literal[
        "health_data_processing",
        "mood_data_processing",
        "mood_ai_sharing",
        "sensitive_image",
        "third_party_ai",
        "push_notification",
    ]
    policy_version: str = Field(min_length=1, max_length=32)
    granted: bool


class ConsentDecisionResponse(BaseModel):
    consent_type: ConsentType
    policy_version: str
    granted: bool
    decided_at: datetime

    @classmethod
    def from_domain(cls, value: ConsentDecisionData) -> "ConsentDecisionResponse":
        return cls(
            consent_type=value.consent_type,
            policy_version=value.policy_version,
            granted=value.granted,
            decided_at=value.decided_at,
        )


class AcceptedOperation(BaseModel):
    operation_id: UUID
    status: str = "accepted"


class ProblemResponse(BaseModel):
    type: str
    title: str
    status: int
    code: str
    request_id: UUID
    detail: str | None = None
    instance: str | None = None
    errors: list[dict[str, Any]] | None = None


def problem_response(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/problem+json": {"schema": ProblemResponse.model_json_schema()}},
    }


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 900

    @classmethod
    def from_domain(cls, value: TokenPair) -> "TokenPairResponse":
        return cls(
            access_token=value.access_token,
            refresh_token=value.refresh_token,
            token_type=value.token_type,
            expires_in=value.expires_in,
        )


def get_auth_service(request: Request) -> AuthServicePort:
    service: AuthServicePort | None = request.app.state.auth_service
    if service is None:
        raise Problem(500, "INTERNAL_ERROR", "Service temporarily unavailable")
    return service


def request_source(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def current_auth_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    service: Annotated[AuthServicePort, Depends(get_auth_service)],
) -> AuthContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise Problem(401, "AUTHENTICATION_REQUIRED", "Authentication required")
    return service.authenticate_access_token(credentials.credentials)


@router.post(
    "/auth/register",
    operation_id="register",
    summary="注册邮箱账户",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AcceptedOperation,
    responses={
        422: problem_response("请求字段无效"),
        429: problem_response("请求频率受限"),
        500: problem_response("内部错误"),
    },
    tags=["Auth"],
)
def register(
    body: RegisterRequest,
    request: Request,
    service: Annotated[AuthServicePort, Depends(get_auth_service)],
) -> AcceptedOperation:
    operation_id = service.register(
        str(body.email),
        body.password,
        body.birth_year,
        body.privacy_policy_version,
        body.health_data_processing_consent,
        body.health_data_processing_policy_version,
        request_source(request),
    )
    return AcceptedOperation(operation_id=operation_id)


@router.post(
    "/auth/email/verify",
    operation_id="verifyEmail",
    summary="验证注册邮箱",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={
        422: problem_response("验证令牌无效"),
        429: problem_response("请求频率受限"),
        500: problem_response("内部错误"),
    },
    tags=["Auth"],
)
def verify_email(
    body: VerifyEmailRequest,
    request: Request,
    service: Annotated[AuthServicePort, Depends(get_auth_service)],
) -> None:
    service.verify_email(body.token, request_source(request))


@router.post(
    "/auth/login",
    operation_id="login",
    summary="邮箱密码登录",
    response_model=TokenPairResponse,
    responses={
        401: problem_response("邮箱或密码无效"),
        429: problem_response("请求频率受限或账户短时锁定"),
        500: problem_response("内部错误"),
    },
    tags=["Auth"],
)
def login(
    body: LoginRequest,
    request: Request,
    service: Annotated[AuthServicePort, Depends(get_auth_service)],
) -> TokenPairResponse:
    return TokenPairResponse.from_domain(
        service.login(str(body.email), body.password, request_source(request))
    )


@router.post(
    "/auth/refresh",
    operation_id="refreshSession",
    summary="轮换刷新令牌",
    response_model=TokenPairResponse,
    responses={
        401: problem_response("刷新令牌无效、过期或已撤销"),
        500: problem_response("内部错误"),
    },
    tags=["Auth"],
)
def refresh(
    body: RefreshRequest,
    service: Annotated[AuthServicePort, Depends(get_auth_service)],
) -> TokenPairResponse:
    return TokenPairResponse.from_domain(service.refresh(body.refresh_token))


@router.post(
    "/auth/password/reset/request",
    operation_id="requestPasswordReset",
    summary="请求密码重置邮件",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AcceptedOperation,
    responses={
        422: problem_response("请求字段无效"),
        429: problem_response("请求频率受限"),
        500: problem_response("内部错误"),
    },
    tags=["Auth"],
)
def request_password_reset(
    body: PasswordResetRequest,
    request: Request,
    service: Annotated[AuthServicePort, Depends(get_auth_service)],
) -> AcceptedOperation:
    return AcceptedOperation(
        operation_id=service.request_password_reset(str(body.email), request_source(request))
    )


@router.post(
    "/auth/password/reset/confirm",
    operation_id="confirmPasswordReset",
    summary="使用单次令牌重置密码",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={
        422: problem_response("重置令牌无效或密码不符合要求"),
        429: problem_response("请求频率受限"),
        500: problem_response("内部错误"),
    },
    tags=["Auth"],
)
def confirm_password_reset(
    body: PasswordResetConfirmRequest,
    request: Request,
    service: Annotated[AuthServicePort, Depends(get_auth_service)],
) -> None:
    service.confirm_password_reset(body.token, body.new_password, request_source(request))


@router.post(
    "/auth/logout",
    operation_id="logout",
    summary="退出当前会话",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    responses={
        401: problem_response("访问令牌缺失、无效、过期或已撤销"),
        500: problem_response("内部错误"),
    },
    tags=["Auth"],
)
def logout(
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[AuthServicePort, Depends(get_auth_service)],
) -> None:
    service.logout(context)


@router.get(
    "/patients/me",
    operation_id="getMyProfile",
    summary="获取当前患者资料",
    response_model=PatientProfileResponse,
    responses={
        401: problem_response("访问令牌缺失、无效、过期或已撤销"),
        404: problem_response("患者资料不存在"),
        500: problem_response("内部错误"),
    },
    tags=["Profile"],
)
def get_my_profile(
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[AuthServicePort, Depends(get_auth_service)],
) -> PatientProfileResponse:
    return PatientProfileResponse.from_domain(service.get_my_profile(context))


@router.patch(
    "/patients/me",
    operation_id="updateMyProfile",
    summary="更新当前患者资料",
    response_model=PatientProfileResponse,
    responses={
        401: problem_response("访问令牌缺失、无效、过期或已撤销"),
        404: problem_response("患者资料不存在"),
        409: problem_response("资料版本冲突"),
        422: problem_response("请求字段无效"),
        500: problem_response("内部错误"),
    },
    tags=["Profile"],
)
def patch_my_profile(
    body: PatientProfilePatchRequest,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[AuthServicePort, Depends(get_auth_service)],
) -> PatientProfileResponse:
    changes = body.model_dump(exclude={"profile_version"}, exclude_unset=True)
    return PatientProfileResponse.from_domain(
        service.patch_my_profile(context, body.profile_version, changes)
    )


@router.post(
    "/patients/me/consents",
    operation_id="recordConsent",
    summary="记录或撤回授权",
    status_code=status.HTTP_201_CREATED,
    response_model=ConsentDecisionResponse,
    responses={
        401: problem_response("访问令牌缺失、无效、过期或已撤销"),
        404: problem_response("患者资料不存在"),
        422: problem_response("请求字段无效"),
        500: problem_response("内部错误"),
    },
    tags=["Privacy"],
)
def record_consent(
    body: ConsentDecisionRequest,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[AuthServicePort, Depends(get_auth_service)],
) -> ConsentDecisionResponse:
    return ConsentDecisionResponse.from_domain(
        service.record_consent(
            context,
            body.consent_type,
            body.policy_version,
            body.granted,
        )
    )
