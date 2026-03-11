#!/usr/bin/env bash
# Reset the RAK2287 concentrator via GPIO pin.
# Called by systemd ExecStartPre (as root) before the service starts.
#
# RAK2287 Pi HAT uses ACTIVE HIGH reset on GPIO 17:
#   HIGH = assert reset (chip held in reset)
#   LOW  = release reset (chip runs)

GPIO_PIN="${1:-17}"

if command -v pinctrl &>/dev/null; then
    pinctrl set "$GPIO_PIN" op dh
    sleep 0.1
    pinctrl set "$GPIO_PIN" op dl
    sleep 0.1
    echo "Concentrator reset via pinctrl GPIO ${GPIO_PIN}"
elif command -v gpioset &>/dev/null; then
    gpioset gpiochip0 "${GPIO_PIN}=1"
    sleep 0.1
    gpioset gpiochip0 "${GPIO_PIN}=0"
    sleep 0.1
    echo "Concentrator reset via gpioset GPIO ${GPIO_PIN}"
else
    echo "WARNING: no GPIO tool found (pinctrl or gpioset)" >&2
    exit 1
fi
