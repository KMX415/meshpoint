`F38f
 __  __ _____ ____  _   _ ____   ___ ___ _   _ _____
|  \/  | ____/ ___|| | | |  _ \ / _ \_ _| \ | |_   _|
| |\/| |  _| \___ \| |_| | |_) | | | | ||  \| | | |
| |  | | |___ ___) |  _  |  __/| |_| | || |\  | | |
|_|  |_|_____|____/|_| |_|_|    \___/___|_| \_| |_|
`f
`F38f`!TechInc Mesh BBS`!`f  `F888//`f  `!About Meshpoint`!
========================================================

>What it is

`*Meshpoint`* is an edge radio + mesh gateway with a web
dashboard. It runs on a Raspberry Pi, listens on real hardware
an 868 MHz LoRa concentrator, an RNode, and a cheap RTL-SDR
dongle and decodes what it hears, stores it, and serves it up
locally. No cloud, no account, no phone-home. One install
script, then it just sits there and listens.

>LoRa mesh

`F888Meshtastic `f: node roster, positions on a map, telemetry,
             DM + channel messaging
`F888MeshCore   `f: node roster, positions on a map, telemetry,
             DM + channel messaging
`F888LoRaWAN    `f: uplink frames, decrypted with your own keys,
             device roster

>Talk back

It is not just a sniffer. From the dashboard you can:

`F888Chat     `f: send on Meshtastic channels + DMs, and message
             MeshCore nodes
`F888Relay    `f: repeat/forward traffic through a USB companion
`F888MQTT     `f: bridge Meshtastic traffic to/from a broker
`F888Meshradar `f: optionally push to meshradar.io for pooled,
             multi-site mesh intelligence

>Reticulum / LXMF

`*Meshpoint`* attaches to a local `*rnsd`* as a client: an LXMF
inbox, a peer roster built from announces, a NomadNet browser,
and when node hosting is on this very BBS. All on one
identity: browse it and message it on the same hash.

>RTL-SDR -- one $30 dongle, a lot of bands

`F888FM / AM radio `f: browser tuner with RDS (station name,
                RadioText, signal meter)
`F888DAB+         `f: digital radio -- channel scan + playback
`F888POCSAG pagers `f: 512 / 1200 / 2400 baud pager decode
`F888DAPNET       `f: amateur-radio paging network
`F888P2000        `f: NL emergency services (FLEX, 169 MHz)
`F888RTL433       `f: 433 MHz ISM -- weather stations, sensors,
                TPMS, doorbells, whatever is chirping
`F888ADS-B        `f: aircraft table + live map (1090 MHz)
`F888ACARS        `f: aircraft VHF datalink messages

Only one RTL-SDR mode runs at a time -- they share the dongle.

>RF environment

A spectrum sweep across the RTL-SDR's range -- a quick "what is
loud right now" view, and a noise-floor trace on the dashboard.
Thru LoRa concentrator or a attached companion.

>Flash companions

Plug an ESP32 board into the Pi's USB and flash it from the
dashboard -- no laptop, no cables to a workstation:

`F888Meshtastic `f: latest release, straight onto a stick
`F888MeshCore   `f: same, for MeshCore companions
`F888RNode      `f: RNode firmware for a Reticulum radio
`F888Companions `f: the POCSAG pager, Reticulum-node and
             RF-environment helper sketches

It reads the board's current version over serial and checks it
against the newest release on GitHub before you flash.

>The dashboard

Per-protocol pages, a live map, a mesh topology graph, a
MeshCore repeater view, packet stats + traffic graphs, a real
terminal, and a plugin system -- every radio mode above is a
plugin you enable per node.

>Open source

`!Meshpoint`! is free software under the `!GNU AGPL v3`!,
developed in the open on GitHub, and installs on Raspberry Pi
OS from a single script. Run it, study it, fork it -- if you
run a changed version that others use, share those changes back.

`F888Source `f: `[github.com/KMX415/meshpoint`https://github.com/KMX415/meshpoint]
`F888Stats  `f: `[this node's live numbers`:/page/info.mu]

-
`[<< Main menu`:/page/index.mu]     `[Get on the mesh >>`:/page/mesh.mu]
