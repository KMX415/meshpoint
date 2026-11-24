"""Validated OP25 receiver settings and generated trunk configuration."""
import csv
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    mode: Literal["trunked", "conventional"] = "trunked"
    name: str = Field("Local P25 system", min_length=1, max_length=80)
    frequencies: list[float] = Field(min_length=1, max_length=32)
    talkgroups: list[int] = Field(default_factory=list, max_length=256)
    nac: int = Field(0, ge=0, le=4095)
    phase2: bool = True
    tdma_control: bool = False
    modulation: Literal["cqpsk", "fsk4"] = "cqpsk"
    gain: int = Field(30, ge=0, le=50)
    ppm: int = Field(0, ge=-200, le=200)
    device: int = Field(0, ge=0, le=15)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if any(ord(c) < 32 for c in value):
            raise ValueError("System name cannot contain control characters")
        return value

    @field_validator("frequencies")
    @classmethod
    def valid_frequencies(cls, values):
        if any(not 24 <= f <= 1766 for f in values):
            raise ValueError("Receive frequencies must be between 24 and 1766 MHz")
        return list(dict.fromkeys(values))

    @field_validator("talkgroups")
    @classmethod
    def valid_talkgroups(cls, values):
        if any(not 1 <= t <= 65534 for t in values):
            raise ValueError("Talkgroups must be between 1 and 65534")
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def conventional_limits(self):
        if self.mode == "conventional" and (len(self.frequencies) != 1 or self.talkgroups or self.tdma_control):
            raise ValueError("Conventional mode uses one frequency without trunk talkgroup filtering or a TDMA control channel")
        return self


def command(settings, directory, audio_port, terminal_port):
    """No shell interpolation or arbitrary user-supplied OP25 arguments."""
    args = ["meshpoint-op25", "--args", f"rtl={settings.device}", "-N", f"LNA:{settings.gain}",
            "-q", str(settings.ppm), "-S", "1000000", "-f", str(round(settings.frequencies[0] * 1e6)),
            "-D", settings.modulation, "-w", "-W", "127.0.0.1", "-u", str(audio_port),
            "-l", f"http:127.0.0.1:{terminal_port}", "--crypt-behavior", "2", "-v", "1"]
    if settings.phase2:
        args.append("-2")
    if settings.tdma_control:
        args.append("--tdma-cc")
    if settings.mode == "trunked":
        directory = Path(directory)
        whitelist = directory / "talkgroups.tsv"
        whitelist.write_text("".join(f"{t}\n" for t in settings.talkgroups), encoding="utf-8")
        path = directory / "trunk.tsv"
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output, delimiter="\t", quoting=csv.QUOTE_ALL)
            writer.writerow(["Sysname", "Control Channel List", "Offset", "NAC", "Modulation", "TGID Tags File", "Whitelist", "Blacklist", "Center Frequency"])
            writer.writerow([settings.name, ",".join(str(f) for f in settings.frequencies), 0, hex(settings.nac), settings.modulation, "", str(whitelist) if settings.talkgroups else "", "", ""])
        args.extend(["-T", str(path)])
    return args
