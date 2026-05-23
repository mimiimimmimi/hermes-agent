"""Tests for the wetfish_baader_fps_capture plugin.

Covers the bundled opt-in plugin at ``plugins/wetfish_baader_fps_capture/``:

  * ``capture.parse_message``: tolerant parser for "192 fish 82 cups 105 avg 2.7"
    style lines, including multi-reading messages and named missing-field
    errors for incomplete entries.
  * ``capture.match_event``: config gating by platform / chat_id / thread_id /
    sender_id and enabled flag.
  * ``capture.process_event``: end-to-end hook orchestration with injected
    HTTP + reply callables. In-scope valid messages POST readings to the FPS
    API and return ``{"action": "skip"}``; in-scope invalid messages send a
    compact help reply and still return skip; out-of-scope messages return
    ``None`` and never POST.
  * Secret hygiene: FPS pin must never appear in replies or in the recorded
    POST URL/body even on failure.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO_ROOT / "plugins" / "wetfish_baader_fps_capture"
SENTINEL_PIN = "super-secret-pin"


def _load_capture():
    """Import the plugin's capture module directly from the repo path."""
    mod_name = "wetfish_baader_fps_capture_under_test"
    cached = sys.modules.get(mod_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        mod_name, PLUGIN_DIR / "capture.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load capture module from {PLUGIN_DIR}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def _load_plugin_shell():
    """Import the plugin package (the __init__.py shell with _http_post/_http_get)."""
    return importlib.import_module("plugins.wetfish_baader_fps_capture")


def _make_event(
    *,
    text: str,
    platform: str = "telegram",
    chat_id: str = "-1001234567890",
    thread_id: str | None = "17585",
    user_id: str = "armi_telegram_id",
    message_id: str = "m1",
):
    """Build a minimal MessageEvent-like object for tests.

    We use SimpleNamespace rather than importing the real MessageEvent because
    the test isolates the parser/gating logic from gateway internals.
    The shape mirrors gateway.platforms.base.MessageEvent + gateway.session
    SessionSource fields used by ``match_event``/``process_event``.
    """
    source = types.SimpleNamespace(
        platform=types.SimpleNamespace(value=platform),
        chat_id=chat_id,
        thread_id=thread_id,
        user_id=user_id,
        message_id=message_id,
        chat_type="group",
    )
    return types.SimpleNamespace(
        text=text,
        source=source,
        message_id=message_id,
    )


def _default_cfg():
    return {
        "enabled": True,
        "fps_api_base_url": "http://127.0.0.1:8090",
        "fps_pin_env": "FPS_SAVE_PIN",
        "request_timeout_seconds": 5,
        "verify_after_post": True,
        "verify_via_history_csv": False,
        "telegram": {
            "chat_ids": ["-1001234567890"],
            "thread_ids": ["17585"],
            "sender_ids": ["armi_telegram_id", "zion_telegram_id"],
            "reply_on_unmatched_prefix": False,
            "accepted_prefixes": ["baader", "fps", "192", "212"],
        },
    }


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestParseMessage:
    def test_parses_two_readings_one_per_line(self):
        capture = _load_capture()
        text = (
            "192 fish 82 cups 105 avg 2.7 issue infeed gaps\n"
            "212 fish 48 cups 130 avg 1.3 issue ok"
        )
        result = capture.parse_message(text)
        assert result.errors == []
        assert len(result.readings) == 2

        r1 = result.readings[0]
        assert r1["baaderId"] == "192"
        assert r1["fishPerMin"] == 82
        assert r1["cupsPerMin"] == 105
        assert r1["avgWeightKg"] == 2.7

        r2 = result.readings[1]
        assert r2["baaderId"] == "212"
        assert r2["fishPerMin"] == 48
        assert r2["cupsPerMin"] == 130
        assert r2["avgWeightKg"] == 1.3

    def test_accepts_alternate_labels(self):
        capture = _load_capture()
        text = "192 fpm 90 cpm 110 weight 2.4"
        result = capture.parse_message(text)
        assert result.errors == []
        assert result.readings[0]["fishPerMin"] == 90
        assert result.readings[0]["cupsPerMin"] == 110
        assert result.readings[0]["avgWeightKg"] == 2.4

    def test_rejects_missing_cups_per_min(self):
        capture = _load_capture()
        text = "192 fish 82 avg 2.7"
        result = capture.parse_message(text)
        assert result.readings == []
        assert len(result.errors) == 1
        err = result.errors[0]
        assert err["baaderId"] == "192"
        assert "cupsPerMin" in err["missing"]
        # Must NOT inflate the error with avg kg (which was present).
        assert "avgWeightKg" not in err["missing"]

    def test_rejects_missing_avg_weight(self):
        capture = _load_capture()
        text = "212 fish 48 cups 130"
        result = capture.parse_message(text)
        assert result.readings == []
        assert len(result.errors) == 1
        err = result.errors[0]
        assert err["baaderId"] == "212"
        assert "avgWeightKg" in err["missing"]

    def test_rejects_missing_fish_per_min(self):
        capture = _load_capture()
        text = "212 cups 130 avg 1.3"
        result = capture.parse_message(text)
        assert result.readings == []
        err = result.errors[0]
        assert err["baaderId"] == "212"
        assert "fishPerMin" in err["missing"]

    def test_ignores_non_baader_lines(self):
        capture = _load_capture()
        text = "hello team\n192 fish 82 cups 105 avg 2.7\nrandom note"
        result = capture.parse_message(text)
        assert len(result.readings) == 1
        assert result.errors == []
        assert result.readings[0]["baaderId"] == "192"

    def test_unsupported_baader_id_is_ignored(self):
        capture = _load_capture()
        # 198 is not a real baader on this line; treat as comment.
        text = "198 fish 50 cups 60 avg 1.0"
        result = capture.parse_message(text)
        assert result.readings == []
        assert result.errors == []

    def test_empty_text_returns_nothing(self):
        capture = _load_capture()
        result = capture.parse_message("")
        assert result.readings == []
        assert result.errors == []

    def test_rejects_duplicate_fish_same_alias(self):
        """Reviewer blocker: ``fish 82 fish 99`` is ambiguous; do not save."""
        capture = _load_capture()
        text = "192 fish 82 fish 99 cups 105 avg 2.7"
        result = capture.parse_message(text)
        assert result.readings == []
        assert len(result.errors) == 1
        err = result.errors[0]
        assert err["baaderId"] == "192"
        ambiguous = err.get("ambiguous") or []
        assert "fishPerMin" in ambiguous

    def test_rejects_duplicate_fish_different_alias(self):
        """``fish 82 fpm 83`` — duplicate via different aliases is also ambiguous."""
        capture = _load_capture()
        text = "192 fish 82 fpm 83 cups 105 avg 2.7"
        result = capture.parse_message(text)
        assert result.readings == []
        assert len(result.errors) == 1
        err = result.errors[0]
        assert err["baaderId"] == "192"
        assert "fishPerMin" in (err.get("ambiguous") or [])

    def test_rejects_duplicate_cups_different_alias(self):
        capture = _load_capture()
        text = "212 fish 48 cups 105 cpm 106 avg 1.3"
        result = capture.parse_message(text)
        assert result.readings == []
        assert len(result.errors) == 1
        err = result.errors[0]
        assert err["baaderId"] == "212"
        assert "cupsPerMin" in (err.get("ambiguous") or [])

    def test_rejects_duplicate_avg_different_alias(self):
        capture = _load_capture()
        text = "192 fish 82 cups 105 avg 2.7 weight 2.8"
        result = capture.parse_message(text)
        assert result.readings == []
        assert len(result.errors) == 1
        err = result.errors[0]
        assert err["baaderId"] == "192"
        assert "avgWeightKg" in (err.get("ambiguous") or [])

    def test_duplicate_does_not_silently_take_first_value(self):
        """The reviewer's exact repro: must NOT save fishPerMin=82 silently."""
        capture = _load_capture()
        text = "192 fish 82 fish 99 cups 105 avg 2.7"
        result = capture.parse_message(text)
        assert not any(r.get("fishPerMin") == 82 for r in result.readings)
        assert result.readings == []


# ---------------------------------------------------------------------------
# Gating tests
# ---------------------------------------------------------------------------

class TestMatchEvent:
    def test_matches_in_scope_event(self):
        capture = _load_capture()
        ev = _make_event(text="192 fish 82 cups 105 avg 2.7")
        assert capture.match_event(ev, _default_cfg()) is True

    def test_rejects_wrong_platform(self):
        capture = _load_capture()
        ev = _make_event(text="192 fish 82 cups 105 avg 2.7", platform="discord")
        assert capture.match_event(ev, _default_cfg()) is False

    def test_rejects_wrong_chat(self):
        capture = _load_capture()
        ev = _make_event(text="192 fish 82 cups 105 avg 2.7", chat_id="-9999")
        assert capture.match_event(ev, _default_cfg()) is False

    def test_rejects_wrong_thread(self):
        capture = _load_capture()
        ev = _make_event(text="192 fish 82 cups 105 avg 2.7", thread_id="42")
        assert capture.match_event(ev, _default_cfg()) is False

    def test_rejects_wrong_sender(self):
        capture = _load_capture()
        ev = _make_event(
            text="192 fish 82 cups 105 avg 2.7", user_id="someone_else"
        )
        assert capture.match_event(ev, _default_cfg()) is False

    def test_rejects_when_disabled(self):
        capture = _load_capture()
        cfg = _default_cfg()
        cfg["enabled"] = False
        ev = _make_event(text="192 fish 82 cups 105 avg 2.7")
        assert capture.match_event(ev, cfg) is False

    def test_rejects_empty_text(self):
        capture = _load_capture()
        ev = _make_event(text="")
        assert capture.match_event(ev, _default_cfg()) is False

    def test_accepts_when_thread_filter_unset(self):
        """An empty thread_ids list means: accept any thread."""
        capture = _load_capture()
        cfg = _default_cfg()
        cfg["telegram"]["thread_ids"] = []
        ev = _make_event(text="192 fish 82 cups 105 avg 2.7", thread_id="99999")
        assert capture.match_event(ev, cfg) is True

    def test_accepts_when_sender_filter_unset(self):
        """An empty sender_ids list means: accept any sender."""
        capture = _load_capture()
        cfg = _default_cfg()
        cfg["telegram"]["sender_ids"] = []
        ev = _make_event(text="192 fish 82 cups 105 avg 2.7", user_id="nobody")
        assert capture.match_event(ev, cfg) is True


# ---------------------------------------------------------------------------
# process_event orchestration tests
# ---------------------------------------------------------------------------

class _FakeHttp:
    """Records POST/GET calls and replies according to a script."""

    def __init__(
        self,
        *,
        post_status: int = 200,
        post_body=None,
        state_body=None,
        raise_on_post: bool = False,
        raise_on_get: bool = False,
    ):
        self.posts: list[dict] = []
        self.gets: list[dict] = []
        self._post_status = post_status
        # Use None as the sentinel so an explicit empty dict / falsy body
        # (e.g. ``{}`` for "missing ok" tests) is preserved rather than
        # silently replaced by the default success body.
        self._post_body = {"ok": True} if post_body is None else post_body
        self._state_body = state_body or {
            "readings": {
                "baader192": {"fishPerMin": 82, "avgWeightKg": 2.7, "cupsPerMin": 105},
            }
        }
        self._raise_on_post = raise_on_post
        self._raise_on_get = raise_on_get

    def post(self, url, *, headers, json_body, timeout):
        self.posts.append(
            {"url": url, "headers": dict(headers), "json": json_body, "timeout": timeout}
        )
        if self._raise_on_post:
            raise RuntimeError(
                f"network unreachable; pin={SENTINEL_PIN}"
            )
        return self._post_status, self._post_body

    def get(self, url, *, headers, timeout):
        self.gets.append({"url": url, "headers": dict(headers), "timeout": timeout})
        if self._raise_on_get:
            raise RuntimeError("verify boom")
        return 200, self._state_body


class _Replies:
    def __init__(self):
        self.sent: list[str] = []

    def __call__(self, text: str) -> None:
        self.sent.append(text)


class TestProcessEvent:
    def test_valid_single_reading_posts_and_replies(self, monkeypatch):
        capture = _load_capture()
        monkeypatch.setenv("FPS_SAVE_PIN", SENTINEL_PIN)

        http = _FakeHttp()
        replies = _Replies()
        ev = _make_event(text="192 fish 82 cups 105 avg 2.7")

        result = capture.process_event(
            ev,
            cfg=_default_cfg(),
            http_post=http.post,
            http_get=http.get,
            reply=replies,
        )
        assert result == {"action": "skip", "reason": "baader_fps_capture"}

        assert len(http.posts) == 1
        post = http.posts[0]
        assert post["url"].endswith("/api/readings")
        assert post["headers"]["X-FPS-PIN"] == SENTINEL_PIN
        reading = post["json"]["reading"]
        assert reading["baaderId"] == "192"
        assert reading["fishPerMin"] == 82
        assert reading["cupsPerMin"] == 105
        assert reading["avgWeightKg"] == 2.7
        assert "ts" in reading  # ISO timestamp added

        # Verified once
        assert len(http.gets) == 1
        assert http.gets[0]["url"].endswith("/api/state")

        # User received a saved confirmation
        assert any("saved" in s.lower() or "ok" in s.lower() for s in replies.sent)

    def test_valid_two_readings_posts_twice(self, monkeypatch):
        capture = _load_capture()
        monkeypatch.setenv("FPS_SAVE_PIN", SENTINEL_PIN)

        http = _FakeHttp(state_body={
            "readings": {
                "baader192": {"fishPerMin": 82, "avgWeightKg": 2.7, "cupsPerMin": 105},
                "baader212": {"fishPerMin": 48, "avgWeightKg": 1.3, "cupsPerMin": 130},
            }
        })
        replies = _Replies()
        ev = _make_event(text=(
            "192 fish 82 cups 105 avg 2.7\n"
            "212 fish 48 cups 130 avg 1.3"
        ))

        result = capture.process_event(
            ev,
            cfg=_default_cfg(),
            http_post=http.post,
            http_get=http.get,
            reply=replies,
        )
        assert result == {"action": "skip", "reason": "baader_fps_capture"}

        assert len(http.posts) == 2
        baader_ids = sorted(p["json"]["reading"]["baaderId"] for p in http.posts)
        assert baader_ids == ["192", "212"]

    def test_incomplete_reading_sends_help_and_skips(self, monkeypatch):
        capture = _load_capture()
        monkeypatch.setenv("FPS_SAVE_PIN", SENTINEL_PIN)

        http = _FakeHttp()
        replies = _Replies()
        # Missing avg weight
        ev = _make_event(text="212 fish 48 cups 130")

        result = capture.process_event(
            ev,
            cfg=_default_cfg(),
            http_post=http.post,
            http_get=http.get,
            reply=replies,
        )
        assert result == {"action": "skip", "reason": "baader_fps_capture"}
        # No POST attempted with an incomplete reading
        assert http.posts == []
        # A compact reply is sent that names the missing field
        assert replies.sent
        joined = "\n".join(replies.sent).lower()
        assert "avgweightkg" in joined or "avg" in joined
        # Reply does not leak the pin
        assert SENTINEL_PIN not in joined

    def test_out_of_scope_returns_none(self, monkeypatch):
        capture = _load_capture()
        monkeypatch.setenv("FPS_SAVE_PIN", SENTINEL_PIN)

        http = _FakeHttp()
        replies = _Replies()
        # Wrong sender => out of scope
        ev = _make_event(
            text="192 fish 82 cups 105 avg 2.7", user_id="someone_else"
        )

        result = capture.process_event(
            ev,
            cfg=_default_cfg(),
            http_post=http.post,
            http_get=http.get,
            reply=replies,
        )
        assert result is None
        assert http.posts == []
        assert http.gets == []
        assert replies.sent == []

    def test_no_baader_text_in_scope_returns_none(self, monkeypatch):
        """In-scope channel/sender but the message has no baader payload.

        We must not consume normal agent chat — return None so the gateway
        falls through to the agent.
        """
        capture = _load_capture()
        monkeypatch.setenv("FPS_SAVE_PIN", SENTINEL_PIN)

        http = _FakeHttp()
        replies = _Replies()
        ev = _make_event(text="hey team how's it going?")

        result = capture.process_event(
            ev,
            cfg=_default_cfg(),
            http_post=http.post,
            http_get=http.get,
            reply=replies,
        )
        assert result is None
        assert http.posts == []
        assert replies.sent == []

    def test_post_failure_reply_does_not_leak_pin(self, monkeypatch):
        capture = _load_capture()
        monkeypatch.setenv("FPS_SAVE_PIN", SENTINEL_PIN)

        http = _FakeHttp(raise_on_post=True)
        replies = _Replies()
        ev = _make_event(text="192 fish 82 cups 105 avg 2.7")

        result = capture.process_event(
            ev,
            cfg=_default_cfg(),
            http_post=http.post,
            http_get=http.get,
            reply=replies,
        )
        assert result == {"action": "skip", "reason": "baader_fps_capture"}
        # A failure reply went out
        assert replies.sent
        joined = "\n".join(replies.sent)
        assert SENTINEL_PIN not in joined
        # User-visible failure must be compact and not contain the raw
        # exception (which embedded the pin in the test).
        for reply in replies.sent:
            assert "RuntimeError" not in reply
            assert "Traceback" not in reply

    def test_post_500_reply_does_not_leak_pin(self, monkeypatch):
        capture = _load_capture()
        monkeypatch.setenv("FPS_SAVE_PIN", SENTINEL_PIN)

        http = _FakeHttp(post_status=500, post_body={"error": "boom"})
        replies = _Replies()
        ev = _make_event(text="192 fish 82 cups 105 avg 2.7")

        result = capture.process_event(
            ev,
            cfg=_default_cfg(),
            http_post=http.post,
            http_get=http.get,
            reply=replies,
        )
        assert result == {"action": "skip", "reason": "baader_fps_capture"}
        joined = "\n".join(replies.sent)
        assert SENTINEL_PIN not in joined

    def test_verify_mismatch_warns_but_does_not_leak_pin(self, monkeypatch):
        capture = _load_capture()
        monkeypatch.setenv("FPS_SAVE_PIN", SENTINEL_PIN)

        # POST succeeds, but verify returns a state where the reading
        # doesn't match what we posted.
        http = _FakeHttp(state_body={
            "readings": {
                "baader192": {"fishPerMin": 1, "avgWeightKg": 0.1, "cupsPerMin": 1},
            }
        })
        replies = _Replies()
        ev = _make_event(text="192 fish 82 cups 105 avg 2.7")

        capture.process_event(
            ev,
            cfg=_default_cfg(),
            http_post=http.post,
            http_get=http.get,
            reply=replies,
        )
        joined = "\n".join(replies.sent)
        assert SENTINEL_PIN not in joined
        # Some indication that verification didn't match.
        assert any(
            "verif" in r.lower() or "mismatch" in r.lower() for r in replies.sent
        )

    def test_pin_not_in_logs_or_exceptions(self, monkeypatch, caplog):
        capture = _load_capture()
        monkeypatch.setenv("FPS_SAVE_PIN", SENTINEL_PIN)
        http = _FakeHttp(raise_on_post=True)
        replies = _Replies()
        ev = _make_event(text="192 fish 82 cups 105 avg 2.7")

        with caplog.at_level("DEBUG"):
            capture.process_event(
                ev,
                cfg=_default_cfg(),
                http_post=http.post,
                http_get=http.get,
                reply=replies,
            )
        log_text = "\n".join(rec.getMessage() for rec in caplog.records)
        assert SENTINEL_PIN not in log_text

    def test_missing_pin_env_blocks_post(self, monkeypatch):
        capture = _load_capture()
        monkeypatch.delenv("FPS_SAVE_PIN", raising=False)
        http = _FakeHttp()
        replies = _Replies()
        ev = _make_event(text="192 fish 82 cups 105 avg 2.7")
        result = capture.process_event(
            ev,
            cfg=_default_cfg(),
            http_post=http.post,
            http_get=http.get,
            reply=replies,
        )
        # In-scope, so we still skip + reply, but never call POST without a pin.
        assert result == {"action": "skip", "reason": "baader_fps_capture"}
        assert http.posts == []
        assert replies.sent

    def test_ambiguous_duplicate_does_not_post(self, monkeypatch):
        """Reviewer blocker: ambiguous line must skip without POSTing."""
        capture = _load_capture()
        monkeypatch.setenv("FPS_SAVE_PIN", SENTINEL_PIN)

        http = _FakeHttp()
        replies = _Replies()
        ev = _make_event(text="192 fish 82 fish 99 cups 105 avg 2.7")

        result = capture.process_event(
            ev,
            cfg=_default_cfg(),
            http_post=http.post,
            http_get=http.get,
            reply=replies,
        )
        assert result == {"action": "skip", "reason": "baader_fps_capture"}
        assert http.posts == []
        assert replies.sent
        joined = "\n".join(replies.sent).lower()
        # Compact guidance must name which field was ambiguous.
        assert "ambiguous" in joined or "duplicate" in joined
        assert "fish" in joined or "fishpermin" in joined
        # No "Saved" confirmation must go out for an ambiguous line.
        assert not any("saved baader" in s.lower() for s in replies.sent)
        # Reply must not leak the pin.
        assert SENTINEL_PIN not in joined

    def test_post_200_ok_false_is_failure(self, monkeypatch):
        """Reviewer blocker: HTTP 200 with {"ok": false} is a failure."""
        capture = _load_capture()
        monkeypatch.setenv("FPS_SAVE_PIN", SENTINEL_PIN)

        http = _FakeHttp(post_status=200, post_body={"ok": False})
        replies = _Replies()
        ev = _make_event(text="192 fish 82 cups 105 avg 2.7")

        result = capture.process_event(
            ev,
            cfg=_default_cfg(),
            http_post=http.post,
            http_get=http.get,
            reply=replies,
        )
        assert result == {"action": "skip", "reason": "baader_fps_capture"}
        # The POST happened
        assert len(http.posts) == 1
        # Must NOT verify, must NOT emit "Saved" confirmation.
        assert http.gets == []
        joined_lower = "\n".join(replies.sent).lower()
        assert "saved baader" not in joined_lower
        # A failure reply must have gone out.
        assert any(
            "failed" in s.lower() or "could not" in s.lower() or "couldn't" in s.lower()
            for s in replies.sent
        )
        # Reply must not leak the pin.
        assert SENTINEL_PIN not in "\n".join(replies.sent)

    @pytest.mark.parametrize(
        "post_body",
        [
            {},  # missing ok entirely
            {"status": "ok"},  # ok missing, other fields present
            {"ok": None},  # ok is None
            {"ok": "false"},  # ok is the string "false"
            {"ok": "true"},  # ok is the string "true" — still not exactly True
            {"ok": 1},  # truthy but not exactly True
            {"ok": 0},  # falsy non-False
        ],
        ids=[
            "missing_ok",
            "ok_absent_other_fields",
            "ok_none",
            "ok_string_false",
            "ok_string_true",
            "ok_int_one",
            "ok_int_zero",
        ],
    )
    def test_post_200_dict_body_without_ok_true_is_failure(
        self, monkeypatch, post_body
    ):
        """HTTP 2xx with dict body where ok is not exactly True is a failure.

        Reviewer blocker: previously only ``ok is False`` was treated as
        failure, so missing/None/truthy-non-True values silently passed and
        produced a (misleading) "Saved" reply.
        """
        capture = _load_capture()
        monkeypatch.setenv("FPS_SAVE_PIN", SENTINEL_PIN)

        http = _FakeHttp(post_status=200, post_body=post_body)
        replies = _Replies()
        ev = _make_event(text="192 fish 82 cups 105 avg 2.7")

        result = capture.process_event(
            ev,
            cfg=_default_cfg(),
            http_post=http.post,
            http_get=http.get,
            reply=replies,
        )
        assert result == {"action": "skip", "reason": "baader_fps_capture"}
        # POST attempted exactly once.
        assert len(http.posts) == 1
        # Must NOT verify (no GET) and must NOT emit a "Saved" confirmation.
        assert http.gets == []
        joined = "\n".join(replies.sent)
        assert "Saved baader" not in joined
        assert "saved baader" not in joined.lower()
        # Compact failure reply went out.
        assert replies.sent
        assert any(
            "failed" in s.lower() or "could not" in s.lower() or "couldn't" in s.lower()
            for s in replies.sent
        )
        # Reply must not leak the pin and must not contain raw body content.
        assert SENTINEL_PIN not in joined
        for reply in replies.sent:
            assert "Traceback" not in reply

    def test_post_201_dict_body_with_ok_true_succeeds(self, monkeypatch):
        """Sanity: a 2xx response with ok=True still saves and verifies."""
        capture = _load_capture()
        monkeypatch.setenv("FPS_SAVE_PIN", SENTINEL_PIN)

        http = _FakeHttp(post_status=201, post_body={"ok": True})
        replies = _Replies()
        ev = _make_event(text="192 fish 82 cups 105 avg 2.7")

        result = capture.process_event(
            ev,
            cfg=_default_cfg(),
            http_post=http.post,
            http_get=http.get,
            reply=replies,
        )
        assert result == {"action": "skip", "reason": "baader_fps_capture"}
        assert len(http.posts) == 1
        # Verify ran and Saved reply went out.
        assert len(http.gets) == 1
        assert any("saved baader" in s.lower() for s in replies.sent)


# ---------------------------------------------------------------------------
# HTTP helper tests (User-Agent + header propagation)
# ---------------------------------------------------------------------------

class _FakeUrlopenResponse:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class TestHttpHelpersUserAgent:
    """Wetfish ops found that the live FPS endpoint returns HTTP 403 when
    urllib sends no User-Agent. Both _http_post and _http_get must include
    a stable product-style User-Agent on every outbound request, alongside
    any caller-supplied headers (including the secret X-FPS-PIN).
    """

    def test_http_post_includes_user_agent_and_pin(self):
        plugin = _load_plugin_shell()
        captured = {}

        def _fake_urlopen(req, timeout):
            captured["req"] = req
            captured["timeout"] = timeout
            return _FakeUrlopenResponse(200, b'{"ok": true}')

        with patch.object(plugin.urllib.request, "urlopen", _fake_urlopen):
            status, body = plugin._http_post(
                "http://127.0.0.1:8090/api/readings",
                headers={"Content-Type": "application/json", "X-FPS-PIN": SENTINEL_PIN},
                json_body={"reading": {"baaderId": "192"}},
                timeout=5,
            )

        assert status == 200
        assert body == {"ok": True}
        req = captured["req"]
        assert req.get_method() == "POST"
        # urllib stores headers title-cased on first capitalize.
        assert req.get_header("User-agent") == plugin.USER_AGENT
        assert req.get_header("X-fps-pin") == SENTINEL_PIN
        assert req.get_header("Content-type") == "application/json"
        # Body must be the JSON-encoded payload.
        assert json.loads(req.data.decode("utf-8")) == {"reading": {"baaderId": "192"}}

    def test_http_get_includes_user_agent(self):
        plugin = _load_plugin_shell()
        captured = {}

        def _fake_urlopen(req, timeout):
            captured["req"] = req
            return _FakeUrlopenResponse(200, b'{"readings": {}}')

        with patch.object(plugin.urllib.request, "urlopen", _fake_urlopen):
            status, body = plugin._http_get(
                "http://127.0.0.1:8090/api/state",
                headers={"Accept": "application/json"},
                timeout=5,
            )

        assert status == 200
        assert body == {"readings": {}}
        req = captured["req"]
        assert req.get_method() == "GET"
        assert req.get_header("User-agent") == plugin.USER_AGENT
        assert req.get_header("Accept") == "application/json"
        # GET must not carry the secret pin.
        assert req.get_header("X-fps-pin") is None
        assert req.data is None

    def test_user_agent_is_stable_non_secret_product_string(self):
        plugin = _load_plugin_shell()
        # Stable identifier, not derived from any secret. Must be a non-empty
        # product-style token so the FPS server's UA check accepts it.
        ua = plugin.USER_AGENT
        assert isinstance(ua, str) and ua
        assert "/" in ua  # product/version shape
        assert SENTINEL_PIN not in ua

    def test_caller_supplied_user_agent_overrides_default(self):
        """If a future caller needs a different UA, it should win over the default."""
        plugin = _load_plugin_shell()
        captured = {}

        def _fake_urlopen(req, timeout):
            captured["req"] = req
            return _FakeUrlopenResponse(200, b"")

        with patch.object(plugin.urllib.request, "urlopen", _fake_urlopen):
            plugin._http_get(
                "http://127.0.0.1:8090/api/state",
                headers={"User-Agent": "OverrideAgent/9.9"},
                timeout=5,
            )

        assert captured["req"].get_header("User-agent") == "OverrideAgent/9.9"

    def test_http_helpers_do_not_log_pin(self, caplog):
        plugin = _load_plugin_shell()

        def _fake_urlopen(req, timeout):
            return _FakeUrlopenResponse(200, b'{"ok": true}')

        with caplog.at_level("DEBUG"), patch.object(
            plugin.urllib.request, "urlopen", _fake_urlopen
        ):
            plugin._http_post(
                "http://127.0.0.1:8090/api/readings",
                headers={"Content-Type": "application/json", "X-FPS-PIN": SENTINEL_PIN},
                json_body={"reading": {"baaderId": "192"}},
                timeout=5,
            )

        log_text = "\n".join(rec.getMessage() for rec in caplog.records)
        assert SENTINEL_PIN not in log_text
