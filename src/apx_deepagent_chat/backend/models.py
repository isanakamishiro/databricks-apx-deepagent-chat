from typing import Literal

from pydantic import BaseModel

from .. import __version__


class VersionOut(BaseModel):
    version: str

    @classmethod
    def from_metadata(cls):
        return cls(version=__version__)


class ApproveDecision(BaseModel):
    type: Literal["approve", "reject"]
    message: str | None = None


class ChatApproveRequest(BaseModel):
    decisions: list[ApproveDecision]


class ChatApproveResponse(BaseModel):
    ok: bool
