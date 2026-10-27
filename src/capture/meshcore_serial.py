"""MeshCore serial transport with boot-control lines released after opening."""

import os


def create_serial_connection(port: str, baud_rate: int):
    """Keep DTR from holding a companion's boot button after USB connection.

    Import lazily so installations without the optional MeshCore dependency
    can still load capture modules. Keep the adjustment local to this transport.
    """
    from meshcore.serial_cx import SerialConnection
    from serial.tools import list_ports

    # Apply the verified workaround to CP210x USB bridges. Native USB CDC
    # devices can require asserted DTR; preserve their library behavior.
    selected = os.path.normcase(os.path.realpath(port))
    cp210x = any(
        item.vid == 0x10C4 and item.pid in (0xEA60, 0xEA70, 0xEA71)
        and os.path.normcase(os.path.realpath(item.device)) == selected
        for item in list_ports.comports()
    )
    if not cp210x:
        return SerialConnection(port, baud_rate, cx_dly=0.1)

    class ReleasedControlConnection(SerialConnection):
        class MCSerialClientProtocol(SerialConnection.MCSerialClientProtocol):
            def connection_made(self, transport):
                super().connection_made(transport)
                # The upstream protocol releases RTS but leaves PySerial's
                # default asserted DTR. On ESP32 USB bridges that can hold
                # BOOT and activate the firmware's startup rescue console.
                serial_port = getattr(transport, "serial", None)
                if serial_port is not None:
                    serial_port.dtr = False

    return ReleasedControlConnection(port, baud_rate, cx_dly=0.1)
