"""F02 upload gateway and medical document routes."""

import hmac
from base64 import b64encode
from datetime import date, datetime
from typing import Annotated, Any, Literal, Protocol, cast
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from gutcare.auth.api import current_auth_context
from gutcare.auth.service import AuthContext
from gutcare.files.service import (
    ConfirmedMedicalFactData,
    DocumentPageData,
    DownloadGrantData,
    FileObjectData,
    FileService,
    MedicalDocumentData,
    UploadSessionData,
)
from gutcare.shared.errors import Problem

router = APIRouter(prefix="/api/v1")
gateway_router = APIRouter()
agent_router = APIRouter(prefix="/internal/v1/agent")


class FileServicePort(Protocol):
    def create_upload(
        self,
        context: AuthContext,
        *,
        purpose: str,
        file_name: str,
        content_type: str,
        size_bytes: int,
        idempotency_key: str,
    ) -> tuple[UploadSessionData, str]: ...

    def accept_upload(
        self, context: AuthContext, capability: str, content: bytes, content_type: str
    ) -> None: ...

    def complete_upload(self, context: AuthContext, upload_id: UUID) -> FileObjectData: ...

    def create_medical_document(
        self,
        context: AuthContext,
        *,
        file_object_id: UUID,
        document_type: str,
        hospital_name: str | None,
        document_date: date | None,
        notes: str | None,
        processing_mode: str,
    ) -> MedicalDocumentData: ...

    def list_medical_documents(
        self,
        context: AuthContext,
        *,
        limit: int = 20,
        cursor: str | None = None,
        document_type: str | None = None,
    ) -> DocumentPageData: ...

    def get_medical_document(
        self, context: AuthContext, document_id: UUID
    ) -> MedicalDocumentData: ...

    def patch_medical_document(
        self,
        context: AuthContext,
        document_id: UUID,
        *,
        record_version: int,
        changes: dict[str, Any],
    ) -> MedicalDocumentData: ...

    def delete_medical_document(self, context: AuthContext, document_id: UUID) -> None: ...

    def create_download_grant(self, context: AuthContext, file_id: UUID) -> DownloadGrantData: ...

    def create_record_image_download_grant(
        self, context: AuthContext, attachment_id: UUID
    ) -> DownloadGrantData: ...

    def download_by_capability(self, capability: str) -> tuple[bytes, str, str]: ...

    def list_medical_candidates(self, context: AuthContext, document_id: UUID) -> list[Any]: ...

    def list_confirmed_medical_facts(
        self, context: AuthContext
    ) -> list[ConfirmedMedicalFactData]: ...

    def decide_medical_candidate(
        self,
        context: AuthContext,
        candidate_id: UUID,
        *,
        decision: str,
        record_version: int,
        idempotency_key: str,
        value: Any = None,
    ) -> None: ...

    def list_medical_fact_conflicts(
        self, context: AuthContext, *, status: str = "open"
    ) -> list[dict[str, Any]]: ...
    def get_medical_fact_conflict(
        self, context: AuthContext, conflict_id: UUID
    ) -> dict[str, Any]: ...
    def resolve_medical_fact_conflict(
        self, context: AuthContext, conflict_id: UUID, *, record_version: int, idempotency_key: str
    ) -> dict[str, Any]: ...

    def submit_medical_candidates(
        self,
        request_id: UUID,
        callback_id: UUID,
        candidates: list[dict[str, Any]],
        *,
        parse_outcome: str | None = None,
        reason_code: str | None = None,
    ) -> None: ...

    def get_medical_parse_inputs(self, request_id: UUID) -> dict[str, Any]: ...

    def fail_medical_parse_request(
        self, request_id: UUID, callback_id: UUID, error_code: str
    ) -> None: ...

    def claim_medical_parse_request(self) -> UUID | None: ...


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: Literal["medical_document", "diet_image", "stool_image", "avatar"]
    file_name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(gt=0)


class UploadSessionResponse(BaseModel):
    upload_id: UUID
    upload_url: str
    expires_at: datetime
    form_fields: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, value: UploadSessionData) -> "UploadSessionResponse":
        return cls(
            upload_id=value.upload_id, upload_url=value.upload_url, expires_at=value.expires_at
        )


class FileObjectResponse(BaseModel):
    id: UUID
    storage_status: str
    content_type: str
    size_bytes: int

    @classmethod
    def from_domain(cls, value: FileObjectData) -> "FileObjectResponse":
        return cls(
            id=value.id,
            storage_status=value.storage_status,
            content_type=value.content_type,
            size_bytes=value.size_bytes,
        )


DocumentType = Literal[
    "outpatient_record",
    "discharge_summary",
    "diagnosis_certificate",
    "lab_report",
    "prescription",
    "other",
]


class MedicalDocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_object_id: UUID
    document_type: DocumentType
    hospital_name: str | None = Field(default=None, max_length=160)
    document_date: date | None = None
    notes: str | None = Field(default=None, max_length=1000)
    processing_mode: Literal["store_only", "analyze"]


class MedicalDocumentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_version: int = Field(ge=1)
    document_type: DocumentType = Field(default=cast(DocumentType, None))
    hospital_name: str | None = Field(default=None, max_length=160)
    document_date: date | None = None
    notes: str | None = Field(default=None, max_length=1000)


class MedicalDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    file_object_id: UUID
    document_type: str
    hospital_name: str | None
    document_date: date | None
    notes: str | None
    processing_mode: str
    parse_status: str
    parse_outcome: Literal["extracted", "no_supported_facts", "insufficient_quality"] | None
    parse_reason_code: str | None
    record_version: int
    created_at: datetime
    updated_at: datetime
    file_status: str
    original_name: str

    @classmethod
    def from_domain(cls, value: MedicalDocumentData) -> "MedicalDocumentResponse":
        return cls.model_validate(value)


class MedicalDocumentPageResponse(BaseModel):
    items: list[MedicalDocumentResponse]
    next_cursor: str | None

    @classmethod
    def from_domain(cls, value: DocumentPageData) -> "MedicalDocumentPageResponse":
        return cls(
            items=[MedicalDocumentResponse.from_domain(item) for item in value.items],
            next_cursor=value.next_cursor,
        )


class DownloadGrantResponse(BaseModel):
    download_url: str
    expires_at: datetime

    @classmethod
    def from_domain(cls, value: DownloadGrantData) -> "DownloadGrantResponse":
        return cls(download_url=value.download_url, expires_at=value.expires_at)


class CandidateDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["accept", "correct", "reject"]
    record_version: int = Field(ge=1)
    value: Any = None


class ConflictResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_version: int = Field(ge=1)


class MedicalFactConflictResponse(BaseModel):
    id: UUID
    status: Literal["open", "resolved", "invalidated"]
    record_version: int
    created_at: datetime
    resolution: Literal["keep_both"] | None = None
    members: list[dict[str, Any]] | None = None


class MedicalFactConflictResolutionResponse(BaseModel):
    id: UUID
    status: Literal["resolved"]
    record_version: int
    resolution: Literal["keep_both"]


class CandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    field_code: str
    value_type: str
    value: Any
    unit: str | None
    confidence: float | None
    uncertainty: str | None
    source_locator: dict[str, Any] | None
    excerpt: str | None
    review_status: str
    record_version: int
    chosen_value: Any


class ConfirmedMedicalFactResponse(BaseModel):
    """Patient-approved projection; deliberately excludes candidate evidence and model metadata."""

    model_config = ConfigDict(from_attributes=True)

    source_document_id: UUID
    field_code: str
    value_type: str
    value: Any
    unit: str | None
    confirmed_at: datetime


class AgentCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_code: str
    value_type: str
    value: Any
    unit: str | None
    confidence: float | None = Field(ge=0, le=1)
    uncertainty: str | None = Field(max_length=500)
    source_locator: dict[str, Any]
    excerpt: str = Field(min_length=1, max_length=500)


class AgentCandidateSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    callback_id: UUID
    parse_outcome: Literal["extracted", "no_supported_facts", "insufficient_quality"] | None = None
    reason_code: (
        Literal[
            "no_supported_fields",
            "unsupported_content",
            "low_quality_scan",
            "illegible_content",
            "incomplete_document",
        ]
        | None
    ) = None
    candidates: list[AgentCandidate] = Field(max_length=200)

    @model_validator(mode="after")
    def validate_parse_outcome(self) -> "AgentCandidateSubmission":
        outcome = self.parse_outcome or ("extracted" if self.candidates else None)
        if outcome == "extracted" and (not self.candidates or self.reason_code is not None):
            raise ValueError("extracted outcome requires candidates and no reason_code")
        if outcome == "no_supported_facts" and (
            self.candidates
            or self.reason_code not in {"no_supported_fields", "unsupported_content"}
        ):
            raise ValueError("no_supported_facts requires an empty candidate list and reason_code")
        if outcome == "insufficient_quality" and (
            self.candidates
            or self.reason_code
            not in {"low_quality_scan", "illegible_content", "incomplete_document"}
        ):
            raise ValueError(
                "insufficient_quality requires an empty candidate list and reason_code"
            )
        if outcome is None:
            raise ValueError("empty candidate list requires an explicit parse_outcome")
        return self


class AgentMedicalInputs(BaseModel):
    request_id: UUID
    document_id: UUID
    document_version: int
    document_type: str
    document_date: date | None
    content_type: str
    file_name: str
    content_base64: str


class AgentParseFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")
    callback_id: UUID
    error_code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_]+$")


def _require_agent(request: Request, authorization: str | None) -> None:
    secret = request.app.state.settings.agent_service_token
    if (
        not secret
        or not authorization
        or not authorization.startswith("Bearer ")
        or not hmac.compare_digest(authorization[7:], secret)
    ):
        raise Problem(401, "AUTHENTICATION_REQUIRED", "Service authentication required")


def get_file_service(request: Request) -> FileServicePort:
    service: FileService | None = request.app.state.file_service
    if service is None:
        raise Problem(503, "FILE_STORAGE_UNAVAILABLE", "File services are temporarily unavailable")
    return service


class AgentMedicalParseClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID | None


@agent_router.post(
    "/medical-parse-requests/claim",
    operation_id="claimMedicalParseRequest",
    response_model=AgentMedicalParseClaim,
)
def claim_medical_parse_request(
    request: Request,
    service: Annotated[FileServicePort, Depends(get_file_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> AgentMedicalParseClaim:
    _require_agent(request, authorization)
    return AgentMedicalParseClaim(request_id=service.claim_medical_parse_request())


@router.post(
    "/files/uploads",
    operation_id="createUpload",
    status_code=status.HTTP_201_CREATED,
    response_model=UploadSessionResponse,
    tags=["Records"],
)
def create_upload(
    body: UploadRequest,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[FileServicePort, Depends(get_file_service)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> UploadSessionResponse:
    data, _ = service.create_upload(
        context,
        purpose=body.purpose,
        file_name=body.file_name,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        idempotency_key=idempotency_key,
    )
    return UploadSessionResponse.from_domain(data)


@router.post(
    "/files/uploads/{upload_id}/complete",
    operation_id="completeUpload",
    response_model=FileObjectResponse,
    responses={503: {"description": "存储或恶意软件扫描服务暂不可用（RFC 9457）"}},
    tags=["Records"],
)
def complete_upload(
    upload_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[FileServicePort, Depends(get_file_service)],
) -> FileObjectResponse:
    return FileObjectResponse.from_domain(service.complete_upload(context, upload_id))


@router.post(
    "/medical-documents",
    operation_id="createMedicalDocument",
    status_code=status.HTTP_201_CREATED,
    response_model=MedicalDocumentResponse,
    tags=["Records"],
)
def create_medical_document(
    body: MedicalDocumentCreate,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[FileServicePort, Depends(get_file_service)],
) -> MedicalDocumentResponse:
    return MedicalDocumentResponse.from_domain(
        service.create_medical_document(context, **body.model_dump())
    )


@router.get(
    "/medical-documents",
    operation_id="listMedicalDocuments",
    response_model=MedicalDocumentPageResponse,
    tags=["Records"],
)
def list_medical_documents(
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[FileServicePort, Depends(get_file_service)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    document_type: DocumentType | None = None,
) -> MedicalDocumentPageResponse:
    return MedicalDocumentPageResponse.from_domain(
        service.list_medical_documents(
            context, limit=limit, cursor=cursor, document_type=document_type
        )
    )


@router.get(
    "/medical-documents/{document_id}",
    operation_id="getMedicalDocument",
    response_model=MedicalDocumentResponse,
    tags=["Records"],
)
def get_medical_document(
    document_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[FileServicePort, Depends(get_file_service)],
) -> MedicalDocumentResponse:
    return MedicalDocumentResponse.from_domain(service.get_medical_document(context, document_id))


@router.patch(
    "/medical-documents/{document_id}",
    operation_id="updateMedicalDocument",
    response_model=MedicalDocumentResponse,
    tags=["Records"],
)
def patch_medical_document(
    document_id: UUID,
    body: MedicalDocumentPatch,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[FileServicePort, Depends(get_file_service)],
) -> MedicalDocumentResponse:
    changes = body.model_dump(exclude={"record_version"}, exclude_unset=True)
    return MedicalDocumentResponse.from_domain(
        service.patch_medical_document(
            context, document_id, record_version=body.record_version, changes=changes
        )
    )


@router.delete(
    "/medical-documents/{document_id}",
    operation_id="deleteMedicalDocument",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    tags=["Records"],
)
def delete_medical_document(
    document_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[FileServicePort, Depends(get_file_service)],
) -> Response:
    service.delete_medical_document(context, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/files/{file_id}/download-grants",
    operation_id="createFileDownloadGrant",
    response_model=DownloadGrantResponse,
    tags=["Records"],
)
def create_download_grant(
    file_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[FileServicePort, Depends(get_file_service)],
) -> DownloadGrantResponse:
    return DownloadGrantResponse.from_domain(service.create_download_grant(context, file_id))


@router.post(
    "/record-images/{attachment_id}/download-grants",
    operation_id="createRecordImageDownloadGrant",
    response_model=DownloadGrantResponse,
    tags=["Records"],
)
def create_record_image_download_grant(
    attachment_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[FileServicePort, Depends(get_file_service)],
) -> DownloadGrantResponse:
    return DownloadGrantResponse.from_domain(
        service.create_record_image_download_grant(context, attachment_id)
    )


@router.get(
    "/medical-documents/{document_id}/candidates",
    response_model=list[CandidateResponse],
    operation_id="listMedicalDocumentCandidates",
    tags=["Records"],
)
def list_medical_candidates(
    document_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[FileServicePort, Depends(get_file_service)],
) -> list[CandidateResponse]:
    return [
        CandidateResponse.model_validate(item)
        for item in service.list_medical_candidates(context, document_id)
    ]


@router.get(
    "/patients/me/confirmed-medical-facts",
    response_model=list[ConfirmedMedicalFactResponse],
    operation_id="listMyConfirmedMedicalFacts",
    tags=["Records"],
)
def list_my_confirmed_medical_facts(
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[FileServicePort, Depends(get_file_service)],
) -> list[ConfirmedMedicalFactResponse]:
    return [
        ConfirmedMedicalFactResponse.model_validate(item)
        for item in service.list_confirmed_medical_facts(context)
    ]


@router.get(
    "/medical-fact-conflicts",
    response_model=list[MedicalFactConflictResponse],
    operation_id="listMedicalFactConflicts",
    tags=["Records"],
)
def list_medical_fact_conflicts(
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[FileServicePort, Depends(get_file_service)],
    status_filter: Annotated[
        str, Query(alias="status", pattern="^(open|resolved|invalidated|all)$")
    ] = "open",
) -> list[MedicalFactConflictResponse]:
    return [
        MedicalFactConflictResponse.model_validate(item)
        for item in service.list_medical_fact_conflicts(context, status=status_filter)
    ]


@router.get(
    "/medical-fact-conflicts/{conflict_id}",
    response_model=MedicalFactConflictResponse,
    operation_id="getMedicalFactConflict",
    tags=["Records"],
)
def get_medical_fact_conflict(
    conflict_id: UUID,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[FileServicePort, Depends(get_file_service)],
) -> MedicalFactConflictResponse:
    return MedicalFactConflictResponse.model_validate(
        service.get_medical_fact_conflict(context, conflict_id)
    )


@router.post(
    "/medical-fact-conflicts/{conflict_id}/resolve",
    response_model=MedicalFactConflictResolutionResponse,
    operation_id="resolveMedicalFactConflict",
    tags=["Records"],
)
def resolve_medical_fact_conflict(
    conflict_id: UUID,
    body: ConflictResolutionRequest,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[FileServicePort, Depends(get_file_service)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> MedicalFactConflictResolutionResponse:
    return MedicalFactConflictResolutionResponse.model_validate(
        service.resolve_medical_fact_conflict(
            context,
            conflict_id,
            record_version=body.record_version,
            idempotency_key=idempotency_key,
        )
    )


@router.post(
    "/medical-field-candidates/{candidate_id}/decision",
    status_code=204,
    operation_id="decideMedicalFieldCandidate",
    tags=["Records"],
)
def decide_medical_candidate(
    candidate_id: UUID,
    body: CandidateDecisionRequest,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[FileServicePort, Depends(get_file_service)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
) -> Response:
    service.decide_medical_candidate(
        context,
        candidate_id,
        decision=body.decision,
        record_version=body.record_version,
        idempotency_key=idempotency_key,
        value=body.value,
    )
    return Response(status_code=204)


@agent_router.post(
    "/medical-parse-requests/{request_id}/candidates",
    status_code=204,
    operation_id="submitMedicalFieldCandidates",
)
def submit_medical_candidates(
    request_id: UUID,
    body: AgentCandidateSubmission,
    request: Request,
    service: Annotated[FileServicePort, Depends(get_file_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    _require_agent(request, authorization)
    service.submit_medical_candidates(
        request_id,
        body.callback_id,
        [item.model_dump() for item in body.candidates],
        parse_outcome=body.parse_outcome or "extracted",
        reason_code=body.reason_code,
    )
    return Response(status_code=204)


@agent_router.get("/medical-parse-requests/{request_id}/inputs", response_model=AgentMedicalInputs)
def get_medical_parse_inputs(
    request_id: UUID,
    request: Request,
    service: Annotated[FileServicePort, Depends(get_file_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> AgentMedicalInputs:
    _require_agent(request, authorization)
    data = service.get_medical_parse_inputs(request_id)
    return AgentMedicalInputs(
        request_id=data["request_id"],
        document_id=data["document_id"],
        document_version=data["document_version"],
        document_type=data["document_type"],
        document_date=data["document_date"],
        content_type=data["content_type"],
        file_name=data["file_name"],
        content_base64=b64encode(data["content"]).decode("ascii"),
    )


@agent_router.post(
    "/medical-parse-requests/{request_id}/fail",
    status_code=204,
    operation_id="failMedicalParseRequest",
)
def fail_medical_parse_request(
    request_id: UUID,
    body: AgentParseFailure,
    request: Request,
    service: Annotated[FileServicePort, Depends(get_file_service)],
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    _require_agent(request, authorization)
    service.fail_medical_parse_request(request_id, body.callback_id, body.error_code)
    return Response(status_code=204)


@gateway_router.put(
    "/uploads/{capability}",
    operation_id="uploadThroughGateway",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def upload_through_gateway(
    capability: str,
    request: Request,
    context: Annotated[AuthContext, Depends(current_auth_context)],
    service: Annotated[FileServicePort, Depends(get_file_service)],
) -> Response:
    length_header = request.headers.get("content-length")
    if length_header is not None:
        try:
            if int(length_header) > 20 * 1024 * 1024:
                raise Problem(413, "FILE_SIZE_LIMIT_EXCEEDED", "File size limit exceeded")
        except ValueError as exc:
            raise Problem(400, "INVALID_CONTENT_LENGTH", "Invalid Content-Length") from exc
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
        if len(chunks) > 20 * 1024 * 1024:
            raise Problem(413, "FILE_SIZE_LIMIT_EXCEEDED", "File size limit exceeded")
    service.accept_upload(
        context,
        capability,
        bytes(chunks),
        request.headers.get("content-type", ""),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@gateway_router.get("/uploads/{capability}", operation_id="downloadThroughGateway")
def download_through_gateway(
    capability: str,
    service: Annotated[FileServicePort, Depends(get_file_service)],
) -> StreamingResponse:
    content, content_type, original_name = service.download_by_capability(capability)
    disposition = (
        f"attachment; filename=\"download\"; filename*=UTF-8''{quote(original_name, safe='')}"
    )
    return StreamingResponse(
        iter((content,)),
        media_type=content_type,
        headers={"Content-Disposition": disposition, "Cache-Control": "private, no-store"},
    )
