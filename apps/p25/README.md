# P25 integration candidate

Optional Meshpoint adapter for [boatbod OP25](https://github.com/boatbod/op25).
This is new Meshpoint integration code. OP25 is separately installed, not bundled.
The module is under development and has not passed native receiver validation.

Install and enable RTL-SDR Hub alongside P25. OP25/GNU Radio and FFmpeg with
libmp3lame are native dependencies outside the Meshpoint Python environment.
The dashboard does not run downloaded installers or automatically open hardware.

## Native dependency contract

Build a reviewed OP25 revision using its instructions for your OS. An executable
named `meshpoint-op25` must be on the Meshpoint service PATH. It must change to
the installed OP25 apps directory and exec rx.py, forwarding all arguments.
Using exec is required so stopping the receiver terminates the decoder.

Example wrapper, with the checkout path adjusted to the actual installation:

```sh
#!/bin/sh
cd /opt/op25/op25/gr-op25_repeater/apps || exit 1
exec ./rx.py "$@"
```

Check `meshpoint-op25 --help` and `ffmpeg -encoders` as the service user before
enabling. Executable discovery alone does not establish working native libraries
or USB access. See the [upstream CLI contract](https://github.com/boatbod/op25/blob/master/op25/gr-op25_repeater/apps/README.md).

## Candidate behavior

The page accepts an explicit control-channel list, decimal NAC, talkgroup list,
modulation, gain, PPM correction and receiver index. No local frequencies are
prefilled. A blank trunked talkgroup list follows all groups. Stop before editing.
The last successful form is retained in this browser; reception never autostarts.

Start P25 launches the receiver; Play audio opens the authenticated audio stream.
Diagnostics distinguish an alive process from actual decoded audio. Hiding the
page stops browser playback. A receiver with no polling or audio subscribers
stops after ten minutes. Shared SDR ownership prevents another plugin from
being silently interrupted. This first adapter targets one system and one SDR.

## Outstanding validation

Implementation review, including OP25 encrypted-call handling, is incomplete.
The catalog entry and source files are a development draft. No native decoder has
been installed, no P25 receiver has been started, and no hardware reception is
claimed. Conventional-mode restrictions, failure-path tests, browser controls,
Phase I/II voice, trunk tracking and sustained Pi performance remain to validate.
