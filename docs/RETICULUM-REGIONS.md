# Reticulum regional starting profiles

Reticulum uses Meshpoint's configured `radio.region` to fill missing RNode
settings. It does not copy the existing Meshtastic or MeshCore radio settings.
The RNode is a separate radio and its peer must use matching on-air settings.

| Meshpoint region | Center frequency | Bandwidth | SF | Coding rate | Initial power |
|---|---:|---:|---:|---:|---:|
| US | 915.000 MHz | 500 kHz | 7 | 4/5 | 7 dBm |
| EU_868 | 869.525 MHz | 125 kHz | 7 | 4/5 | 7 dBm |
| ANZ | 916.000 MHz | 500 kHz | 7 | 4/5 | 7 dBm |
| IN | 866.000 MHz | 125 kHz | 7 | 4/5 | 7 dBm |
| KR | 921.900 MHz | 125 kHz | 7 | 4/5 | 7 dBm |
| SG_923 | 923.000 MHz | 125 kHz | 7 | 4/5 | 7 dBm |

These are Meshpoint starting profiles for initial testing, not official
Reticulum channels, regional maximum-power settings or certified operating
plans. They do not establish permission to transmit. Hardware band support,
antenna gain, equipment approval, actual occupied bandwidth, channel access
and national restrictions still need checking. ANZ is a shared application
label; Australia and New Zealand have separate rules. Other countries must
not infer compatibility from a nearby country's profile.

The initial airtime budgets are 10% over approximately 15 seconds and 1%
over a rolling hour, enforced by RNode. These are configurable traffic limits,
not universal legal duty-cycle limits. Some uses require tighter limits or
specific access mechanisms that these two settings alone do not implement.

## Saved settings and region changes

For complete installation and first-message instructions, see the
[Reticulum guide](../apps/reticulum/README.md). A physical two-RNode LXMF test
has passed for a US setup; that does not establish validation of
all profiles or replace the limitations above.

- Every explicitly saved radio parameter is retained, including zero TX power.
  Existing manual frequencies are never silently moved to another channel.
- The settings page identifies the device region. **Use region starting
  profile** copies that region's values into the form. Review and save them;
  the button does not enable RF or change other plugin settings.
- Saving freezes the selected values. Changing the device region later does
  not retune those saved values. Reapply a profile or enter matching values
  explicitly when relocating a radio.
- An unknown region has no default frequency. The plugin can still run with
  RF disabled; enabling RNode requires an explicit frequency.
- Blank airtime limits resolve to the known region's starting limits. For an
  unknown region, blank leaves that limit unspecified.
- RF and backbone remain disabled until the operator enables them. Restart
  Meshpoint after saving interface changes.

## References and scope

Reviewed 2026-09-11. The profile frequencies are selected by Meshpoint inside
the relevant band ranges; the sources below do not endorse this table as a
complete compliant Reticulum setup.

- [Reticulum interface parameters and airtime limits](https://reticulum.network/manual/interfaces.html#rnode-lora-interface).
- [US FCC section 15.247](https://www.govinfo.gov/content/pkg/CFR-2025-title47-vol1/pdf/CFR-2025-title47-vol1-sec15-247.pdf): the digital-modulation provisions require at least 500 kHz measured 6 dB bandwidth. Selecting nominal 500 kHz does not prove compliance. The frequency-hopping dwell-time provisions are not a blanket rule for fixed-frequency LoRa.
- [CEPT Report 85](https://docdb.cept.org/download/4444): European SRD band harmonisation; national implementation and application-specific conditions still apply.
- [Australia LIPD Class Licence 2025](https://www.legislation.gov.au/F2025L01047/asmade/2025-09-05/text/original/pdf) and [New Zealand SRD general user licence](https://www.rsm.govt.nz/licensing/frequencies-for-anyone/short-range-devices-gurl).
- [India Department of Telecommunications subordinate legislation](https://www.dot.gov.in/static/uploads/2025/07/84f33f09e137fa81930f44bcd5f2d238.pdf): includes short-range-device provisions for 865-868 MHz; applicable device category matters.
- [Korean RRA USN equipment classification](https://www.rra.go.kr/ko/license/A_b_popup_keyno.do?key_no=R-R-HCk-HC03RFM-1): band classification only, not approval of this Heltec/firmware or profile.
- [Singapore IMDA radio equipment standards](https://www.imda.gov.sg/regulations-and-licensing-listing/ict-standards-and-quality-of-service/telecommunication-and-security-standards/radio-communication-equipment-standards): consult the current SRD specification and applicable application category.
