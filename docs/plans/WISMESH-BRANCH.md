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
sudo ./scripts/install.sh --platform node   # when Phase 1 lands; until then standard install
sudo meshpoint setup
sudo systemctl restart meshpoint
```

Requires **meshtasticd** installed and configured per RAK's WisMesh quickstart before Meshpoint can capture RF (Phase 2 bridge).

## Switch back to Gateway (concentrator)

```bash
cd /opt/meshpoint
sudo git checkout main
sudo git pull origin main
sudo ./scripts/install.sh
sudo systemctl restart meshpoint
```

Preserve `config/local.yaml` if you want the same `device_id` and API key.
