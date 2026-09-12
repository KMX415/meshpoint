"""RTL-SDR plugin -- entry point.

Nothing to register: this plugin only provides "sidebar" (a top-level
dashboard page), which is wired declaratively through plugin.toml's
[sidebar] table + its frontend script, not through PluginRegistry (there's
no reg.add_sidebar() -- see docs/PLUGINS.md). register() still has to
exist and be callable, but has nothing to do.
"""

from __future__ import annotations


def register(reg) -> None:
    pass
