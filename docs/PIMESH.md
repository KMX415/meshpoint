# PiMesh installation and protocol switching

Meshpoint supports the MeshSmith PiMesh-1W through Linux Meshtastic and MeshCore
backends. Both are installed together and share the normal Meshpoint dashboard.
Only one protocol runs on the HAT at a time.

This support is experimental. PiMesh V2 E22P-915M30S has been tested on a Raspberry
Pi 4 running 64-bit Debian 13. V1 and 868 MHz profiles have not been verified on
physical hardware. Peer-assisted messaging and delivery acknowledgement testing
is still required before claiming full feature parity.

## Initial installation

Use a Meshpoint build containing PiMesh support. From its checkout, for a V2
E22P-915M30S in the US:

```bash
sudo bash scripts/install.sh --platform pimesh --board pimesh-v2 --band 915 --region US --protocol meshtastic
sudo reboot
```

Use `--protocol meshcore` to start with MeshCore instead. Both backends are
installed either way. First installation requires explicit hardware selection
because automatic HAT identification is not reliable.

For V1 use `--board pimesh-v1`. Select the physical module band and deployment
region: US/915, ANZ/915 or EU_868/868. The initial reboot enables SPI and the
required GPIO configuration.

Open `http://<pi-ip>:8080` to complete activation and administrator setup.

## Switching protocols and updating

An administrator can select Meshtastic or MeshCore in **Configuration > Radio**.
Switching briefly interrupts messaging and reconnects the dashboard. Each
protocol retains its own identity, channels and radio settings; history is
preserved. A failed switch attempts to restore the previous working protocol.

The **Settings > Updates** branch picker changes the installed software build.
It is separate from the radio protocol selector. The experimental PiMesh entry
and protocol controls appear only on provisioned PiMesh installations. The
selected software branch must be published before updates can be fetched.

Subsequent installs detect the provisioning record and preserve the hardware
profile and selected protocol. Switching protocols does not require another
installation or reboot.

MeshCore's application TX control blocks Meshpoint messages and adverts; native
protocol acknowledgements remain managed by its daemon. Protocol-specific
telemetry and advert behavior are retained.

## Diagnostics and backups

```bash
systemctl status meshpoint meshtasticd meshpoint-openhop
journalctl -u meshpoint -u meshtasticd -u meshpoint-openhop
```

Only the selected radio daemon should be active. Do not manually start both.
The authenticated `/api/pimesh/status` endpoint reports switch progress and
recovery errors. `/var/lib/meshpoint-radio/state.json` stores the last working
selection. Retry a failed recovery through the protocol selector after resolving
the reported problem.

Back up Meshpoint's database and private configuration, the meshtasticd data
directory, `/etc/meshpoint-openhop` and `/var/lib/meshpoint-openhop`. These contain
separate identities and channel secrets; retain them during software updates.
