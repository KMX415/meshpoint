# rtlsdr

Optional Meshpoint receiver plugin, adapted from javastraat/meshpoint at `b18d6742de6c4cf7fb2e743c690400bea5790a9f`. Original author: Einstein PD2EMC.

This folder is catalog source, not an installed or enabled module. Install only the modules you want through Settings > Plugins. This module supplies the host page for receiver tabs. Install and enable the desired child modules separately. Restart after enabling.

Required commands: none for the host page itself. Install the documented native tools on the device before enabling this module. Setup does not run automatically. See [the optional plugin guide](../../docs/PLUGINS.md) for package availability, setup limitations, hardware sharing, and removal.

The host page itself does not start a decoder. Use Start on the selected receiver tab after installing its dependencies. One receiver holds the shared SDR reservation until stopped; switching pages does not interrupt it. Command detection and native hardware validation are separate checks.

This is unreleased integration work. Tests use mocked processes; device and RF validation remains required before release.
