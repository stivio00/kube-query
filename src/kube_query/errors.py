"""User-facing errors. All are click exceptions: printed as ``Error: <msg>``, exit code 1."""

from __future__ import annotations

import json

import click

try:  # kubernetes >= 33 layout
    from kubernetes.client.exceptions import ApiException as ApiException
except ImportError:  # pragma: no cover - older clients
    from kubernetes.client.rest import ApiException as ApiException  # type: ignore[no-redef]


class KqError(click.ClickException):
    """A friendly, agent-actionable error message."""


class KqApiError(KqError):
    """An error response from the Kubernetes API server."""

    def __init__(self, status: int | str, message: str, *, action: str = "") -> None:
        self.status = status
        self.message = message
        prefix = f"API {status} error"
        if action:
            prefix += f" while {action}"
        super().__init__(f"{prefix}: {message}")


def api_error(e: Exception, action: str = "") -> KqApiError:
    """Convert a kubernetes client ApiException into a KqApiError."""
    status = getattr(e, "status", None) or "?"
    message = ""
    body = getattr(e, "body", None)
    if body:
        try:
            message = (json.loads(body) or {}).get("message") or str(body)[:500]
        except Exception:
            message = str(body)[:500]
    if not message:
        message = getattr(e, "reason", None) or str(e)
        if len(message) > 500:
            message = message[:500]
    return KqApiError(status, message, action=action)
