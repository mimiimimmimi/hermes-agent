"""wetfish_baader_fps_capture — bundled opt-in Telegram capture plugin.

Hooks ``pre_gateway_dispatch`` and, for narrowly-gated Telegram chats,
parses Baader 192/212 readings out of free-form messages and forwards them
to the Wetfish FPS pi-server's ``/api/readings`` endpoint. Out-of-scope
messages and free-form chat in the same channel pass through untouched
(the hook returns ``None`` and the gateway continues to normal dispatch).

All the testable logic lives in :mod:`.capture`. This file is just the
glue: real HTTP via stdlib ``urllib`` and reply-sending that schedules
``adapter.send`` on the running event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from . import capture as _capture


logger = logging.getLogger(__name__)


# Stable, non-secret product-style User-Agent for outbound FPS API requests.
# Wetfish ops found that the FPS pi-server returns HTTP 403 to urllib's
# default (no User-Agent) but HTTP 200 with a normal product UA, so this is
# required for the plugin to function against live FPS.
USER_AGENT = "HermesWetfishBaaderFpsCapture/1.0"


def _http_request(
    url: str,
    *,
    method: str,
    headers: Dict[str, str],
    body: Optional[bytes],
    timeout: float,
) -> Tuple[int, Any]:
    """Perform an HTTP request. Returns (status, parsed-json-or-text).

    Wraps urllib so HTTPError (4xx/5xx) is returned as (status, body) rather
    than raised. Other network errors propagate as exceptions for the
    caller to catch and convert to a safe user-facing hint.
    """
    merged_headers = {"User-Agent": USER_AGENT, **headers}
    req = urllib.request.Request(
        url, data=body, headers=merged_headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read() if hasattr(exc, "read") else b""
        status = exc.code
    text = raw.decode("utf-8", errors="replace") if raw else ""
    try:
        return status, json.loads(text) if text else None
    except ValueError:
        return status, text


def _http_post(url: str, *, headers: Dict[str, str], json_body: Any, timeout: float):
    body = json.dumps(json_body).encode("utf-8")
    return _http_request(
        url, method="POST", headers=headers, body=body, timeout=timeout
    )


def _http_get(url: str, *, headers: Dict[str, str], timeout: float):
    return _http_request(
        url, method="GET", headers=headers, body=None, timeout=timeout
    )


def _make_reply(gateway: Any, event: Any):
    """Build the reply callable bound to this event's chat/thread.

    Replies are scheduled fire-and-forget on the running asyncio loop. If
    no loop is running (defensive — pre_gateway_dispatch always fires
    inside the gateway's loop in production), the reply is logged and
    dropped rather than blocking the hook.
    """
    source = getattr(event, "source", None)

    def _reply(text: str) -> None:
        if source is None:
            return
        adapter = None
        adapters = getattr(gateway, "adapters", None) or {}
        platform = getattr(source, "platform", None)
        if platform is not None:
            adapter = adapters.get(platform)
        if adapter is None:
            logger.debug(
                "wetfish_baader_fps_capture: no adapter for platform=%s; "
                "dropping reply",
                getattr(platform, "value", platform),
            )
            return
        send = getattr(adapter, "send", None)
        if send is None:
            return
        # Telegram threads: send back into the same forum topic.
        metadata = {}
        thread_id = getattr(source, "thread_id", None)
        if thread_id:
            metadata["message_thread_id"] = thread_id
        try:
            coro = send(
                source.chat_id,
                text,
                reply_to=getattr(source, "message_id", None) or getattr(event, "message_id", None),
                metadata=metadata or None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "wetfish_baader_fps_capture: adapter.send sync setup failed: %s",
                type(exc).__name__,
            )
            return
        if asyncio.iscoroutine(coro):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.debug(
                    "wetfish_baader_fps_capture: no running loop; "
                    "discarding reply"
                )
                coro.close()
                return
            loop.create_task(coro)

    return _reply


def _hook(event: Any = None, gateway: Any = None, session_store: Any = None, **_) -> Optional[Dict[str, Any]]:
    cfg = _capture.load_capture_config()
    if not cfg or not cfg.get("enabled"):
        return None
    try:
        return _capture.process_event(
            event,
            cfg=cfg,
            http_post=_http_post,
            http_get=_http_get,
            reply=_make_reply(gateway, event),
        )
    except Exception as exc:  # noqa: BLE001 — never let a plugin break dispatch
        logger.warning(
            "wetfish_baader_fps_capture hook raised: %s",
            type(exc).__name__,
        )
        return None


def register(ctx) -> None:
    ctx.register_hook("pre_gateway_dispatch", _hook)
