"""Platform adapter contract.

Every platform — LinkedIn, X, Facebook, or one added later — is a class that
satisfies the `PlatformAdapter` protocol. The publisher and scheduler only ever
talk to this interface, so adding a platform is a single new file plus its name
in `ENABLED_PLATFORMS`. Nothing in the dispatch logic changes.

`PostError` is the one exception adapters may raise to signal a failed post; the
publisher catches it and records a FAILED PostResult rather than aborting the
whole campaign.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class PostError(Exception):
    """Raised by an adapter when a post could not be published."""


@dataclass(frozen=True)
class DraftPost:
    """The platform-agnostic content handed to every adapter."""

    title: str
    content: str
    media_url: str | None = None


@dataclass(frozen=True)
class PostReceipt:
    """A successful publish — the platform's id for the created post."""

    platform_post_id: str


@runtime_checkable
class PlatformAdapter(Protocol):
    name: str

    def validate_credentials(self) -> bool:
        """Return True when the adapter has everything it needs to publish."""
        ...

    def post(self, draft: DraftPost, attempt: int = 1) -> PostReceipt:
        """Publish `draft`. Returns a receipt, or raises PostError on failure.

        `attempt` is 1 on the first publish and increments on each retry; real
        adapters can ignore it (it is used by the demo adapter to simulate a
        transient outage that clears on retry)."""
        ...
