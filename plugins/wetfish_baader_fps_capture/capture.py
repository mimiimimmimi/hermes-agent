"""Pure logic for the wetfish_baader_fps_capture plugin.

This module is split out from ``__init__.py`` so it can be unit-tested
without importing the whole hermes plugin runtime. Three layers:

  * ``parse_message`` — tolerant text-to-readings parser.
  * ``match_event``  — config gating (platform / chat_id / thread_id /
                       sender_id / enabled).
  * ``process_event`` — orchestrator. Injects HTTP + reply callables so
                       tests can exercise the full path without network.

The plugin shell in ``__init__.py`` wires real HTTP + a real reply that
schedules ``adapter.send`` on the running event loop.

Secret handling note: the FPS pin is read from an env var (whose *name*
is configured, not the value). It is only placed into the outbound HTTP
header — never into log lines, reply text, or recorded exception messages.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


SUPPORTED_BAADER_IDS = ("192", "212")

# Label aliases. All matching is case-insensitive on lowercased tokens.
_FISH_LABELS = {"fish/min", "fpm", "fish"}
_CUPS_LABELS = {"cups/min", "cpm", "cups"}
_AVG_LABELS = {"avg", "average", "weight", "kg"}
_NOTE_LABELS = {"issue", "comment", "note", "notes"}

# Tokenizer: split on whitespace. Keep "fish/min", "cups/min" as single
# tokens (slashes already preserved). Strip trailing punctuation.
_TOKEN_RE = re.compile(r"[\s,]+")
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


@dataclass
class ParseResult:
    readings: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _classify_label(token: str) -> Optional[str]:
    """Return the canonical field name for a label token, or None."""
    t = token.lower().rstrip(":")
    if t in _FISH_LABELS:
        return "fishPerMin"
    if t in _CUPS_LABELS:
        return "cupsPerMin"
    if t in _AVG_LABELS:
        return "avgWeightKg"
    if t in _NOTE_LABELS:
        return "_note"
    return None


def _coerce_number(token: str) -> Optional[float]:
    if not _NUMBER_RE.match(token):
        return None
    try:
        val = float(token)
    except ValueError:
        return None
    if val.is_integer():
        return int(val)
    return val


def _parse_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse a single Baader line.

    Returns either a fully populated reading dict, a dict with a
    ``"_missing"`` key listing field names that were absent, or a dict
    with an ``"_ambiguous"`` key listing field names that were specified
    more than once on the same line (e.g. ``fish 82 fish 99`` or
    ``fish 82 fpm 83``). Returns ``None`` if the line is not a Baader
    reading at all (e.g. doesn't start with a supported id).
    """
    stripped = line.strip()
    if not stripped:
        return None

    tokens = [t for t in _TOKEN_RE.split(stripped) if t]
    if not tokens:
        return None

    head = tokens[0].rstrip(":,.")
    if head not in SUPPORTED_BAADER_IDS:
        return None

    reading: Dict[str, Any] = {"baaderId": head}
    note_parts: List[str] = []
    in_note = False
    ambiguous: List[str] = []

    def _assign(field_name: str, value: Any) -> None:
        if field_name in reading:
            if field_name not in ambiguous:
                ambiguous.append(field_name)
            return
        reading[field_name] = value

    # Scan token pairs. We accept both "label number" and "number label"
    # ordering. Note labels consume the rest of the line.
    i = 1
    while i < len(tokens):
        tok = tokens[i].rstrip(":,.")
        if in_note:
            note_parts.append(tokens[i])
            i += 1
            continue

        field_name = _classify_label(tok)
        if field_name == "_note":
            in_note = True
            i += 1
            continue
        if field_name is not None:
            # label-first: peek next token for a number
            if i + 1 < len(tokens):
                num = _coerce_number(tokens[i + 1].rstrip(":,."))
                if num is not None:
                    _assign(field_name, num)
                    i += 2
                    continue
            i += 1
            continue

        # token is not a label: maybe number-then-label
        num = _coerce_number(tok)
        if num is not None and i + 1 < len(tokens):
            label_after = _classify_label(tokens[i + 1].rstrip(":,."))
            if label_after and label_after != "_note":
                _assign(label_after, num)
                i += 2
                continue
        # Unrecognised token — skip.
        i += 1

    if note_parts:
        reading["_note"] = " ".join(note_parts)

    if ambiguous:
        # Ambiguous lines are never saved; do not also report missing.
        return {"baaderId": head, "_ambiguous": ambiguous}

    missing: List[str] = []
    for required in ("fishPerMin", "cupsPerMin", "avgWeightKg"):
        if required not in reading:
            missing.append(required)
    if missing:
        return {"baaderId": head, "_missing": missing}

    return reading


def parse_message(text: str) -> ParseResult:
    """Parse a free-form Telegram message into Baader readings.

    Each line is parsed independently. Lines whose first token is not a
    supported Baader id are silently ignored (treated as commentary).
    Lines that *start* with a supported Baader id but are missing any of
    fish/min, cups/min, or avg kg become an error entry naming the missing
    fields.
    """
    result = ParseResult()
    if not text:
        return result
    for line in text.splitlines():
        parsed = _parse_line(line)
        if parsed is None:
            continue
        if "_ambiguous" in parsed:
            result.errors.append(
                {"baaderId": parsed["baaderId"], "ambiguous": parsed["_ambiguous"]}
            )
        elif "_missing" in parsed:
            result.errors.append(
                {"baaderId": parsed["baaderId"], "missing": parsed["_missing"]}
            )
        else:
            # Drop optional note from FPS payload — endpoint doesn't accept it.
            parsed.pop("_note", None)
            result.readings.append(parsed)
    return result


# ---------------------------------------------------------------------------
# Config gating
# ---------------------------------------------------------------------------

def _str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(v) for v in value]


def match_event(event: Any, cfg: Dict[str, Any]) -> bool:
    """Decide whether this event is in scope for capture.

    Gating is exact-match on chat_id, optional thread_id, optional
    sender_id. Empty filter lists mean "any". Anything that fails returns
    False — the gateway then continues to normal agent dispatch.
    """
    if not isinstance(cfg, dict) or not cfg.get("enabled"):
        return False
    if event is None:
        return False
    text = getattr(event, "text", "") or ""
    if not text.strip():
        return False
    source = getattr(event, "source", None)
    if source is None:
        return False

    platform_obj = getattr(source, "platform", None)
    platform_name = getattr(platform_obj, "value", None) or str(platform_obj or "")
    if platform_name != "telegram":
        return False

    tg = cfg.get("telegram") or {}
    chat_ids = _str_list(tg.get("chat_ids"))
    if not chat_ids:
        # No chat_ids configured == nothing matches (fail-closed).
        return False
    if str(getattr(source, "chat_id", "")) not in chat_ids:
        return False

    thread_ids = _str_list(tg.get("thread_ids"))
    if thread_ids:
        if str(getattr(source, "thread_id", "") or "") not in thread_ids:
            return False

    sender_ids = _str_list(tg.get("sender_ids"))
    if sender_ids:
        if str(getattr(source, "user_id", "") or "") not in sender_ids:
            return False

    return True


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _looks_like_baader_attempt(text: str) -> bool:
    """Cheap pre-filter: does the message *look* like a baader update?

    We only consume in-scope messages that look intended for capture; this
    keeps normal agent chat in the same channel flowing to the agent.
    """
    if not text:
        return False
    lowered = text.lower()
    if "baader" in lowered or "fps" in lowered:
        return True
    # Lines that begin with a supported id are the canonical format.
    for line in text.splitlines():
        first = line.strip().split(":", 1)[0].split(maxsplit=1)
        if first and first[0].rstrip(",.") in SUPPORTED_BAADER_IDS:
            return True
    return False


def _fmt_missing_help(errors: List[Dict[str, Any]]) -> str:
    """Compact help reply for incomplete or ambiguous readings.

    Reports both missing fields (none provided on the line) and ambiguous
    fields (the same metric specified more than once, including via
    different aliases — e.g. ``fish 82 fpm 83``).
    """
    lines = ["Baader entry needs a fix:"]
    for err in errors:
        baader_id = err.get("baaderId", "?")
        missing = err.get("missing") or []
        ambiguous = err.get("ambiguous") or []
        if missing:
            lines.append(f"  {baader_id}: missing {', '.join(missing)}")
        if ambiguous:
            lines.append(
                f"  {baader_id}: ambiguous {', '.join(ambiguous)} "
                f"(multiple values given)"
            )
    lines.append("Format: 192 fish 82 cups 105 avg 2.7")
    return "\n".join(lines)


def _fmt_saved(reading: Dict[str, Any]) -> str:
    return (
        f"Saved baader{reading['baaderId']}: "
        f"fish/min={reading['fishPerMin']}, "
        f"cups/min={reading['cupsPerMin']}, "
        f"avg={reading['avgWeightKg']} kg"
    )


def _fmt_post_failure(reading: Dict[str, Any], hint: str) -> str:
    return (
        f"Failed to save baader{reading['baaderId']} reading: {hint}. "
        f"Please retry or save manually in the FPS UI."
    )


def _fmt_verify_warning(reading: Dict[str, Any]) -> str:
    return (
        f"Baader{reading['baaderId']} saved but verification did not match — "
        f"please double-check via the FPS UI."
    )


def _verify_state(
    reading: Dict[str, Any],
    state_body: Any,
) -> bool:
    """Confirm /api/state shows the values we just posted (within rounding)."""
    if not isinstance(state_body, dict):
        return False
    readings = state_body.get("readings") if isinstance(state_body.get("readings"), dict) else None
    if not readings:
        return False
    entry = readings.get(f"baader{reading['baaderId']}")
    if not isinstance(entry, dict):
        return False
    # Compare numerics with a small tolerance to avoid float-eq false alarms.
    def _close(a, b):
        try:
            return abs(float(a) - float(b)) < 0.01
        except (TypeError, ValueError):
            return False
    if not _close(entry.get("fishPerMin"), reading["fishPerMin"]):
        return False
    if not _close(entry.get("avgWeightKg"), reading["avgWeightKg"]):
        return False
    cups = entry.get("cupsPerMin")
    if cups is not None and not _close(cups, reading["cupsPerMin"]):
        return False
    return True


def _resolve_pin(cfg: Dict[str, Any]) -> Optional[str]:
    env_name = cfg.get("fps_pin_env") or "FPS_SAVE_PIN"
    pin = os.environ.get(str(env_name))
    if not pin:
        return None
    return pin


def _safe_status_hint(status: int) -> str:
    """Compact non-secret hint for a non-2xx HTTP status."""
    if status == 401:
        return "auth rejected (HTTP 401)"
    if status == 400:
        return "request rejected (HTTP 400)"
    if 500 <= status < 600:
        return f"server error (HTTP {status})"
    return f"HTTP {status}"


def process_event(
    event: Any,
    *,
    cfg: Dict[str, Any],
    http_post: Callable[..., Tuple[int, Any]],
    http_get: Callable[..., Tuple[int, Any]],
    reply: Callable[[str], None],
    now: Optional[Callable[[], str]] = None,
) -> Optional[Dict[str, Any]]:
    """Main entry point. Returns ``{"action": "skip"}`` when handled, else None.

    The skip action prevents the gateway from continuing to normal agent
    dispatch. We only return skip for messages we actually intend to
    handle (in-scope AND look like a Baader entry). Out-of-scope messages
    and free-form chat return None.
    """
    if not match_event(event, cfg):
        return None

    text = (event.text or "").strip()
    if not _looks_like_baader_attempt(text):
        # In-scope sender/chat but not a baader message — let normal dispatch
        # handle it. Don't consume.
        return None

    parsed = parse_message(text)

    if not parsed.readings and not parsed.errors:
        # Looked like an attempt but had nothing parseable.
        reply("Couldn't read any Baader values from that message.\n"
              "Format: 192 fish 82 cups 105 avg 2.7")
        return {"action": "skip", "reason": "baader_fps_capture"}

    if parsed.errors:
        reply(_fmt_missing_help(parsed.errors))
        # If there's a mix (some valid, some invalid), still POST the valid
        # ones below — fall through.
        if not parsed.readings:
            return {"action": "skip", "reason": "baader_fps_capture"}

    pin = _resolve_pin(cfg)
    base_url = str(cfg.get("fps_api_base_url") or "").rstrip("/")
    timeout = float(cfg.get("request_timeout_seconds") or 5)
    verify = bool(cfg.get("verify_after_post"))

    if not pin:
        logger.warning(
            "wetfish_baader_fps_capture: FPS pin env var unset; cannot POST"
        )
        reply("Cannot save: FPS pin is not configured on the bot. "
              "Set the configured env var and retry.")
        return {"action": "skip", "reason": "baader_fps_capture"}
    if not base_url:
        logger.warning(
            "wetfish_baader_fps_capture: fps_api_base_url unset; cannot POST"
        )
        reply("Cannot save: FPS API URL is not configured on the bot.")
        return {"action": "skip", "reason": "baader_fps_capture"}

    now_fn = now or _now_iso

    for reading in parsed.readings:
        payload = {
            "reading": {
                "baaderId": reading["baaderId"],
                "fishPerMin": reading["fishPerMin"],
                "cupsPerMin": reading["cupsPerMin"],
                "avgWeightKg": reading["avgWeightKg"],
                "ts": now_fn(),
            }
        }
        url = f"{base_url}/api/readings"
        headers = {
            "Content-Type": "application/json",
            "X-FPS-PIN": pin,
        }
        try:
            status, body = http_post(
                url,
                headers=headers,
                json_body=payload,
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001 — converted to safe hint below
            # Critical: never put the exception object (or its repr) into a
            # log line or user reply — it could contain headers/values.
            logger.warning(
                "wetfish_baader_fps_capture: POST to /api/readings failed "
                "for baader%s: %s",
                reading["baaderId"],
                type(exc).__name__,
            )
            reply(_fmt_post_failure(reading, "network error"))
            continue

        if status < 200 or status >= 300:
            logger.warning(
                "wetfish_baader_fps_capture: POST to /api/readings returned "
                "%s for baader%s",
                status,
                reading["baaderId"],
            )
            reply(_fmt_post_failure(reading, _safe_status_hint(status)))
            continue

        # FPS may return HTTP 2xx with a JSON body that doesn't confirm
        # success (ok missing, ok=false, ok=None, ok="false", etc.). Only
        # treat dict bodies where ok is exactly True as a successful save.
        # Non-dict bodies (legacy/empty responses) are left to the verify
        # step below.
        if isinstance(body, dict) and body.get("ok") is not True:
            logger.warning(
                "wetfish_baader_fps_capture: POST to /api/readings returned "
                "%s without ok=true for baader%s",
                status,
                reading["baaderId"],
            )
            reply(_fmt_post_failure(reading, "server did not confirm save"))
            continue

        if verify:
            try:
                vstatus, vbody = http_get(
                    f"{base_url}/api/state",
                    headers={"Accept": "application/json"},
                    timeout=timeout,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "wetfish_baader_fps_capture: verify GET failed for "
                    "baader%s: %s",
                    reading["baaderId"],
                    type(exc).__name__,
                )
                reply(_fmt_verify_warning(reading))
                continue
            if vstatus != 200 or not _verify_state(reading, vbody):
                reply(_fmt_verify_warning(reading))
                continue

        reply(_fmt_saved(reading))

    return {"action": "skip", "reason": "baader_fps_capture"}


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_capture_config() -> Dict[str, Any]:
    """Read ``wetfish.baader_fps_capture`` from hermes config.yaml.

    Returns an empty dict on any failure (no config / parse error / shape
    mismatch). Callers must check ``enabled`` themselves before acting.
    """
    try:
        from hermes_cli.config import cfg_get, load_config
    except Exception as exc:
        logger.debug("hermes_cli.config not importable: %s", exc)
        return {}
    try:
        cfg = load_config()
    except Exception as exc:
        logger.debug("load_config failed: %s", exc)
        return {}
    section = cfg_get(cfg, "wetfish", "baader_fps_capture", default={})
    if not isinstance(section, dict):
        return {}
    return section
