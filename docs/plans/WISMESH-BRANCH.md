# WisMesh Node platform (`feat/wismesh-hat`)

Experimental **Meshpoint Node** support for the RAK6421 WisMesh Pi HAT (meshtasticd-backed RF).
This work lives on a **long-lived branch** and may not merge to `main` for some time.
Gateway users (RAK2287 / SenseCap M1 concentrators) should stay on **`main`**.

## Install (6421 + WisBlock module)

```bash
cd /opt/meshpoint
sudo git fetch origin
sudo git checkout feat/wismesh-hat
sudo git pull origin feat/wismesh-hat
sudo ./scripts/install.sh --platform node
sudo meshpoint setup
sudo systemctl restart meshtasticd meshpoint
```

`install.sh --platform node` will:

- Skip the SX1302 HAL build
- Install and configure **meshtasticd** (Debian 12/13 OBS repo)
- Copy the RAK6421 LoRa preset and set `MACAddressSource`
- Install `meshpoint-node.service` (starts **after** meshtasticd)

The setup wizard writes `device.platform: node` and `capture.sources: [meshtasticd]`.

## Verify

```bash
systemctl status meshtasticd meshpoint
/opt/meshpoint/venv/bin/meshtastic --host localhost:4403 --info
journalctl -u meshpoint -n 30 --no-pager | grep meshtasticd
```

## Migrate between platforms

See [`docs/MIGRATE-GATEWAY-TO-NODE.md`](../MIGRATE-GATEWAY-TO-NODE.md) and `meshpoint migrate-platform --to node|gateway`.

## Switch back to Gateway (concentrator)

```bash
cd /opt/meshpoint
sudo git checkout main
sudo git pull origin main
sudo meshpoint migrate-platform --to gateway --force
sudo ./scripts/install.sh --platform gateway
sudo systemctl restart meshpoint
```

Preserve `config/local.yaml` if you want the same `device_id` and API key.

## Related docs

- [`wisemesh-node-meshtasticd.md`](wisemesh-node-meshtasticd.md): meshtasticd IPC spike notes
- [`MIGRATE-GATEWAY-TO-NODE.md`](../MIGRATE-GATEWAY-TO-NODE.md): migration runbook
