"""Serialize access to libloragw's process-global state and native TX."""
import ctypes
from functools import wraps
import logging
import threading
import time

logger = logging.getLogger(__name__)
HAL_LOCK = threading.RLock()
TX_LOCK = threading.Lock()
TX_FREE = 2
TX_SCHEDULED = 3
TX_EMITTING = 4
POLL_SECONDS = 0.01
BUSY_TIMEOUT_SECONDS = 10.0


def serialized_hal(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with HAL_LOCK:
            return method(self, *args, **kwargs)
    return call


def send_immediate(wrapper, packet):
    """Wait for a free transmitter, send, and wait for bounded completion.

    Keep TX ownership across airtime, but release HAL_LOCK between polls so
    receive can continue. The lock also survives cancellation of to_thread's
    awaiter: the worker retains ownership until it returns.
    """
    if not TX_LOCK.acquire(timeout=BUSY_TIMEOUT_SECONDS):
        logger.error("Native TX queue wait timed out")
        return -1
    try:
        deadline = time.monotonic() + BUSY_TIMEOUT_SECONDS
        while True:
            with HAL_LOCK:
                if not wrapper._started:
                    raise RuntimeError("Concentrator not started, cannot transmit")
                state = wrapper.get_tx_status(packet.rf_chain)
                if state == TX_FREE:
                    airtime = wrapper.get_time_on_air(packet) / 1000.0
                    if airtime <= 0:
                        raise RuntimeError("HAL returned invalid TX airtime")
                    result = wrapper._lib.lgw_send(ctypes.byref(packet))
                    if result != 0:
                        return result
                    generation = wrapper._generation
                    started = time.monotonic()
                    break
                if state not in (TX_EMITTING, TX_SCHEDULED):
                    raise RuntimeError("Transmitter is unavailable")
            if time.monotonic() >= deadline:
                raise TimeoutError("Transmitter remained busy")
            time.sleep(POLL_SECONDS)

        deadline = started + airtime + 2.0
        saw_emitting = False
        while True:
            with HAL_LOCK:
                if not wrapper._started or wrapper._generation != generation:
                    raise RuntimeError("Concentrator stopped or restarted during transmission")
                state = wrapper.get_tx_status(packet.rf_chain)
            saw_emitting |= state == TX_EMITTING
            elapsed = time.monotonic() - started
            # A short packet can complete between polls. Never mistake the
            # initial FREE status immediately after lgw_send for completion.
            if state == TX_FREE and (saw_emitting or elapsed >= airtime):
                return 0
            if state not in (TX_FREE, TX_EMITTING, TX_SCHEDULED):
                raise RuntimeError("Transmitter became unavailable")
            if time.monotonic() >= deadline:
                raise TimeoutError("Transmission completion timed out")
            time.sleep(POLL_SECONDS)
    except (RuntimeError, TimeoutError):
        logger.exception("Native transmission did not complete")
        return -1
    finally:
        TX_LOCK.release()
