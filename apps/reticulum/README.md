# Reticulum and LXMF

Optional Meshpoint plugin adapted from Einstein PD2EMC's work at `javastraat/meshpoint`, commit `b18d6742de6c4cf7fb2e743c690400bea5790a9f`.

## Install only when needed

1. Install **Reticulum** from a pinned catalog in Settings > Plugins.
2. Select **Install Reticulum dependencies**. This downloads [RNS 1.5.3](https://pypi.org/project/rns/1.5.3/) and [LXMF 1.1.1](https://pypi.org/project/lxmf/1.1.1/) using fixed SHA-256 checksums. Libraries are stored separately beside installed plugins. The core Python environment is not upgraded, and no downloaded setup scripts run.
3. Enable Reticulum, restart Meshpoint, then reload the dashboard.
4. Open **Reticulum > Settings**. Choose the interfaces you want, supply their connection settings, save, and restart Meshpoint.

An RNode is optional: a configured TCP interface can provide connectivity without another radio. RF and backbone interfaces start disabled. No public backbone is preselected, and automatic LAN discovery is disabled. Radio settings remain the operator's choice and require device testing.

## Features

RNode settings follow the configured Meshpoint region for missing values.
Explicit saved values remain unchanged. See the
[regional profiles and limitations](../../docs/RETICULUM-REGIONS.md).

- Peers and recent announce activity, with link details and saved contacts.
- LXMF messages with a separate conversation history and read status.
- NomadNet browsing, local Micron page editing, sample pages, and optional hosting.
- Optional propagation storage, outbound propagation-node selection, and synchronization.
- Optional telemetry collection/publishing, with location sharing separately enabled.
- Optional hosted-node information, SpaceAPI/iCalendar pages, and talk-back responses.
- A topbar status chip and live Reticulum dashboard events.

Hosting, propagation, telemetry publishing, notifications, and talk-back features remain off until configured. Extra TCP/UDP interfaces also require explicit configuration.

## Process and data isolation

Reticulum runs in a separate worker process. The worker owns an unprivileged daemon, and its LXMF client requires that shared daemon. It cannot silently fall back to opening the same radio interfaces itself. There is no additional HTTP server, root helper, or global rnsd service. Browser requests pass Meshpoint's admin authentication and then use private process pipes.

Stopping or losing Reticulum does not terminate Meshpoint's core process. Restarting Meshpoint restarts the optional worker and daemon with saved settings. Disabling Reticulum and restarting leaves both stopped.

Messages, peer records, contacts, identity, hosted pages and LXMF data live in the `reticulum/` directory beside the main database. The Reticulum message database is separate from Meshtastic and MeshCore history. Keep this directory in your backups, including the identity file; do not publish its contents.

The generated daemon configuration lives in `reticulum/rns_config/`. Configure interfaces through the dashboard; generated files are replaced on startup. Shared native/Python dependencies and this data directory remain when the plugin is uninstalled. Disable and restart before updating or uninstalling the code.

## Validation status

This is an unreleased plugin. Automated checks cover configuration, messaging,
access controls and process isolation. Bidirectional LXMF delivery and USB
reconnect have been tested with Heltec V3/V4 RNodes on official firmware 1.86.
Full power-cycle recovery, endurance, other hardware, backbone connectivity
and propagation interoperability still require testing.

## First RNode session

Use a separate supported RNode radio with an appropriate antenna. Do not assign
the serial port already used by Meshtastic, MeshCore or GPS. Identical USB
identifiers can occur; select a verified physical `/dev/serial/by-path/` path
when a by-id name is ambiguous. Moving USB sockets can change that path.
See [USB nodes](../../docs/USB-NODES.md).

Review the region shown in Settings and the [starting profiles](../../docs/RETICULUM-REGIONS.md).
Saved values take precedence; changing Meshpoint's region does not silently
retune saved RNode settings. Match peer frequency, bandwidth, SF and coding rate,
enable only the desired interface, save and restart Meshpoint.

The page provides Messages, Peers, Compose, Contacts, Browse, Activity,
Telemetry and Settings views; hosted Pages appear when hosting is enabled.
Select a discovered peer or contact and use Compose to send a test message.
Confirm receipt at the other endpoint. The stored outbound `sent` status means
queued; later delivery callbacks are not currently persisted. A transmit LED
or queued message alone does not establish delivery.

If the RNode is connected but messages do not arrive, test both directions and
confirm receipt at each endpoint. Check matching radio settings, antennas and
the selected USB port. A running daemon, green connection indicator or increasing
USB transmit-byte count does not prove an RF transmission. Restarting Meshpoint
also does not necessarily reset the RNode firmware. If the problem persists,
restart the dedicated RNode using its supported reset procedure, then repeat
the two-way message test after it reconnects. Do not reset a USB node used by
Meshtastic or MeshCore instead. Record whether recovery survives another USB
disconnect/reconnect before treating the issue as resolved.

Keep the RNode and antenna separated from the host and nearby USB electronics
when checking reception problems. Compare actual two-way delivery before and
after moving it; a changed noise-floor reading alone does not identify the
source. A battery-powered RNode can remain powered when USB is disconnected:
USB reconnection and a complete power cycle are different tests. For a full
power cycle, remove every power source using the board's supported procedure,
then reconnect with the antenna attached.

If a board identifies as RNode but cannot start its radio, verify the exact
board/firmware match and official provisioning diagnostics. Screenless V4
hardware needs serial diagnostics. Do not infer wrong firmware from the generic
dashboard error alone, or copy provisioning values from another device.

For consistent backups, disable Reticulum and restart before downloading a
Meshpoint backup: its separate databases are copied as files, unlike the core
SQLite snapshot. Preserve its identity directory and verify a restore on test
hardware. See [backup and restore](../../docs/CONFIGURATION.md#backup-and-restore).
