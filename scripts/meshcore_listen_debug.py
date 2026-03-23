"""Diagnostic: listen for ALL MeshCore events with debug logging.

Run on the Pi (stop meshpoint first):
  sudo systemctl stop meshpoint
  sudo /opt/meshpoint/venv/bin/python3 scripts/meshcore_listen_debug.py

Listens for 60 seconds and prints every event received.
"""

import asyncio
import logging
import sys

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("listen")

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
LISTEN_SECONDS = 60


async def main():
    from meshcore import MeshCore, EventType

    logger.info("Connecting to %s with debug=True ...", PORT)
    mc = await MeshCore.create_serial(PORT, 115200, debug=True)
    logger.info("Connected.")

    info = await mc.commands.send_device_query()
    if info.type == EventType.ERROR:
        logger.error("Device query failed: %s", info.payload)
    else:
        logger.info("Device: %s", info.payload)

    event_count = 0

    async def on_any(event):
        nonlocal event_count
        event_count += 1
        etype = event.type.value if hasattr(event.type, "value") else str(event.type)
        logger.info("EVENT #%d  type=%s  payload=%s", event_count, etype, event.payload)

    subscribed = []
    for et in EventType:
        try:
            sub = mc.subscribe(et, on_any)
            subscribed.append(sub)
        except Exception:
            pass

    logger.info("Subscribed to %d event types. Listening for %ds ...", len(subscribed), LISTEN_SECONDS)
    logger.info(">>> Send a message from your PC now <<<")

    await mc.start_auto_message_fetching()

    await asyncio.sleep(LISTEN_SECONDS)

    await mc.stop_auto_message_fetching()
    for sub in subscribed:
        mc.unsubscribe(sub)
    await mc.disconnect()
    logger.info("Done. Received %d events total.", event_count)


asyncio.run(main())
