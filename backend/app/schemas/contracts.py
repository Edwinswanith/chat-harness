from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


class Scope(BaseModel):
    user_id: str
    workspace_id: str


class FileScope(str, Enum):
    CURRENT_MESSAGE = "current_message"
    EXPLICIT_SELECTED = "explicit_selected"
    THREAD = "thread"


class MessageRequest(BaseModel):
    thread_id: str
    text: str = Field(min_length=1, max_length=16000)
    idempotency_key: str = Field(min_length=1, max_length=128)
    file_ids: list[str] = Field(default_factory=list, max_length=10)
    file_scope: FileScope = FileScope.CURRENT_MESSAGE


class UploadRequest(BaseModel):
    thread_id: str
    name: str = Field(min_length=1, max_length=120)
    content: str = Field(max_length=500000)


class SearchRequest(BaseModel):
    thread_id: str
    query: str = Field(min_length=1, max_length=16000)
    file_ids: list[str] = Field(default_factory=list, max_length=10)


class ToolResult(BaseModel):
    status: Literal["success", "error"]
    data: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    error: str | None = None
    retryable: bool = False


class Decision(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)
    kind: Literal["final", "tool", "subagent"]
    text: str = ""
    name: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)


class SubAgentResult(BaseModel):
    feedback: str
    status: Literal["success", "error"] = "success"


class ValidationResult(BaseModel):
    passed: bool
    retryable: bool = False
    errors: list[str] = Field(default_factory=list)
    feedback: str | None = None


class MemoryBundle(BaseModel):
    records_found: int = 0
    recent: list[dict] = Field(default_factory=list)
    summary: str = ""


class RagContext(BaseModel):
    chunks: list[dict] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)


class ModelContext(BaseModel):
    request: dict
    plan: str
    memory: MemoryBundle
    rag: RagContext
    tools: list[dict] = Field(default_factory=list)
    results: list[ToolResult] = Field(default_factory=list)
    feedback: list[str] = Field(default_factory=list)
