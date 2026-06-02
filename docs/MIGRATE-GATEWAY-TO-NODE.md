# Migrating between Gateway and Node platforms

Meshpoint supports two RF backends on Raspberry Pi hardware:

| Platform | Hardware | RF owner | `capture.sources` |
|----------|----------|----------|-------------------|
| **Gateway** | SX1302/SX1303 concentrator (RAK V2, SenseCap M1, DIY) | Meshpoint HAL | `concentrator` |
| **Node** | WisMesh Pi HAT (RAK6421) + WisBlock SX1262 | **meshtasticd** | `meshtasticd` |

On **Node** platforms, meshtasticd must be running **before** Meshpoint starts. The installer configures systemd ordering automatically.

## WisMesh Node (fresh install)

Use the long-lived branch documented in [`docs/plans/WISMESH-BRANCH.md`](plans/WISMESH-BRANCH.md):

```bash
cd /opt/meshpoint
sudo git fetch origin
sudo git checkout feat/wismesh-hat
sudo git pull
sudo ./scripts/install.sh --platform node
sudo meshpoint setup
```

The wizard detects the RAK6421 HAT and writes `device.platform: node` plus `capture.sources: [meshtasticd]`.

## Switch an existing Gateway to Node

Only do this when the Pi actually has a WisMesh HAT (not an SX1302 concentrator).

```bash
cd /opt/meshpoint
sudo git checkout feat/wismesh-hat
sudo git pull
sudo meshpoint migrate-platform --to node
sudo ./scripts/install.sh --platform node
sudo systemctl restart meshtasticd meshpoint
```

## Switch Node back to Gateway

When you replace the WisMesh HAT with an SX1302 concentrator HAT:

```bash
cd /opt/meshpoint
sudo meshpoint migrate-platform --to gateway
sudo ./scripts/install.sh --platform gateway
sudo systemctl restart meshpoint
```

Re-run `sudo meshpoint setup` if capture sources or region changed.

## Verify meshtasticd (Node only)

```bash
systemctl status meshtasticd
/opt/meshpoint/venv/bin/meshtastic --host localhost:4403 --info
journalctl -u meshpoint -n 50 --no-pager
```

Look for `meshtasticd bridge connected to 127.0.0.1:4403` and `Meshtastic DM identity:` in the Meshpoint logs.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| meshtasticd crash: blank MAC | Ensure `/etc/meshtasticd/config.yaml` has `General.MACAddressSource: eth0` (or `wlan0`) |
| meshtasticd crash: no preset | Re-run `sudo ./scripts/install_meshtasticd.sh` (installs bundled 13302 preset) |
| TX power ~22 dBm on RAK13302 1W module | 13300 preset or PA not powered | `meshtastic --host localhost:4403 --info` should show `txPower=30` and preset `13302` |
| Meshpoint cannot connect to 4403 | Start meshtasticd first: `sudo systemctl restart meshtasticd` then `sudo systemctl restart meshpoint` |
| Dashboard Apply fails at install.sh | Git may still be current while install failed. Run `sudo dpkg --configure -a`, then Apply again or `sudo bash scripts/install.sh` + restart |
| Wrong platform detected | Override with `sudo ./scripts/install.sh --platform node` or edit `device.platform` in `local.yaml` |
| OTA packets in logs then silence | Restart both services; do not run `meshtastic --host` while Meshpoint is up (single TCP client) |
| Phone DM delivered but not on dashboard | meshtasticd node id must match DM destination; see `Meshtastic DM identity` in logs. Remove stale `transmit.node_id` if it disagrees with meshtasticd |
| RSSI looks weak at short range | Check `hops=0 direct` on `>> PKT` line; values are from meshtasticd unchanged. Weak direct RSSI usually means the other radio's antenna/TX, not Meshpoint |

See also [`docs/plans/wisemesh-node-meshtasticd.md`](plans/wisemesh-node-meshtasticd.md) for IPC spike notes and [`docs/plans/WISMESH-BRANCH.md`](plans/WISMESH-BRANCH.md) for full branch architecture.
