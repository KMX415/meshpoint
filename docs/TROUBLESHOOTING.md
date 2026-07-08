# Troubleshooting

### Service won't start

```bash
meshpoint logs
```

Common issues:
- **"No module named 'src'"**: Check that `/opt/meshpoint` contains the source code.
- **"Permission denied: /dev/spidev0.0"**: Run `sudo usermod -a -G spi meshpoint`
- **"No module named 'psutil'"**: Run `sudo /opt/meshpoint/venv/bin/pip install psutil`
- **"no GPIO tool found (pinctrl or gpioset)"**: This means the concentrator reset script can't toggle GPIO. Raspberry Pi OS Lite (64-bit) includes `pinctrl` by default. If you're on a non-standard image, install `gpiod`: `sudo apt install -y gpiod`

### Concentrator fails to start

If logs show `lgw_start() failed` or `Failed to set SX1250_0 in STANDBY_RC mode`:

The SPI bus latched due to a hard power cut. `sudo reboot` and `meshpoint restart` normally prevent this, but a hard power loss (yanked cable, outage) can still cause it. Do a full power cycle:

1. `sudo poweroff`
2. Wait for the green LED to stop blinking
3. Unplug power for 10+ seconds, then plug back in

### RAK Hotspot V2 (RAK7248) specific issues

Some RAK7248 carriers (especially enclosed Helium Hotspot V2 units) are more
sensitive to reset timing than standard RAK Pi HATs.

**Symptoms**
- `lgw_start()` returns -1 with "chip version is 0x00" or "0x05"
- "Failed to set SX1250_0 in STANDBY_RC mode" even after a full power cycle
- Works when running manually as the `pi` user but fails under the `meshpoint` service user

**Common fixes**

1. **Increase reset hold time** (most effective for many users):

   Add this to your systemd service (or the environment section):

   ```ini
   Environment=CONCENTRATOR_RESET_HOLD_SEC=1.0
   ```

   This makes the Python-side reset use a longer pulse (the shell pre-script
   still runs with its default timing).

2. **SPI device-tree overlay conflict**:

   On some RAK7248 boards the line `dtoverlay=spi0-0cs` in `/boot/firmware/config.txt`
   produces the kernel error:

   ```
   spi-bcm2835 ... there is not valid maps for state default
   ```

   Try commenting it out:

   ```bash
   sudo sed -i 's/^dtoverlay=spi0-0cs/#dtoverlay=spi0-0cs/' /boot/firmware/config.txt
   sudo reboot
   ```

3. **GPIO 25 behavior**:

   On certain RAK7248 carriers GPIO 25 is part of the reset circuit rather than
   (or in addition to) a power-enable line. Using it as a separate "power GPIO"
   in custom reset sequences can hold the chip in reset.

After making changes, do a full physical power cycle (unplug 15–20 s) before testing.

### Database errors after update

If logs show `sqlite3.OperationalError: table nodes has no column named <column>`:

The database schema is older than the current code. The service runs automatic migrations on startup. If it fails with `attempt to write a readonly database`, fix permissions:

```bash
sudo chmod 777 /opt/meshpoint/data
sudo chmod 666 /opt/meshpoint/data/*.db
sudo systemctl restart meshpoint
```

### Concentrator starts but receives no packets

If the logs show `SX1302 concentrator started` and `Sync word set to 0x2B` but the receive loop consistently reports `0 pkt this cycle`, the SX1250 radio's analog front-end may be damaged. This typically happens after:

- Repeated power loss events (storms, breaker trips, yanked cables)
- SPI bus latch events (the `lgw_start() failed` error, even if resolved by power cycling)

The SX1250's digital SPI interface can recover while the RF receive path remains non-functional. To confirm: test a known-working Meshtastic device within a few meters. If still zero packets, the RAK2287 module needs replacement (~$50-60). The Pi and carrier board are unaffected.

### No LoRa packets captured

- Verify the concentrator is detected: `ls /dev/spidev0.*`
- Verify libloragw is installed: `ls /usr/local/lib/libloragw.so`
- Check that there are Meshtastic/MeshCore devices transmitting in your area
- Verify the antenna is connected

### MeshCore companion not receiving packets

- Verify the device is detected: `ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null`
- Check that the companion is running USB companion firmware (not BLE)
- Verify radio frequency matches your region: re-run `sudo meshpoint setup` to reconfigure
- Check logs: `meshpoint logs | grep -i meshcore`
- If the device was recently plugged in, unplug and re-plug to reset the serial connection

### TX not working (messages not received by other nodes)

1. Verify TX is enabled in the Radio settings page on the dashboard
2. Confirm the HAL TX sync word patch was applied (this happens automatically when you run `install.sh`): `meshpoint logs | grep -i "tx\|transmit"`. If TX is silently failing, re-run `sudo bash /opt/meshpoint/scripts/install.sh` to re-apply the patch idempotently.
3. Verify the modem preset matches the mesh network you're targeting (e.g. LongFast)
4. Check that the antenna is connected: transmitting without an antenna damages the radio

### Not appearing on cloud dashboard

1. Check that `upstream.enabled` is `true` in your local config
2. Verify your API key is correct
3. Check logs: `meshpoint logs | grep -i upstream`
4. Make sure the Pi has internet access: `ping google.com`

### Remote commands not working

1. Check the fleet view on meshradar.io: device should show as "Online"
2. Try a Ping command from the fleet panel
3. Check logs: `meshpoint logs | grep -i "command\|response"`

### Recovering from a corrupted install

If `meshpoint logs` shows `SyntaxError: source code string cannot contain null bytes` or `git pull` fails with `error: inflate` / `fatal: loose object is corrupt`, the SD card took a bad write (usually from a hard power cut).

#### Disaster recovery with a saved backup (recommended)

Use this when you have a **Settings → System → Download backup** `.tar.gz` saved on your PC or NAS (not only on the Pi).

**Before you start**

1. Keep the backup file **off the Pi**. A dead SD card takes the on-device copy with it.
2. Do **not** delete or rotate the Meshradar API key in the backup until upstream reconnects after restore, or be ready to paste a new key for the same `device_id` (see [COMMON-ERRORS.md](COMMON-ERRORS.md#upstream-http-403-after-restore)).

**Steps (dashboard user path)**

1. Flash a fresh SD card (or wipe and reinstall on the same card):
   ```bash
   sudo git clone https://github.com/KMX415/meshpoint.git /opt/meshpoint
   cd /opt/meshpoint
   sudo bash scripts/install.sh
   ```
2. **Bootstrap activation (SSH, required on a blank install).** The dashboard will not load until `config/local.yaml` has a valid Meshradar API key. The service exits with `Meshpoint is not activated` until then. Run the setup wizard once:
   ```bash
   sudo meshpoint setup
   ```
   Paste **any** valid API key from [meshradar.io](https://meshradar.io). Accept defaults for the rest if you are about to restore: restore overwrites this throwaway config.
3. Start the service:
   ```bash
   sudo systemctl restart meshpoint
   ```
4. Open the dashboard. Complete **`/setup`** with any admin password (also replaced by restore).
5. **Settings → System → Restore backup** and upload your saved `.tar.gz`. Wait for the service to restart.
6. Sign in with the **password from before the disaster** (restore puts back `web_auth` from the archive).
7. Confirm local data: nodes and packets should match the backup snapshot. Check upstream:
   ```bash
   meshpoint logs | grep -i upstream
   ```
   You should see `connected to wss://api.meshradar.io`. If you see `HTTP 403`, the API key in the backup was revoked on Meshradar: generate a new key for the restored `device_id`, then run `sudo meshpoint setup` and paste it (or edit `upstream.auth_token` in `config/local.yaml`), and restart.

**What restore brings back:** `device_id`, channel keys, PKI keys, SQLite database (nodes, packets, messages), dashboard password, and the API key that was in the archive at backup time.

**What restore does not fix:** A Meshradar API key you deleted in the cloud after taking the backup. Local restore can succeed while upstream stays on `HTTP 403` until you update the key.

#### SSH restore when the dashboard will not load

If the service will not stay up long enough for the upload UI, copy the archive to the Pi and finish from SSH:

```bash
scp meshpoint-backup-*.tar.gz pi@<pi-ip>:/tmp/meshpoint-restore.tar.gz
ssh pi@<pi-ip>
sudo bash /opt/meshpoint/scripts/restore_finish.sh /tmp/meshpoint-restore.tar.gz
```

See [COMMON-ERRORS.md](COMMON-ERRORS.md#restore-backup-stopped-the-service-and-it-never-came-back) if restore stops the service and does not restart it.

#### Manual re-clone without a backup file

**SSH fallback** when you have no `.tar.gz` backup:

```bash
cd /opt/meshpoint
sudo cp -r data/ /tmp/meshpoint-data-backup
sudo cp config/local.yaml /tmp/local-yaml-backup
cd /home/pi
sudo rm -rf /opt/meshpoint
sudo git clone https://github.com/KMX415/meshpoint.git /opt/meshpoint
sudo cp -r /tmp/meshpoint-data-backup /opt/meshpoint/data/
sudo cp /tmp/local-yaml-backup /opt/meshpoint/config/local.yaml
sudo chmod 777 /opt/meshpoint/data
sudo chmod 666 /opt/meshpoint/data/*.db
sudo python3 -m venv /opt/meshpoint/venv
sudo /opt/meshpoint/venv/bin/pip install -r /opt/meshpoint/requirements.txt
sudo systemctl restart meshpoint
```

This preserves your packet database and device config. The venv must be recreated since it is not tracked by git.

### Backup before SD card trouble

On a healthy Meshpoint, open **Settings → System → Download backup** and save the file to your PC or NAS.

The archive contains `config/local.yaml` (API key, `device_id`, web auth hashes, radio and MQTT settings) and the full `data/` tree (SQLite database, PKI private keys, rollback state). It is **not encrypted**. Treat it like a password vault: offline storage only.

Download a fresh backup:

- Before flashing or replacing the SD card
- Before **Clear database** or other destructive actions (restore can still roll back, but an off-Pi copy is safer)
- When root disk use climbs above 90% (the System page also suggests it at that threshold)

Restore always returns the Pi to the **backup snapshot**, even if you cleared the database or changed config after that backup was taken.

### Using pip on Raspberry Pi OS

Raspberry Pi OS (Bookworm and later) uses PEP 668 externally-managed environments. Never use the system `pip` directly: always use the venv:

```bash
sudo /opt/meshpoint/venv/bin/pip install -r requirements.txt
```

Running `sudo pip install ...` without the venv path will fail with `error: externally-managed-environment`.
