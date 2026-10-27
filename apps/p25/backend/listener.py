"""Optional OP25 process and bounded loopback audio bridge. Idle at creation."""
import asyncio
import shutil
import socket
import tempfile
import time
from collections import deque
from .settings import Settings, command
from src.audio import sdr_registry


class PCMReceiver(asyncio.DatagramProtocol):
    def __init__(self, queue):
        self.queue = queue

    def datagram_received(self, data, addr):
        # OP25 audio is 8 kHz signed 16-bit mono PCM. Ignore control datagrams.
        if len(data) <= 4 or len(data) % 2:
            return
        if self.queue.full():
            self.queue.get_nowait()
        self.queue.put_nowait(data)


class P25Listener:
    def __init__(self):
        self._lock = asyncio.Lock()
        self.decoder = self.encoder = None
        self.transport = self.directory = None
        self.tasks = []
        self.subscribers = set()
        self.settings = None
        self.error = ""
        self.logs = deque(maxlen=60)
        self.pcm = asyncio.Queue(maxsize=64)
        self.audio_bytes = 0
        self.last_poll = time.monotonic()

    @property
    def running(self):
        return all(p is not None and p.returncode is None for p in (self.decoder, self.encoder))

    def status(self):
        self.last_poll = time.monotonic()
        return {"running": self.running, "settings": self.settings.model_dump() if self.settings else None,
                "last_error": self.error, "logs": list(self.logs), "audio_bytes": self.audio_bytes,
                "dongle_owner": sdr_registry.current_owner(), "listeners": len(self.subscribers)}

    async def start(self, settings):
        if not isinstance(settings, Settings):
            settings = Settings.model_validate(settings)
        async with self._lock:
            if self.running:
                raise ValueError("Stop P25 before changing receiver settings")
            for name in ("meshpoint-op25", "ffmpeg"):
                if shutil.which(name) is None:
                    raise RuntimeError(f"{name} is missing; follow the P25 setup guide")
            sdr_registry.claim("p25")
            self.error = ""
            self.logs.clear()
            self.audio_bytes = 0
            self.settings = settings
            self.last_poll = time.monotonic()
            try:
                self.directory = tempfile.TemporaryDirectory(prefix="meshpoint-p25-")
                loop = asyncio.get_running_loop()
                self.pcm = asyncio.Queue(maxsize=64)
                self.transport, _ = await loop.create_datagram_endpoint(lambda: PCMReceiver(self.pcm), local_addr=("127.0.0.1", 0))
                audio_port = self.transport.get_extra_info("sockname")[1]
                with socket.socket() as reserve:
                    reserve.bind(("127.0.0.1", 0))
                    terminal_port = reserve.getsockname()[1]
                self.encoder = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "s16le", "-ar", "8000", "-ac", "1", "-i", "pipe:0",
                    "-c:a", "libmp3lame", "-b:a", "32k", "-f", "mp3", "-flush_packets", "1", "pipe:1",
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                self.decoder = await asyncio.create_subprocess_exec(
                    *command(settings, self.directory.name, audio_port, terminal_port),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
                self.tasks = [asyncio.create_task(self._feed()), asyncio.create_task(self._broadcast()),
                              asyncio.create_task(self._log(self.decoder)), asyncio.create_task(self._log(self.encoder))]
                await asyncio.sleep(1)
                if not self.running:
                    raise RuntimeError("OP25 or audio encoder exited during startup; check receiver diagnostics")
                self.tasks.append(asyncio.create_task(self._watch()))
            except BaseException:
                await self._cleanup()
                raise

    async def stop(self):
        async with self._lock:
            await self._cleanup()

    async def _cleanup(self):
        current = asyncio.current_task()
        tasks, self.tasks = self.tasks, []
        for task in tasks:
            if task is not current:
                task.cancel()
        await asyncio.gather(*(t for t in tasks if t is not current), return_exceptions=True)
        for proc in (self.decoder, self.encoder):
            if proc is not None and proc.returncode is None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), 4)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
        self.decoder = self.encoder = None
        if self.transport:
            self.transport.close()
            self.transport = None
        if self.directory:
            self.directory.cleanup()
            self.directory = None
        for queue in self.subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(b"")
        self.subscribers.clear()
        sdr_registry.release("p25")

    async def _feed(self):
        while True:
            data = await self.pcm.get()
            self.encoder.stdin.write(data)
            await self.encoder.stdin.drain()

    async def _broadcast(self):
        while data := await self.encoder.stdout.read(4096):
            self.audio_bytes += len(data)
            for queue in self.subscribers:
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(data)

    async def _log(self, proc):
        while line := await proc.stderr.readline():
            text = line.decode("utf-8", errors="replace").strip()[:500]
            if text:
                self.logs.append(text)

    async def _watch(self):
        while self.running:
            if any(t.done() and not t.cancelled() and t.exception() for t in self.tasks if t is not asyncio.current_task()):
                self.error = "Audio bridge failed; receiver stopped"
                break
            if not self.subscribers and time.monotonic() - self.last_poll > 600:
                self.error = "P25 stopped after ten minutes without a dashboard or audio listener"
                break
            await asyncio.sleep(1)
        if not self.error:
            self.error = "Receiver process exited; check diagnostics"
        await self.stop()

    def subscribe(self):
        queue = asyncio.Queue(maxsize=32)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue):
        self.subscribers.discard(queue)
