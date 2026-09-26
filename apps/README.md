# Compatibility snapshot

Official plugin development has moved to
[KMX415/meshpoint-plugins](https://github.com/KMX415/meshpoint-plugins).

This tree remains for existing catalog pins and core regression tests. It is not
loaded automatically by Meshpoint. Installed plugins live alongside the device
database under `plugins/apps/` and retain their selected source and revision.

Submit new plugin changes to the dedicated repository. Coordinate compatibility
updates here when a core change requires updating regression fixtures. See
[the plugin guide](../docs/PLUGINS.md) for source selection and migration steps.
