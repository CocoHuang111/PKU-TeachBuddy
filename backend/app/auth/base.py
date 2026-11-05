"""认证提供者接口。具体协议实现隔离在各 provider 模块。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class AuthIdentityInfo:
    provider: str
    subject: str
    school: str = ""
    username: str | None = None
    display_name: str = ""
    provider_data: dict[str, Any] = field(default_factory=dict)


class AuthProvider(Protocol):
    name: str

    async def authenticate(self, **credentials: Any) -> AuthIdentityInfo: ...

    async def get_identity(self, subject: str) -> AuthIdentityInfo: ...
