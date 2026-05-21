"""AIP 协议数据模型 — 对齐 AIP 智能体实现.pptx + acps-sdk"""
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional
from enum import Enum

BEIJING_TZ = timezone(timedelta(hours=8))


def now_iso() -> str:
    return datetime.now(BEIJING_TZ).isoformat()


class TaskState(str, Enum):
    Accepted = "accepted"
    Working = "working"
    AwaitingInput = "awaiting_input"
    AwaitingCompletion = "awaiting_completion"
    Completed = "completed"
    Failed = "failed"
    Rejected = "rejected"
    Canceled = "canceled"


class TaskCommandType(str, Enum):
    Start = "start"
    Get = "get"
    Continue = "continue"
    Cancel = "cancel"
    Complete = "complete"


@dataclass
class TextDataItem:
    text: str


@dataclass
class FileDataItem:
    uri: str = ""
    mimeType: str = ""
    bytes: str = ""


@dataclass
class TaskStatus:
    state: TaskState
    stateChangedAt: str = field(default_factory=now_iso)
    dataItems: list = field(default_factory=list)


@dataclass
class Product:
    id: str = ""
    dataItems: list = field(default_factory=list)


@dataclass
class TaskCommand:
    taskId: str = ""
    sessionId: str = ""
    command: TaskCommandType = TaskCommandType.Start
    dataItems: list = field(default_factory=list)


@dataclass
class TaskResult:
    id: str = ""
    sentAt: str = field(default_factory=now_iso)
    senderRole: str = "partner"
    senderId: str = ""
    taskId: str = ""
    sessionId: str = ""
    status: Optional[TaskStatus] = None
    products: list = field(default_factory=list)
    commandHistory: list = field(default_factory=list)
    statusHistory: list = field(default_factory=list)


@dataclass
class RpcRequest:
    jsonrpc: str = "2.0"
    id: str = ""
    method: str = "task/execute"
    params: Optional[dict] = None


@dataclass
class RpcResponse:
    jsonrpc: str = "2.0"
    id: str = ""
    result: Optional[dict] = None
    error: Optional[dict] = None
