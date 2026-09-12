# Optional plugins and themes

This guide describes the unreleased `feat/v0.8.0` integration. The stable release remains the recommended installation until regression and hardware testing is complete.

## What the base installation includes

Meshtastic and MeshCore keep their existing capture, messaging, configuration, and firmware pages. Plugin and theme managers are available in Settings for administrators. An empty plugin installation performs no optional downloads, starts no extra receiver, and adds no optional Python packages to the core environment.

The repository's `apps/` directory holds catalog source. Meshpoint discovers installed apps only in `plugins/apps/` beside the configured database, normally `data/plugins/apps/`. Cloning the repository does not enable its catalog modules.

## Choose modules

| Module | Purpose | Required native commands | Status |
| --- | --- | --- | --- |
| RTL-SDR | Host page for optional receiver tabs | None for the page itself | Integrated, hardware signoff pending |
| Radio | FM, AM and SSB audio; optional RDS | `rtl_fm`, `ffmpeg`; `redsea` for RDS | Integrated, hardware signoff pending |
| DAB+ | Digital radio multiplex browsing and audio | `welle-cli`, `curl` | Integrated, hardware signoff pending |
| ACARS | Aircraft VHF data messages | `acarsdec` with its native libraries | Integrated, hardware signoff pending |
| ADS-B | Aircraft position messages | `dump1090` | Integrated, hardware signoff pending |
| RTL433 | Compatible sensors and telemetry | `rtl_433` | Integrated, hardware signoff pending |
| P2000 | FLEX pager reception | `rtl_fm`, `multimon-ng` | Integrated, hardware signoff pending |
| Pagers / POCSAG | POCSAG pager reception | `rtl_fm`, `multimon-ng` | Integrated, hardware signoff pending |
| Reticulum / LXMF | Messaging, contacts, NomadNet pages, propagation and telemetry | Install verified optional libraries from the manager | Integrated; physical two-RNode LXMF test passed; recovery/interoperability signoff pending |
| P25 | OP25-based voice/trunking adapter | `meshpoint-op25`, `ffmpeg`, separate OP25/GNU Radio setup | Experimental; native, UI and hardware validation pending |
| DAPNET | Dedicated serial capture and packet history | Optional receiver firmware and pipeline integration required | Not yet in the installable catalog |

An RTL-SDR receiver is separate hardware from the Meshtastic or MeshCore USB nodes. The receive plugins share one SDR reservation: stop the active receiver before starting another. Switching tabs does not stop a recording or retune the receiver. Multiple simultaneous SDR devices are not yet supported by this reservation model.

## Install and enable

Source downloads are locked by default, including on upgrades without an explicit
opt-in. On the device, add `plugin_sources_enabled: true` at the top level of
`config/local.yaml`, then restart Meshpoint. Use a YAML boolean, not a quoted
string. There is no dashboard switch for this permission. With it off, catalog
browsing and installed-module management remain available, but source addition,
revision changes, installation and updates (including theme installs) are denied.
The separate reviewed Reticulum dependency recipe remains available.
Set the flag to `false` and restart to lock downloads again.

This controls the source API, not all administrator capabilities. Backup restore
can replace configuration and plugin files, and enabled plugins run trusted code.
Only restore trusted archives and review these opt-ins after a restore.

The store has searchable module cards, categories, hardware requirements and
installation states. A preview card is not proof that a published source or
native decoder is available. Use the source catalog and installed inventory to
confirm what is actually downloaded and enabled. Optional pages require an
administrator; [public summaries](DASHBOARD-ACCESS.md) do not expose them.

1. Open **Settings > Plugins** as an administrator.
2. Add a trusted GitHub catalog URL and a branch, tag, or commit. Adding a source resolves it to a fixed commit. No background update follows subsequent branch changes.
3. Browse the source and install only the desired items. Installation downloads and validates code; it does not enable it or install dependencies.
4. Install and enable the **RTL-SDR** host before enabling one of its receiver modules.
5. Install the module's native tools on the device. Refresh the plugin list to see missing command checks.
6. Enable the module and restart Meshpoint using the existing restart controls. Reload the dashboard to load its page.
7. Open the optional page, review its receiver settings, and press **Start**. Enablement alone leaves a receiver idle.

The catalog in this feature branch is not published until the branch is pushed. Do not add the stable branch expecting these entries yet. Catalog source code is trusted application code, with access to the Meshpoint process when enabled; it is not sandboxed.

## Dependency setup

Reticulum supplies starting profiles for all six Meshpoint region labels,
with explicit frequency selection required for unknown regions. Saved radio
settings are preserved. See [Reticulum regions](RETICULUM-REGIONS.md).

The manager reports missing command names without executing the commands. A successful command check means the executable exists, not that USB access or reception has passed a hardware test.

Install native dependencies using the device's package manager or the tool's documented build procedure. Package names and availability depend on the device OS. Tools such as ACARS decoders and DAB receivers may require a source build; build and device validation remain part of RC testing. RDS is optional for Radio and should not block ordinary audio reception.

The dashboard does not run downloaded setup scripts as root, grant plugins sudo access, change USB permissions, or install Python packages into the base environment. Privileged one-click native dependency setup is not implemented. Reticulum has a reviewed, unprivileged library recipe: **Install Reticulum dependencies** downloads checksum-pinned RNS and LXMF wheels and extracts only their package trees into `data/plugins/environments/reticulum-v1/`. It runs no setup script or pip dependency upgrade.

Reticulum runs in its own worker process with a managed, unprivileged daemon. The parent communicates over private pipes; there is no extra HTTP listener or systemd unit. A worker or daemon failure leaves core Meshpoint capture running. RF, backbone, automatic LAN discovery, hosting, propagation and telemetry are off by default. Enable the specific interfaces and features you want, save, then restart Meshpoint. See the [Reticulum guide](../apps/reticulum/README.md).

## Updates and removal

Disable an app and restart Meshpoint before updating or uninstalling it. A loaded app cannot be safely unloaded from Python or have its mounted routes removed during a request.

Updating a source revision changes the catalog pin only. It does not update installed apps. Browse the pinned catalog and select **Update** for the individual disabled app. Updates must use the original source. The old code is restored if replacement or configuration persistence fails; the updated app remains disabled until explicitly enabled again.

Uninstall removes the installed app code. Configuration and separately stored captured data remain. Native tools are retained because several modules may share them. Data saved inside an app's own code directory is removed with that directory; plugin authors must store persistent data separately.

## Themes

**Settings > Themes** includes the existing Dark, High Contrast and Sunlight palettes, a custom palette editor, and a device default selector. The browser's saved choice takes precedence over the device default. Themes change presentation and need no radio hardware or native dependencies.

Custom themes can be saved or installed from a catalog. Reload after adding or editing a theme so its stylesheet is loaded. Built-in themes cannot be removed. Theme CSS must be local: external imports and asset URLs are rejected.

## Plugin authors

Each app has `plugin.toml`, an API version, declared capabilities, and an optional `backend/__init__.py` registration function. This integration supports authenticated HTTP routes, services, idle listeners, sidebar pages, page hooks, and topbar chips. Capture and protocol registration are still pending.

Frontend scripts and styles must be declared in the manifest. Only successfully loaded plugins expose these files through the authenticated asset endpoint. Backend files, setup files, and undeclared assets are not served. Optional pages currently require an administrator session.

Use `[deps].executables` for command availability checks and `[deps].apt` to describe package requirements. Neither field executes an installer. Keep dependencies optional, keep persistent data outside the installed code directory, and make listener construction side-effect free. Hardware opens only from an explicit Start action. Stop must tolerate an idle or partially initialized listener.

Receiver packages and page registries are adapted from Einstein PD2EMC's `javastraat/meshpoint` work at `b18d6742de6c4cf7fb2e743c690400bea5790a9f`. Source attribution is retained for the eventual port commits.


## Receiver regions and local channels

Radio starts with manual tuning. The Netherlands preset library is optional,
explicitly selected, and contains examples to verify locally. Existing favorites
are retained. FM audio correction starts at 75 microseconds for US and 50 for
EU_868; other regions require an explicit selection. A saved `plugins.radio.deemphasis_us`
overrides that starting value. The selected value applies to both FM audio paths.
See [ITU-R BS.450](https://www.itu.int/rec/R-REC-BS.450-4-201910-I/en).

Pagers, POCSAG, RTL433 and ACARS do not assume a local channel. Enter receive
frequencies on their pages before starting. Stop before changing frequency.
Selections remain for the running Meshpoint session; they do not automatically
write device configuration. For a persistent default, the first three accept
`plugins.<module>.frequency_mhz`; ACARS preserves `plugins.acars.freqs`.
ACARS accepts one to eight VHF channels; usable simultaneous channel spacing
also depends on the decoder and receiver. Invalid settings are rejected.

P2000 is specifically the Netherlands FLEX service at 169.65 MHz. DAB/DAB+
currently supports Band III only, and requires locally available broadcasts.
ADS-B remains a 1090 MHz receiver. None of these receiver choices change the
Meshpoint mesh radios or Reticulum RF settings.

P25 has a local draft adapter and catalog entry; it is not a release-ready receiver.
[OP25](https://github.com/boatbod/op25/blob/master/README.md) is the candidate
for Phase I/II voice and trunk tracking. Initial scope is unencrypted voice,
talkgroup selection and explicit system/control-channel setup. Native dependency
installation, SDR ownership, audio integration and Pi performance need validation.

See the [P25 candidate README](../apps/p25/README.md) for the current contract
and outstanding work. DAPNET capture/protocol integration remains pending.
Flock camera detection was discussed but is not an implemented catalog feature.

## Backup and recovery

Disable apps and restart before taking a consistent backup of their separate
databases. The main database has live-snapshot handling; optional databases do
not. Retain plugin configuration, source pins, custom themes and Reticulum
identity/data, and record the native tools installed outside Meshpoint's data
directory. See [backup and restore](CONFIGURATION.md#backup-and-restore).
Restoring an archive can restore enabled app flags and public-view policy;
review both before returning the device to normal use.
