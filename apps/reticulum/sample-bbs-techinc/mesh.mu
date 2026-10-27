`F38f`!TechInc Mesh BBS`!`f  `F888//`f  `!Get on the mesh`!
========================================================

>What this node does

This node runs `*Meshpoint`* on a RAK V2 (RAK2287 + Raspberry Pi)
at TechInc. It listens on a single 868 MHz LoRa concentrator plus
an RNode, captures and relays several mesh protocols at once, and
hosts this NomadNet page on the `!same identity`! as its LXMF
address.

>Frequencies

`F888Meshtastic  `f: 869.525 MHz   preset LongFast
`F888MeshCore    `f: 869.618 MHz
`F888Reticulum   `f: 869.463 MHz   (RNode, plus a TCP backbone)
#`F888POCSAG/pager `f: 869.4625 MHz  (DAPNET / P2000 monitoring)

>Reach this node

`F888Browse `f: you are already here -- bookmark this node's hash
`F888LXMF   `f: message the same hash from Sideband / MeshChat /
          NomadNet; it lands in Meshpoint's inbox
`F888Stats  `f: `[live node + mesh stats`:/page/info.mu]

>Want your own Reticulum node?

Grab an RNode (or run rnsd over TCP), point it at the same band,
and announce. Meshpoint, NomadNet and Sideband all speak plain
Reticulum -- no accounts, no servers.

`F888Reticulum `f: `[reticulum.network`https://reticulum.network]
`F888NomadNet  `f: `[github.com/markqvist/NomadNet`https://github.com/markqvist/NomadNet]
`F888Sideband  `f: `[unsigned.io/sideband`https://unsigned.io/sideband]

-
`[<< Main menu`:/page/index.mu]     `[Other nodes & links >>`:/page/links.mu]
