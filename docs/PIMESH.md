# PiMesh installation and protocol switching

Meshpoint supports the [MeshSmith PiMesh-1W](https://meshsmith.net/wiki/products/pimesh-1w)
through Linux Meshtastic and MeshCore
backends. Both are installed together and share the normal Meshpoint dashboard.
Only one protocol runs on the HAT at a time.

This support is experimental. PiMesh V2 E22P-915M30S has been tested on a Raspberry
Pi 4 running 64-bit Debian 13. V1 and 868 MHz profiles have not been verified on
physical hardware. Peer-assisted messaging and delivery acknowledgement testing
is still required before claiming full feature parity.

## Initial installation

Start with a Pi 4 running 64-bit Debian 12 or 13, network access and a PiMesh HAT
whose physical band matches your region. Debian 13 / V2 915 MHz is the tested
combination. Connect the appropriate antenna before powering the radio.

PiMesh support is on the experimental `codex/pimesh-dual-protocol` branch, not
Stable. Once that branch is published, a fresh device can obtain it with:

```bash
sudo apt update && sudo apt install -y git
sudo git clone --branch codex/pimesh-dual-protocol https://github.com/KMX415/meshpoint.git /opt/meshpoint
cd /opt/meshpoint
```

If you already have that checkout at `/opt/meshpoint`, start there. For a V2
E22P-915M30S in the US, install and reboot:

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

After reboot, reconnect over SSH and run:

```bash
sudo meshpoint setup
```

Provide your activation/API key, device name and position, retain the deployment
region selected during installation, and let the wizard start Meshpoint. The
wizard recognizes the provisioned PiMesh backend. Activation is required before
the dashboard starts on a fresh installation.

Then open `http://<pi-ip>:8080`, create the dashboard administrator password on
the first-run page, and sign in. In Configuration > Radio, confirm the selected
protocol reports connected. Match its radio preset and channels to nearby peers
before checking messages.

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

## Messaging validation

On PiMesh V2 (E22P-915M30S), bidirectional over-the-air tests against a Meshpoint
RAK gateway and MeshCore companion passed for public channels, private channels
with different slot numbers on each device, and direct messages. Direct-message
radio acknowledgements were verified for both protocols. Tests used US LongFast
for Meshtastic and 910.525 MHz / 62.5 kHz / SF7 for MeshCore.

Meshtastic encrypted DMs require the peers to exchange NodeInfo public keys
first. An accepted send request does not prove delivery: the radio can still
reject it or time out. Dashboard sent status currently records submission;
these tests checked receiver storage and radio acknowledgements separately.
This validates the messaging paths, not every protocol-specific feature.

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
