"""CPU sampling must be independent of request volume and cleaned up on exit."""

import asyncio
import unittest
from unittest.mock import patch

from src.system_metrics import CpuSampler, cpu_sampler
from src.api.routes.system_metrics import system_metrics
from src.remote.executors import execute_get_metrics


class CpuSamplerTests(unittest.IsolatedAsyncioTestCase):
    async def test_discards_prime_and_publishes_periodic_samples(self):
        sampler = CpuSampler()
        observed = []

        async def tick(interval):
            self.assertEqual(interval, 2.0)
            observed.append(sampler.value)
            if len(observed) == 3:
                raise asyncio.CancelledError

        with patch("psutil.cpu_percent", side_effect=[99, 12, 4]) as read:
            with patch("src.system_metrics.asyncio.sleep", side_effect=tick):
                with self.assertRaises(asyncio.CancelledError):
                    await sampler._sample()
        self.assertEqual(observed, [None, 12, 4])
        self.assertEqual(read.call_count, 3)
        for call in read.call_args_list:
            self.assertEqual(call.kwargs, {"interval": None})

    async def test_failure_clears_cache_and_reprimes_before_recovery(self):
        sampler = CpuSampler()
        observed = []

        async def tick(_interval):
            observed.append(sampler.value)
            if len(observed) == 5:
                raise asyncio.CancelledError

        with patch("psutil.cpu_percent", side_effect=[0, 12, OSError("unavailable"), 99, 6]):
            with patch("src.system_metrics.asyncio.sleep", side_effect=tick):
                with self.assertLogs("src.system_metrics", level="ERROR"):
                    with self.assertRaises(asyncio.CancelledError):
                        await sampler._sample()
        self.assertEqual(observed, [None, 12, None, None, 6])

    async def test_lifecycle_cancels_sampler_and_resets_cache_on_each_exit(self):
        sampler = CpuSampler()
        for fail in (False, True):
            entered = asyncio.Event()
            cancelled = asyncio.Event()

            async def wait(_interval):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

            with patch("psutil.cpu_percent", return_value=99) as read:
                with patch("src.system_metrics.asyncio.sleep", side_effect=wait):
                    try:
                        async with sampler.running():
                            await asyncio.wait_for(entered.wait(), timeout=1)
                            self.assertIsNone(sampler.value)
                            if fail:
                                raise RuntimeError("service startup failed")
                    except RuntimeError:
                        if not fail:
                            raise
                self.assertTrue(cancelled.is_set())
                self.assertIsNone(sampler.value)
                read.assert_called_once_with(interval=None)

    async def test_missing_psutil_leaves_metrics_unavailable(self):
        sampler = CpuSampler()
        with patch.dict("sys.modules", {"psutil": None}):
            with self.assertLogs("src.system_metrics", level="WARNING"):
                await sampler._sample()
            self.assertIsNone(sampler.value)
            self.assertEqual(execute_get_metrics({}), {"error": "psutil not installed"})

    async def test_both_metrics_paths_read_cache_without_sampling(self):
        for value in (None, 0.0, 23.4):
            with patch.object(cpu_sampler, "value", value):
                with patch("psutil.cpu_percent", side_effect=AssertionError("request sampled CPU")):
                    local = await asyncio.gather(*(system_metrics() for _ in range(20)))
                    remote = [execute_get_metrics({}) for _ in range(20)]
            self.assertTrue(all(item["cpu_percent"] == value for item in local + remote))


if __name__ == "__main__":
    unittest.main()
