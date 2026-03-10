# End-to-End Validation Checklist

Run through this list after deploying updates to the Pi and/or the cloud.

## Pre-Deployment

- [ ] All local tests pass: `python -m pytest tests/ -v`
- [ ] CDK synth succeeds: `cdk synth --no-lookups` (from `cloud/infrastructure/`)
- [ ] Deploy cloud stack: `cdk deploy --require-approval never`

## On the Pi

1. **Pull and restart**
   ```bash
   cd /opt/meshpoint && sudo git pull origin main
   sudo /opt/meshpoint/venv/bin/pip install -r requirements.txt
   sudo systemctl restart meshpoint
   ```

2. **Verify service started**
   ```bash
   journalctl -u meshpoint -n 20 --no-pager
   ```
   Expected: "Mesh Point started" and "Upstream connected" with no tracebacks.

## Validation Steps

- [ ] **Upstream connected** -- Check Pi logs for `Upstream connected to wss://api.meshradar.io`:
  ```bash
  meshpoint logs | grep -i upstream
  ```

- [ ] **Device online in cloud dashboard** -- Visit meshradar.io, log in, and check the fleet view. The Pi should show as "Online" (green dot).

- [ ] **Remote command: Ping** -- In the fleet panel on meshradar.io, click your device, then click **Ping**. Should return a round-trip time in milliseconds, plus uptime and version.

- [ ] **Remote command: Status** -- Click **Status**. Should show version, uptime, and device time.

- [ ] **Remote command: Metrics** -- Click **Metrics**. Should show CPU %, RAM, disk, and temperature.

- [ ] **Remote command: Logs** -- Click **Logs**. Should display recent service log lines in a scrollable block.

- [ ] **Meshtastic packet end-to-end** -- Send a Meshtastic text message from a node within range. Confirm:
  - Packet appears in the local dashboard live feed (`http://<pi-ip>:8080`)
  - Packet appears in the cloud dashboard global packet feed

- [ ] **System metrics on local dashboard** -- Open the local dashboard (`http://<pi-ip>:8080`). Confirm the CPU, RAM, Disk, and CPU Temp stat cards display values.

- [ ] **Heartbeat in CloudWatch** -- Open CloudWatch Logs for the ingest Lambda. Within 5 minutes, confirm `Heartbeat: device=<id>` log entries appear.

- [ ] **Offline transition** -- Stop the meshpoint service (`meshpoint stop`). Within 15 minutes, the device should show as "Offline" in the cloud dashboard. Restart with `meshpoint restart`.

- [ ] **Log rotation** -- Verify journald config is active:
  ```bash
  journalctl --disk-usage
  ```
  Should show usage under 100M after running for a while.

## Provisioned Device Validation

For pre-provisioned devices (shipped to friends), verify before shipping:

- [ ] Device boots and auto-connects to the configured Wi-Fi
- [ ] `meshpoint status` shows "running" with correct device name
- [ ] Device appears in your fleet on meshradar.io within 2 minutes of boot
- [ ] Ping command succeeds from the cloud dashboard
- [ ] Local dashboard accessible at `http://<device-ip>:8080`
