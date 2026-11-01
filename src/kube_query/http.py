"""Raw read-only HTTP access to the Kubernetes API server.

kube-query only ever issues GET requests. This module deliberately has no
support for other verbs: the read-only guarantee is enforced here.

Works with both the modern (>= 33) and legacy kubernetes client transports.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .errors import ApiException, KqApiError, KqError, api_error

DEFAULT_TIMEOUT = float(os.environ.get("KQ_TIMEOUT", "30"))


def raw_get(api_client: Any, path: str, params: dict | None = None) -> tuple[int, bytes]:
    """GET ``path?params``. Returns ``(status, body_bytes)``; raises on HTTP errors."""
    query = [(k, str(v)) for k, v in (params or {}).items() if v is not None and v != ""]
    try:
        if hasattr(api_client, "param_serialize"):
            # Modern transport (kubernetes >= 33).
            method, url, headers, body, post = api_client.param_serialize(
                "GET",
                path,
                query_params=query,
                header_params={"Accept": "application/json"},
                auth_settings=["BearerToken"],
            )
            _basic_auth_fallback(api_client, headers)
            resp = api_client.call_api(
                method,
                url,
                header_params=headers,
                body=body,
                post_params=post,
                _request_timeout=DEFAULT_TIMEOUT,
            )
            data = resp.read()
            status, reason = resp.status, resp.reason
        else:
            # Legacy transport (kubernetes < 33).
            resp = api_client.call_api(
                path,
                "GET",
                query_params=query,
                auth_settings=["BearerToken", "BasicAuth"],
                _preload_content=False,
                _return_http_data_only=True,
                _request_timeout=DEFAULT_TIMEOUT,
            )
            data = resp.data
            status, reason = resp.status, resp.reason
    except ApiException as e:
        raise api_error(e, f"GET {path}") from None
    except KqError:
        raise
    except Exception as e:  # connection refused, TLS errors, timeouts, ...
        raise KqError(
            f"request failed (GET {path}): {e}\n  Hint: check the context/cluster (kube-query ctx) and network reachability."
        ) from None
    if status >= 400:
        message = _status_message(data)
        raise KqApiError(status, message or reason or "request failed", action=f"GET {path}")
    return status, data


def get_json(api_client: Any, path: str, params: dict | None = None) -> Any:
    status, data = raw_get(api_client, path, params)
    try:
        return json.loads(data)
    except Exception:
        raise KqError(f"non-JSON response from {path} (HTTP {status})") from None


def get_text(api_client: Any, path: str, params: dict | None = None) -> str:
    _, data = raw_get(api_client, path, params)
    return data.decode("utf-8", "replace")


def _status_message(data: bytes) -> str:
    try:
        return str((json.loads(data) or {}).get("message", "") or "")
    except Exception:
        return ""


def _basic_auth_fallback(api_client: Any, headers: dict) -> None:
    """The modern transport only applies bearer auth; add basic auth if configured."""
    cfg = getattr(api_client, "configuration", None)
    if cfg is None:
        return
    if headers.get("authorization"):
        return
    if getattr(cfg, "username", None) or getattr(cfg, "password", None):
        token = cfg.get_basic_auth_token()
        if token:
            headers["authorization"] = token
