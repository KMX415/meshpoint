# radio

Optional Meshpoint receiver plugin, adapted from javastraat/meshpoint at `b18d6742de6c4cf7fb2e743c690400bea5790a9f`. Original author: Einstein PD2EMC.

This folder is catalog source, not an installed or enabled module. Install only the modules you want through Settings > Plugins. Receiver modules use the optional RTL-SDR host page; install and enable `rtlsdr` as well. Restart after enabling.

Required commands: rtl_fm, ffmpeg. Install the documented native tools on the device before enabling this module. Setup does not run automatically. See [the optional plugin guide](../../docs/PLUGINS.md) for package availability, setup limitations, hardware sharing, and removal.

Enabling creates an idle listener. Press Start in the plugin page to open the receiver. A running receiver holds the shared SDR until stopped; switching pages does not interrupt it.

This is unreleased integration work. Tests use mocked processes; device and RF validation remains required before release.

## Tuning and regional choices

Start with manual tuning. The Netherlands preset library is opt-in example
content, not a default for every region; saved favorites are retained. FM
de-emphasis starts at 75 microseconds for US and 50 for EU_868, with explicit
selection for other regions. A saved `plugins.radio.deemphasis_us` takes
precedence. RDS additionally needs `redsea`; ordinary audio does not.
Stop the receiver before retuning. See [receiver regions](../../docs/PLUGINS.md#receiver-regions-and-local-channels).
