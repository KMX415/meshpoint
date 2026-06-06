# LAN Automation API

Meshpoint exposes a small REST surface for Home Assistant, Node-RED, and other LAN automation tools. It reuses the same data and TX paths as the dashboard but accepts a static API token so scripts do not need browser cookies.

**Local network only.** Do not port-forward port 8080 to the internet. The automation API is designed for trusted LAN clients.

## Enable

1. Generate a long random token (32+ characters):

   ```bash
   openssl rand -hex 32
   ```

2. Add to `config/local.yaml`:

   ```yaml
   automation:
     enabled: true
     token: "paste-your-64-char-hex-here"
   ```

3. Restart Meshpoint:

   ```bash
   sudo systemctl restart meshpoint
   ```

When `automation.enabled` is `false` (the default), all `/api/automation/*` routes return **403** and existing dashboard behaviour is unchanged.

## Authentication

Present the token using either header:

| Header | Example |
|--------|---------|
| `X-Meshpoint-Token` | `X-Meshpoint-Token: abc123...` |
| `Authorization` | `Authorization: Bearer abc123...` |

A valid dashboard JWT (cookie or `Authorization: Bearer <jwt>`) also works when automation is enabled.

## Endpoints (v1)

Base URL: `http://<meshpoint-ip>:8080`

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/automation/status` | Uptime, relay stats, WebSocket client count |
| `GET` | `/api/automation/nodes` | Node list with signal (`?limit=500&enrich=true`) |
| `GET` | `/api/automation/nodes/{id}` | Single node record |
| `GET` | `/api/automation/packets` | Recent packets (`?limit=100`) |
| `POST` | `/api/automation/send` | Send Meshtastic text (broadcast or DM) |

### Send message

```json
POST /api/automation/send
Content-Type: application/json
X-Meshpoint-Token: <your-token>

{
  "text": "Hello from Home Assistant",
  "channel": 0,
  "destination": "broadcast",
  "protocol": "meshtastic",
  "want_ack": false
}
```

Response (success):

```json
{
  "success": true,
  "packet_id": 1234567890,
  "protocol": "meshtastic",
  "timestamp": "2026-06-02T12:00:00+00:00",
  "airtime_ms": 42,
  "error": null
}
```

TX rate limits and duty-cycle guards from the native messaging stack still apply.

## curl examples

```bash
export MESHPOINT="http://192.168.1.50:8080"
export TOKEN="your-automation-token"

# Health check
curl -s -H "X-Meshpoint-Token: $TOKEN" "$MESHPOINT/api/automation/status" | jq .

# List nodes
curl -s -H "X-Meshpoint-Token: $TOKEN" "$MESHPOINT/api/automation/nodes?limit=20" | jq .

# Recent packets
curl -s -H "X-Meshpoint-Token: $TOKEN" "$MESHPOINT/api/automation/packets?limit=5" | jq .

# Broadcast
curl -s -X POST -H "Content-Type: application/json" \
  -H "X-Meshpoint-Token: $TOKEN" \
  -d '{"text":"Test from curl","channel":0}' \
  "$MESHPOINT/api/automation/send" | jq .
```

## Home Assistant

REST sensor for node count:

```yaml
rest:
  - resource: "http://192.168.1.50:8080/api/automation/nodes?limit=500"
    headers:
      X-Meshpoint-Token: !secret meshpoint_automation_token
    scan_interval: 60
    sensor:
      - name: "Mesh Nodes"
        value_template: "{{ value_json | length }}"
        unit_of_measurement: "nodes"
```

REST command to send a message:

```yaml
rest_command:
  meshpoint_broadcast:
    url: "http://192.168.1.50:8080/api/automation/send"
    method: POST
    headers:
      Content-Type: "application/json"
      X-Meshpoint-Token: !secret meshpoint_automation_token
    payload: '{"text":"{{ message }}","channel":0}'
```

Automation example:

```yaml
automation:
  - alias: "Meshpoint morning status"
    trigger:
      - platform: time
        at: "08:00:00"
    action:
      - service: rest_command.meshpoint_broadcast
        data:
          message: "Good morning from Home Assistant"
```

Store the token in `secrets.yaml`:

```yaml
meshpoint_automation_token: "your-64-char-hex-token"
```

## Node-RED

Use an **http request** node:

- Method: `GET` or `POST` as needed
- URL: `http://192.168.1.50:8080/api/automation/status`
- Headers: `X-Meshpoint-Token` → your token (use an environment variable or credentials store)

## Errors

| Status | Meaning |
|--------|---------|
| `401` | Missing or invalid token / JWT |
| `403` | Automation API disabled (`automation.enabled: false`) |
| `503` | Enabled but token missing or shorter than 32 characters |

The raw token is never returned by `GET /api/config`; only `automation.token_set: true/false` is exposed.
