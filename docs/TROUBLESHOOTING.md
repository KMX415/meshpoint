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
2. Check that `patch_hal.sh` was run after install: `meshpoint logs | grep -i "tx\|transmit"`
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

If `meshpoint logs` shows `SyntaxError: source code string cannot contain null bytes` or `git pull` fails with `error: inflate` / `fatal: loose object is corrupt`, the SD card took a bad write (usually from a hard power cut). Fix with a clean re-clone:

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

### Using pip on Raspberry Pi OS

Raspberry Pi OS (Bookworm and later) uses PEP 668 externally-managed environments. Never use the system `pip` directly: always use the venv:

```bash
sudo /opt/meshpoint/venv/bin/pip install -r requirements.txt
```

Running `sudo pip install ...` without the venv path will fail with `error: externally-managed-environment`.
