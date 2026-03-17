#!/usr/bin/env bash
# Reset the RAK2287/WM1302 concentrator via GPIO.
#
# Different carrier boards route the SX1302 reset to different pins:
#   GPIO 17 — some RAK Pi HAT revisions
#   GPIO 25 — other RAK Pi HAT revisions
# Both pins are toggled to ensure reset works on any board.
# Asserting reset on an unconnected pin is harmless.
#
# ACTIVE HIGH reset: HIGH = chip held in reset, LOW = chip runs.
#
# Usage:
#   reset_concentrator.sh          Full cycle (assert + release) -- ExecStartPre
#   reset_concentrator.sh --hold   Assert reset and hold -- ExecStopPost

RESET_PINS="${RESET_GPIO:-17 25}"
HOLD_MODE=false

for arg in "$@"; do
    case "$arg" in
        --hold) HOLD_MODE=true ;;
    esac
done

if command -v pinctrl &>/dev/null; then
    GPIO_CMD="pinctrl"
    _pin_high() { pinctrl set "$1" op dh; }
    _pin_low()  { pinctrl set "$1" op dl; }
elif command -v gpioset &>/dev/null; then
    GPIO_CMD="gpioset"
    _pin_high() { gpioset gpiochip0 "$1=1"; }
    _pin_low()  { gpioset gpiochip0 "$1=0"; }
else
    echo "WARNING: no GPIO tool found (pinctrl or gpioset)" >&2
    exit 1
fi

for pin in $RESET_PINS; do
    _pin_high "$pin"
done
sleep 0.5

if [ "$HOLD_MODE" = true ]; then
    echo "Concentrator held in reset via ${GPIO_CMD} GPIO [${RESET_PINS}]"
else
    for pin in $RESET_PINS; do
        _pin_low "$pin"
    done
    sleep 0.5
    echo "Concentrator reset via ${GPIO_CMD} GPIO [${RESET_PINS}]"
fi
