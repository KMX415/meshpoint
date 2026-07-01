# Home Assistant Cookbook

Copy-paste recipes for Meshpoint LAN automation. Enable the API first
(see [API-AUTOMATION.md](./API-AUTOMATION.md)), then add these snippets
to `configuration.yaml` or package files.

All examples assume:

- Meshpoint dashboard: `http://192.168.1.50:8080`
- Token stored in `secrets.yaml` as `meshpoint_automation_token`

## Node count sensor

```yaml
rest:
  - resource: "http://192.168.1.50:8080/api/automation/nodes?limit=500"
    headers:
      X-Meshpoint-Token: !secret meshpoint_automation_token
    scan_interval: 60
    sensor:
      - name: "Mesh Nodes"
        unique_id: meshpoint_node_count
        value_template: "{{ value_json | length }}"
        unit_of_measurement: "nodes"
        icon: mdi:access-point-network
```

## Meshpoint health binary

Alerts when the automation API stops responding (power loss, service crash).

```yaml
rest:
  - resource: "http://192.168.1.50:8080/api/automation/status"
    headers:
      X-Meshpoint-Token: !secret meshpoint_automation_token
    scan_interval: 30
    binary_sensor:
      - name: "Meshpoint Online"
        unique_id: meshpoint_online
        value_template: "{{ value_json.uptime_seconds is defined }}"
        device_class: connectivity
```

## Relay activity sensor

```yaml
rest:
  - resource: "http://192.168.1.50:8080/api/automation/status"
    headers:
      X-Meshpoint-Token: !secret meshpoint_automation_token
    scan_interval: 60
    sensor:
      - name: "Meshpoint Relayed"
        unique_id: meshpoint_relayed_total
        value_template: "{{ value_json.relay.relayed | default(0) }}"
        unit_of_measurement: "packets"
      - name: "Meshpoint Relay Rejected"
        unique_id: meshpoint_relay_rejected
        value_template: "{{ value_json.relay.rejected | default(0) }}"
        unit_of_measurement: "packets"
```

## Broadcast from an automation

```yaml
rest_command:
  meshpoint_broadcast:
    url: "http://192.168.1.50:8080/api/automation/send"
    method: POST
    headers:
      Content-Type: "application/json"
      X-Meshpoint-Token: !secret meshpoint_automation_token
    payload: '{"text":"{{ message }}","channel":0,"destination":"broadcast"}'

automation:
  - alias: "Mesh morning check-in"
    trigger:
      - platform: time
        at: "08:00:00"
    action:
      - service: rest_command.meshpoint_broadcast
        data:
          message: "Good morning from Home Assistant"
```

## Alert when node count drops

Useful when a backbone node disappears from the mesh.

```yaml
automation:
  - alias: "Mesh node count drop"
    trigger:
      - platform: numeric_state
        entity_id: sensor.mesh_nodes
        below: 5
        for: "00:05:00"
    action:
      - service: notify.mobile_app
        data:
          title: "Meshpoint alert"
          message: "Node count fell below 5 for 5 minutes"
```

## MQTT + Home Assistant (packet stream)

If `mqtt.enabled` is true, Meshpoint can publish decoded packets to your
broker. Enable **Home Assistant auto-discovery** under Configuration →
MQTT, or subscribe manually to `msh/<region>/2/json/...` topics.

The Configuration MQTT card shows live broker health: connection state,
publish count, disconnect count, and topic prefix.

## Node-RED

Use an **http request** node pointed at `/api/automation/status` or
`/api/automation/nodes` with header `X-Meshpoint-Token`. Poll every 30–60 s
for dashboards; use inject + POST for one-shot messages.

## Security notes

- Keep `automation.token` at 32+ random characters.
- Do not expose port 8080 to the internet.
- MQTT credentials live in `config/local.yaml`; treat that file like a secret.
