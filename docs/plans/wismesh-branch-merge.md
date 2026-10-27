# Keeping `feat/wismesh-hat` in sync with `main`

`feat/wismesh-hat` tracks WisMesh Node work (meshtasticd bridge, `platform: node`).
`main` tracks gateway work (SX1302 concentrator, PKI mesh participant, native TX).
Both share the dashboard and cloud upstream; RF paths diverge.

## When to merge

After each gateway release lands on `main` (for example v0.7.6, v0.7.7), merge
`origin/main` into `feat/wismesh-hat` before more Node-only commits pile up.

## Merge procedure

```bash
git fetch origin
git checkout feat/wismesh-hat
git merge origin/main
```

1. **Resolve conflicts in `src/api/server.py` first.** Keep WisMesh wiring
   (`_add_meshtasticd_source`, location sync, node DM identity via
   `build_our_meshtastic_node_ids`) AND gateway-only blocks gated with
   `is_node_platform()` from `src/platform_guards.py`.
2. **Never let gateway-only features run unguarded on node.** See
   `GATEWAY_ONLY_CAPABILITIES` in `src/platform_guards.py`.
3. Run the node invariant suite (fast):

   ```bash
   python -m pytest tests/test_node_platform_invariants.py \
     tests/test_server_node_platform_guards.py \
     tests/test_config_node_guards.py -v
   ```

4. Run the full suite:

   ```bash
   python -m pytest tests/ -q
   ```

5. Commit the merge, push `feat/wismesh-hat`.

## Gateway-only vs node-safe

| Capability | Gateway (`platform: gateway`) | Node (`platform: node`) |
|---|---|---|
| SX1302 concentrator capture | Yes | No (sources: `meshtasticd`) |
| PKI keypair bootstrap | Yes | No (meshtasticd owns crypto) |
| Inbound traceroute/telemetry/ACK replies | Yes (native TX) | No |
| Telemetry / position broadcasters | Yes | No |
| TX gain injection / native relay | Yes | No |
| Spectral scan | Yes | No |
| Dashboard DMs / text | Native TX or meshtasticd | meshtasticd only |
| NodeInfo on mesh | Native broadcast + PKI pubkey | meshtasticd `setOwner` sync only |
| MQTT / upstream / SQLite | Yes | Yes |
| MeshCore USB auto-detect | Yes | Suppressed |

## Adding a new gateway feature on `main`

Before merging into `feat/wismesh-hat`:

1. If the feature touches concentrator, native TX, PKI, relay, or spectral
   scan, gate it with `is_gateway_platform(config)` or
   `not is_node_platform(config)`.
2. Add or extend a test in `tests/test_node_platform_invariants.py`.
3. Register the capability name in `GATEWAY_ONLY_CAPABILITIES` when it is
   gateway-only.

## Hot files (expect conflicts)

- `src/api/server.py` (lifespan wiring)
- `docs/HARDWARE-MATRIX.md` (gateway matrix + WisMesh section)
- `src/config.py` / `config/default.yaml` (shared schema)
- `docs/CHANGELOG.md` (ship on `main` only; cherry-pick notes if needed)

## CI

Pushes to `feat/wismesh-hat` run the same pytest + ruff job as `main`. A red
node invariant test blocks shipping a bad merge.

## Hardware smoke (optional after merge)

On a WisMesh Pi with `device.platform: node`:

```bash
cd /opt/meshpoint
sudo git fetch origin && sudo git checkout feat/wismesh-hat && sudo git pull
sudo bash scripts/install.sh --platform node
sudo systemctl restart meshtasticd meshpoint
journalctl -u meshpoint -n 50 --no-pager
```

Confirm: bridge connected, no PKI keypair log, no `lgw_send` / concentrator
errors, dashboard loads, DMs send via meshtasticd.
