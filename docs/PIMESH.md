# PiMesh installation and protocol switching

Meshpoint supports the [MeshSmith PiMesh-1W](https://meshsmith.net/wiki/products/pimesh-1w)
through Linux Meshtastic and MeshCore
backends. Both are installed together and share the normal Meshpoint dashboard.
Only one protocol runs on the HAT at a time.

This support is experimental. PiMesh V2 E22P-915M30S has been tested on a Raspberry
Pi 4 running 64-bit Debian 13. V1 and 868 MHz profiles have not been verified on
physical hardware. Bidirectional messaging and radio acknowledgements passed
the tests described below; full feature parity remains unverified.

## Backends and attribution

Meshpoint provides the dashboard, message storage, installer and supervisor that
switches ownership of the PiMesh radio. Radio operation is supplied by these
upstream projects:

| Protocol | Backend | Integration |
| --- | --- | --- |
| Meshtastic | [meshtasticd](https://github.com/meshtastic/firmware), from the Meshtastic project | A separate daemon, accessed through the Meshtastic TCP API. |
| MeshCore | [openHop Repeater](https://github.com/openhop-dev/openhop_repeater) and [openHop Core](https://github.com/openhop-dev/openhop_core), by Rightup and contributors | A separate daemon with a local TCP companion interface used by Meshpoint. |

openHop Core implements the MeshCore protocol in Python and drives the SPI radio.
Credit for that backend belongs to the openHop authors; Meshpoint's PiMesh
integration builds on their work. The original MeshCore protocol and C++ project
are maintained by [MeshCore](https://github.com/meshcore-dev/MeshCore).

The PiMesh installer clones openHop Repeater into `/opt/meshpoint-openhop` at
revision `13eb8b2ea8b1cdb4a07ed6e282dc99e3aa8a5a8b`. That revision pins
`openhop_core==1.1.3`. It uses a dedicated Python environment and system service.
Meshpoint applies [a local compatibility patch](../scripts/patch_openhop.py) to
ensure changes to TX power reach the radio; this patch is maintained by Meshpoint.

The pinned [Repeater license](https://github.com/openhop-dev/openhop_repeater/blob/13eb8b2ea8b1cdb4a07ed6e282dc99e3aa8a5a8b/LICENSE)
and [Core 1.1.3 release](https://pypi.org/project/openhop-core/1.1.3/) specify the
MIT license. Their copyright and license notices must be retained when copying
or distributing their software. The installer keeps the upstream checkout's
license, and the Core package includes its license. Meshpoint's AGPL-3.0 license
does not replace those upstream licenses. This integration does not imply
endorsement by the upstream projects.

## Initial installation

Start with a Pi 4 running 64-bit Debian 12 or 13, network access and a PiMesh HAT
whose physical band matches your region. Debian 13 / V2 915 MHz is the tested
combination. Connect the appropriate antenna before powering the radio.

PiMesh support is experimental and is included in RC (`feat/v0.8.0`). The
`codex/pimesh-dual-protocol` development branch also remains available. For the
RC installation, a fresh device can obtain it with:

```bash
sudo apt update && sudo apt install -y git
sudo git clone --branch feat/v0.8.0 https://github.com/KMX415/meshpoint.git /opt/meshpoint
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

## Device roles and forwarding

On provisioned PiMesh installations, **Configuration > Radio > Device behavior**
lets an administrator change the active backend's behavior without reinstalling.
These controls are hidden on concentrator and other non-PiMesh installations.

For Meshtastic, the available roles are Client, Client mute, Client base, Router,
Router late and Repeater. Client is the normal starting point; Client mute does
not relay other devices' traffic. Infrastructure roles change relay scheduling
and may affect telemetry and device information. The rebroadcast filter further
limits eligible traffic. All skip decoding requires Repeater. Specialized tracker,
sensor and deprecated roles are not offered; an existing unsupported role is
displayed without silently changing it. Saving can briefly restart the radio.

For MeshCore, the choices call the separate
[openHop Repeater](https://github.com/openhop-dev/openhop_repeater) backend:

| Mode | Behavior |
| --- | --- |
| Monitor | Receive and send local messages without repeating other devices. |
| Forward | Repeat eligible MeshCore traffic and allow local messages. |
| No TX | Receive only; block all backend transmissions, including acknowledgements. |

Forwarding does not enable repeater advertisements or discovery; those remain
separate openHop settings. No TX is stronger than Meshpoint's application TX
toggle. A queued or accepted message is not evidence of a radio transmission.
This UI calls openHop's mode API; it does not implement or copy its forwarding
engine. These modes are not equivalent to every Meshtastic role.

The UI confirms changes from a backend response. If a save is unconfirmed,
wait for the radio to reconnect and choose **Reload behavior** before retrying.
Each backend stores its own settings across protocol switches and service restarts.

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
