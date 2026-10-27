"""MeshCore USB reconnect on command timeout (javastraat port).

Credit: javastraat/meshpoint b04e91c / c1bc3b8
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.transmit.meshcore_tx_client import MeshCoreTxClient, SendResult


class TestReconnectReentrancyGuard(unittest.IsolatedAsyncioTestCase):
    """_reconnect_in_progress serializes health vs timeout reconnects."""

    def test_serial_open_releases_boot_line_without_global_library_patch(self):
        from types import SimpleNamespace
        from src.capture.meshcore_serial import create_serial_connection

        class BaseConnection:
            def __init__(self, port, baudrate, cx_dly):
                self.port, self.baudrate, self.cx_dly = port, baudrate, cx_dly

            class MCSerialClientProtocol:
                def connection_made(self, transport):
                    transport.serial.rts = False
                    transport.base_called = True

        with patch.dict("sys.modules", {
            "meshcore.serial_cx": SimpleNamespace(SerialConnection=BaseConnection),
        }):
            for port in ["/dev/ttyACM7", "/dev/serial/by-id/selected-node", "COM12"]:
                with patch("serial.tools.list_ports.comports", return_value=[
                    SimpleNamespace(device=port, vid=0x10C4, pid=0xEA60),
                ]):
                    connection = create_serial_connection(port, 115200)
                transport = SimpleNamespace(serial=SimpleNamespace(rts=True, dtr=True))
                connection.MCSerialClientProtocol().connection_made(transport)
                self.assertTrue(transport.base_called)
                self.assertFalse(transport.serial.rts)
                self.assertFalse(transport.serial.dtr)
                self.assertEqual(connection.port, port)
            original = SimpleNamespace(serial=SimpleNamespace(rts=True, dtr=True))
            BaseConnection.MCSerialClientProtocol().connection_made(original)
            self.assertTrue(original.serial.dtr)
            with patch("serial.tools.list_ports.comports", return_value=[
                SimpleNamespace(device="COM12", vid=0x303A, pid=0x1001),
            ]):
                native = create_serial_connection("COM12", 115200)
            self.assertIs(type(native), BaseConnection)

    async def test_repeated_fetch_restarts_keep_one_subscription(self):
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource
        source = MeshcoreUsbCaptureSource()
        source._connected = True
        subscriptions = 1

        async def stop():
            nonlocal subscriptions
            subscriptions = 0
            await asyncio.sleep(0)

        async def start():
            nonlocal subscriptions
            subscriptions += 1
            self.assertEqual(subscriptions, 1)

        source._meshcore = MagicMock()
        source._meshcore.stop_auto_message_fetching = AsyncMock(side_effect=stop)
        source._meshcore.start_auto_message_fetching = AsyncMock(side_effect=start)
        await asyncio.gather(*(source.restart_auto_fetching() for _ in range(4)))
        self.assertEqual(subscriptions, 1)

    async def test_health_waits_for_tx_and_pauses_fetching(self):
        from types import SimpleNamespace
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource
        source = MeshcoreUsbCaptureSource()
        source._connected = True
        source._meshcore = MagicMock()
        mc = source._meshcore
        order = []

        async def stop():
            order.append("stop")

        async def query():
            self.assertTrue(source._command_lock.locked())
            self.assertEqual(order[-1], "stop")
            order.append("query")
            return SimpleNamespace(type="info")

        async def start():
            order.append("start")

        mc.stop_auto_message_fetching = AsyncMock(side_effect=stop)
        mc.start_auto_message_fetching = AsyncMock(side_effect=start)
        mc.commands.send_device_query = AsyncMock(side_effect=query)
        client = MeshCoreTxClient()
        client.set_source(source)
        self.assertIs(source._command_lock, client._cmd_lock)
        with patch.dict("sys.modules", {"meshcore": SimpleNamespace(
            EventType=SimpleNamespace(ERROR="error", DEVICE_INFO="info"),
        )}):
            async with client._cmd_lock:
                task = asyncio.create_task(source._check_health())
                await asyncio.sleep(0)
                mc.commands.send_device_query.assert_not_awaited()
            self.assertTrue(await task)
        self.assertEqual(order, ["stop", "query", "stop", "start"])

    async def test_failed_connects_clean_up_owned_dispatcher_tasks(self):
        from types import SimpleNamespace
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource

        tasks = []
        instances = []

        class FailedConnection:
            def __init__(self, *args, **kwargs):
                self.task = None
                self.stop_auto_message_fetching = AsyncMock()
                instances.append(self)

            async def connect(self):
                self.task = asyncio.create_task(asyncio.Event().wait())
                tasks.append(self.task)
                await asyncio.sleep(0)
                raise OSError(5, "Input/output error")

            async def disconnect(self):
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    pass

        source = MeshcoreUsbCaptureSource()
        with patch.dict("sys.modules", {
            "meshcore": SimpleNamespace(MeshCore=FailedConnection, EventType=MagicMock()),
            "src.capture.meshcore_serial": SimpleNamespace(create_serial_connection=MagicMock()),
        }):
            for port in ["/dev/ttyACM7", "/dev/serial/by-id/another-radio", "COM12"]:
                with self.assertLogs("src.capture.meshcore_usb_source", level="WARNING") as logs:
                    await source._connect(port)
                self.assertFalse(source.connected)
                self.assertIsNone(source._meshcore)
                self.assertTrue(tasks[-1].done())
                self.assertIsNone(logs.records[-1].exc_info)
        self.assertEqual(len(instances), 3)

    async def test_cancelled_handshake_cleans_up_and_propagates_cancellation(self):
        from types import SimpleNamespace
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource

        instance = MagicMock()
        instance.connect = AsyncMock(side_effect=asyncio.CancelledError)
        instance.stop_auto_message_fetching = AsyncMock()
        instance.disconnect = AsyncMock()
        source = MeshcoreUsbCaptureSource()
        with patch.dict("sys.modules", {
            "meshcore": SimpleNamespace(MeshCore=MagicMock(return_value=instance), EventType=MagicMock()),
            "src.capture.meshcore_serial": SimpleNamespace(create_serial_connection=MagicMock()),
        }):
            with self.assertRaises(asyncio.CancelledError):
                await source._connect("/dev/serial/by-path/selected-radio")
        instance.disconnect.assert_awaited_once()
        self.assertFalse(source.connected)
        self.assertIsNone(source._meshcore)

    async def test_disconnect_event_marks_offline_without_counting_as_activity(self):
        from types import SimpleNamespace
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource
        source = MeshcoreUsbCaptureSource()
        source._running = source._connected = True
        source._last_event_at = 123.0
        source._reconnect_until_connected = AsyncMock()
        event = SimpleNamespace(type=SimpleNamespace(name="DISCONNECTED", value="disconnected"))
        await source._on_event(event)
        await source._on_event(event)
        self.assertFalse(source.connected)
        self.assertEqual(source._last_event_at, 123.0)
        self.assertTrue(source._queue.empty())
        await source._reconnect_task
        source._reconnect_until_connected.assert_awaited_once()

    async def test_missing_usb_node_starts_recovery_without_active_probe(self):
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource
        source = MeshcoreUsbCaptureSource()
        source._running = source._connected = True
        source._resolved_port = "/dev/serial/by-path/test-companion"
        source._reconnect_until_connected = AsyncMock()
        source._check_health = AsyncMock()
        with patch("src.capture.meshcore_usb_source.os.name", "posix"), patch(
            "src.capture.meshcore_usb_source.os.path.exists", return_value=False,
        ):
            source._check_usb_presence()
            source._check_usb_presence()
        self.assertFalse(source.connected)
        await source._reconnect_task
        source._reconnect_until_connected.assert_awaited_once()
        source._check_health.assert_not_awaited()

    async def test_existing_device_is_not_reset_by_presence_check(self):
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource
        source = MeshcoreUsbCaptureSource()
        source._connected = True
        source._resolved_port = "/dev/test-companion"
        source._trigger_reconnect = MagicMock()
        with patch("src.capture.meshcore_usb_source.os.name", "posix"), patch(
            "src.capture.meshcore_usb_source.os.path.exists", return_value=True,
        ):
            source._check_usb_presence()
        self.assertTrue(source.connected)
        source._trigger_reconnect.assert_not_called()

    async def test_reconnect_no_ops_while_already_in_progress(self):
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource

        source = MeshcoreUsbCaptureSource(
            serial_port="/dev/ttyFAKE", auto_detect=False
        )
        source._reconnect_in_progress = True
        source._disconnect = AsyncMock()  # type: ignore[method-assign]

        await source._reconnect()

        source._disconnect.assert_not_called()

    async def test_flag_is_set_during_and_cleared_after_a_real_run(self):
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource

        source = MeshcoreUsbCaptureSource(
            serial_port="/dev/ttyFAKE", auto_detect=False
        )
        source._running = True
        source._resolved_port = "/dev/ttyFAKE"
        flag_during_connect = None

        async def fake_disconnect():
            return None

        async def fake_connect(port):
            nonlocal flag_during_connect
            flag_during_connect = source._reconnect_in_progress
            source._connected = True

        source._disconnect = fake_disconnect  # type: ignore[method-assign]
        source._connect = fake_connect  # type: ignore[assignment]

        self.assertFalse(source._reconnect_in_progress)
        with patch(
            "src.capture.meshcore_usb_source.asyncio.sleep", AsyncMock()
        ):
            await source._reconnect()

        self.assertTrue(flag_during_connect)
        self.assertFalse(source._reconnect_in_progress)

    async def test_flag_clears_even_if_reconnect_raises(self):
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource

        source = MeshcoreUsbCaptureSource(
            serial_port="/dev/ttyFAKE", auto_detect=False
        )

        async def raise_disconnect():
            raise RuntimeError("boom")

        source._disconnect = raise_disconnect  # type: ignore[method-assign]

        with self.assertRaises(RuntimeError):
            await source._reconnect()

        self.assertFalse(source._reconnect_in_progress)

    async def test_trigger_reconnect_skips_when_already_in_progress(self):
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource

        source = MeshcoreUsbCaptureSource(
            serial_port="/dev/ttyFAKE", auto_detect=False
        )
        source._connected = True
        source._reconnect_in_progress = True

        async def fake_health_loop():
            await asyncio.sleep(60)

        source._health_task = asyncio.create_task(fake_health_loop())

        try:
            source._trigger_reconnect("some command timed out")
            self.assertIsNotNone(source._health_task)
            self.assertFalse(source._health_task.done())
            self.assertIsNone(source._reconnect_task)
            self.assertTrue(source._connected)
        finally:
            source._health_task.cancel()
            try:
                await source._health_task
            except asyncio.CancelledError:
                pass


class TestTxClientTimeoutTriggersReconnect(unittest.IsolatedAsyncioTestCase):
    """TxClient command timeouts kick the bound USB source."""

    async def test_set_name_timeout_sets_timed_out_and_triggers(self):
        client = MeshCoreTxClient()
        source = MagicMock()
        source._connected = True
        source._meshcore = MagicMock()
        source._meshcore.commands.set_name = AsyncMock()
        source._meshcore.self_info = {"name": "old-name"}
        source._trigger_reconnect = MagicMock()
        client.set_source(source)

        meshcore_mod = MagicMock()
        meshcore_mod.EventType = MagicMock()

        async def raise_timeout(coro, *_args, **_kwargs):
            if hasattr(coro, "close"):
                coro.close()
            raise asyncio.TimeoutError()

        with patch.dict("sys.modules", {"meshcore": meshcore_mod}):
            with patch(
                "src.transmit.meshcore_tx_client.asyncio.wait_for",
                side_effect=raise_timeout,
            ):
                result = await client.set_companion_name("Mesh Lab East")

        self.assertFalse(result.success)
        self.assertTrue(result.timed_out)
        source._trigger_reconnect.assert_called_once_with("set_name timed out")
        self.assertEqual(source._meshcore.self_info["name"], "old-name")

    async def test_channel_send_timeout_triggers(self):
        client = MeshCoreTxClient()
        source = MagicMock()
        source._connected = True
        source._meshcore = MagicMock()
        source._meshcore.commands.send_chan_msg = AsyncMock()
        source._trigger_reconnect = MagicMock()
        client.set_source(source)

        async def raise_timeout(coro, *_args, **_kwargs):
            if hasattr(coro, "close"):
                coro.close()
            raise asyncio.TimeoutError()

        with patch(
            "src.transmit.meshcore_tx_client.asyncio.wait_for",
            side_effect=raise_timeout,
        ):
            result = await client.send_channel_message(0, "hi")

        self.assertTrue(result.timed_out)
        source._trigger_reconnect.assert_called_once_with("Send timed out")

    async def test_firmware_error_does_not_set_timed_out(self):
        result = SendResult(success=False, error="rejected", timed_out=False)
        self.assertFalse(result.timed_out)

    async def test_set_radio_success_triggers_reconnect(self):
        from src.transmit.meshcore_exclusive_radio import (
            MeshcoreExclusiveRadioApply,
        )

        client = MeshCoreTxClient()
        source = MagicMock()
        source._connected = True
        source._meshcore = MagicMock()
        client.set_source(source)

        with patch.object(
            MeshcoreExclusiveRadioApply,
            "apply_via_source",
            new=AsyncMock(
                return_value=SendResult(success=True, event_type="set_radio")
            ),
        ) as apply:
            result = await client.set_radio_params(910.525, 62.5, 7, 5)

        self.assertTrue(result.success)
        apply.assert_awaited_once()



if __name__ == "__main__":
    unittest.main()
