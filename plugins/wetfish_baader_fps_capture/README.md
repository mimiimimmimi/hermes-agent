# wetfish_baader_fps_capture

Opt-in Hermes Agent plugin that turns Telegram Baader status messages into
HTTP POSTs against the Wetfish FPS pi-server `/api/readings` endpoint.

This is a **Wetfish-internal workflow plugin**. It is shipped with the repo
in disabled form: until both the plugin entry and its config block are
enabled, the hook is dormant.

## What it does

When a message arrives on the gateway's `pre_gateway_dispatch` hook:

1. If the platform / chat_id / thread_id / sender_id do not match this
   plugin's config, the hook returns `None` and the message continues to
   normal agent dispatch.
2. If the message *does* match but doesn't look like a Baader update
   (no "baader", no "fps", no line beginning with `192`/`212`), it also
   returns `None` so normal chat still reaches the agent.
3. Matching Baader entries are parsed, POSTed to `/api/readings` with the
   `X-FPS-PIN` header read from the configured env var, and confirmed via
   `GET /api/state`. The hook returns `{"action": "skip"}` so the agent
   does not also reply.

## Message format

One reading per line. Order of `<id> <label> <value> ...` is fixed at the
id, but the label/value pairs can appear in any order on the line.

```
192 fish 82 cups 105 avg 2.7 issue infeed gaps
212 fish 48 cups 130 avg 1.3 issue ok
```

Tolerated label aliases:

| Field          | Accepted labels                       |
|----------------|---------------------------------------|
| `fishPerMin`   | `fish`, `fish/min`, `fpm`             |
| `cupsPerMin`   | `cups`, `cups/min`, `cpm`             |
| `avgWeightKg`  | `avg`, `average`, `weight`, `kg`      |
| (free comment) | `issue`, `comment`, `note`, `notes`   |

All three numeric fields are required for this workflow. Incomplete
entries get a compact reply naming the missing field; nothing is POSTed.
Cups/min is **not optional here**, even though the FPS API would accept a
reading without it.

## Configuration

Enable the plugin in `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - wetfish_baader_fps_capture

wetfish:
  baader_fps_capture:
    # Top-level kill switch. If false (or this block is missing), the
    # hook returns None on every event.
    enabled: true

    # FPS pi-server base URL. Trailing slash optional.
    fps_api_base_url: "http://127.0.0.1:8090"

    # Name of the env var that holds the X-FPS-PIN value. The value is
    # never read from config and never logged.
    fps_pin_env: "FPS_SAVE_PIN"

    # POST/GET timeout. Verify GET uses the same timeout.
    request_timeout_seconds: 5

    # After POST, GET /api/state and confirm the reading was persisted.
    verify_after_post: true

    # Reserved: alternate verify path via history CSV.
    verify_via_history_csv: false

    telegram:
      # Exact match. Must include the leading "-" for Telegram supergroups.
      chat_ids: ["-1001234567890"]
      # Optional. Empty list == accept any thread in the chat.
      thread_ids: ["17585"]
      # Optional. Empty list == accept any sender in the chat/thread.
      sender_ids: ["armi_telegram_id", "zion_telegram_id"]

      # Currently unused (reserved for a future prefix-only ack mode).
      reply_on_unmatched_prefix: false
      accepted_prefixes: ["baader", "fps", "192", "212"]
```

The pin itself goes in the environment, **not** in config. Example
systemd unit excerpt:

```
Environment=FPS_SAVE_PIN=********
```

## Rollback

Remove `wetfish_baader_fps_capture` from `plugins.enabled` (or set
`wetfish.baader_fps_capture.enabled: false`) and restart the gateway.
There is no on-disk state and no migration. The FPS pi-server is
untouched by this plugin's removal.

## What is NOT in scope

- No production deployment is performed by this plugin or this PR.
- No edits to the FPS pi-server. The capture hook only consumes its
  documented public API surface.
- No write to any platform other than Telegram.
- No agent slash commands. The agent never sees a successfully-captured
  message (the hook returns `skip`).
