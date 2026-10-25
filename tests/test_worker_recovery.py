"""Deterministic outage/restart regressions; no provider or GPU calls."""
import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from apps.worker.main import control_post, main
from packages.common.config import settings
from packages.common.identity import model_identity
from scripts.gpu_experiment import compact_engine_sample


class WorkerRecovery(unittest.TestCase):
    def test_transient_failures_preserve_auth_and_finalization_payload(self):
        async def scenario():
            seen = []
            def api(request):
                seen.append((request.headers['authorization'], json.loads(request.content)))
                if len(seen) == 1:
                    raise httpx.ReadError('lost response', request=request)
                return httpx.Response(503 if len(seen) == 2 else 200, json={})
            async with httpx.AsyncClient(base_url='https://control.invalid',
                                        headers={'Authorization': 'Bearer unit-worker'},
                                        transport=httpx.MockTransport(api)) as client:
                await control_post(client, '/finalize', json={'epoch': 7, 'output_tokens': 3})
            self.assertEqual(seen, [('Bearer unit-worker', {'epoch': 7, 'output_tokens': 3})] * 3)
        asyncio.run(scenario())

    def test_auth_and_permanent_errors_never_retry(self):
        async def scenario(code):
            seen = []
            def api(request):
                seen.append(request)
                return httpx.Response(code)
            async with httpx.AsyncClient(base_url='https://control.invalid', transport=httpx.MockTransport(api)) as client:
                with self.assertRaises(httpx.HTTPStatusError):
                    await control_post(client, '/poll')
            self.assertEqual(len(seen), 1)
        for code in (400, 401, 403, 404, 409):
            with self.subTest(code=code):
                asyncio.run(scenario(code))

    def test_outage_budget_exhaustion_and_cancellation(self):
        async def scenario():
            async with httpx.AsyncClient(base_url='https://control.invalid',
                                        transport=httpx.MockTransport(lambda r: httpx.Response(502))) as client:
                with self.assertRaisesRegex(RuntimeError, 'recovery deadline'):
                    await control_post(client, '/poll', retry_seconds=0)
                task = asyncio.create_task(control_post(client, '/poll'))
                await asyncio.sleep(.01)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        asyncio.run(scenario())

    def test_stale_finalize_fence_is_terminal(self):
        async def scenario(code):
            async with httpx.AsyncClient(base_url='https://control.invalid',
                                        transport=httpx.MockTransport(lambda r: httpx.Response(code))) as client:
                result = await control_post(client, '/finalize', accepted_statuses=(404, 409))
                self.assertEqual(result.status_code, code)
        for code in (404, 409):
            asyncio.run(scenario(code))

    def test_retry_does_not_send_another_request_after_deadline(self):
        async def scenario():
            calls = []
            def api(request):
                calls.append(request)
                return httpx.Response(429)
            async with httpx.AsyncClient(base_url='https://control.invalid', transport=httpx.MockTransport(api)) as client:
                with self.assertRaisesRegex(RuntimeError, 'recovery deadline'):
                    await control_post(client, '/poll', retry_seconds=.01)
            self.assertEqual(len(calls), 1)
        asyncio.run(scenario())

    def test_slow_request_cannot_outlive_total_recovery_budget(self):
        async def scenario():
            canceled = asyncio.Event()
            async def api(request):
                try:
                    await asyncio.sleep(60)
                finally:
                    canceled.set()
                return httpx.Response(200)
            async with httpx.AsyncClient(base_url='https://control.invalid', transport=httpx.MockTransport(api)) as client:
                with self.assertRaisesRegex(RuntimeError, 'recovery deadline'):
                    await asyncio.wait_for(control_post(client, '/poll', retry_seconds=.01), timeout=1)
            self.assertTrue(canceled.is_set())
        asyncio.run(scenario())

    def test_worker_survives_poll_heartbeat_and_finalize_outages_without_reenrollment(self):
        async def scenario():
            calls = {'register': 0, 'heartbeat': 0, 'poll': 0, 'finalize': 0, 'engine': 0}
            finished = asyncio.Event()
            sent = False
            async def api(request):
                nonlocal sent
                name = request.url.path.rsplit('/', 1)[-1]
                calls[name] += 1
                if name == 'register':
                    return httpx.Response(200, json={'worker_token': 'unit-worker'})
                self.assertEqual(request.headers['authorization'], 'Bearer unit-worker')
                if calls[name] == 1:
                    return httpx.Response(502)
                if name == 'poll':
                    items = [] if sent else [{'id': 'r-one', 'epoch': 9, 'identity': model_identity(), 'payload': {}}]
                    sent = True
                    return httpx.Response(200, json={'items': items})
                if name == 'finalize':
                    self.assertEqual(json.loads(request.content)['epoch'], 9)
                    finished.set()
                return httpx.Response(200, json={})
            async def execute(item):
                calls['engine'] += 1
                return {'output_text': 'unit', 'input_tokens': 1, 'output_tokens': 1}
            real_client = httpx.AsyncClient
            def factory(*args, **kwargs):
                return real_client(*args, **kwargs, transport=httpx.MockTransport(api))
            with patch.object(settings(), 'execution_mode', 'mock'), patch.dict(os.environ, {'CONTROL_PLANE_URL': 'https://control.invalid'}), \
                    patch('httpx.AsyncClient', side_effect=factory), \
                    patch('apps.worker.engines.MockInferenceEngine.execute', side_effect=execute):
                task = asyncio.create_task(main())
                try:
                    await asyncio.wait_for(finished.wait(), timeout=8)
                    self.assertFalse(task.done())
                finally:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
            self.assertEqual(calls['register'], 1)
            self.assertEqual(calls['engine'], 1)
            self.assertEqual(calls['finalize'], 2)
            self.assertGreaterEqual(calls['heartbeat'], 2)
        asyncio.run(scenario())

    def test_compact_telemetry_retains_measurements_below_fragment_limit(self):
        record = {'observed_at': '2026-10-25T00:00:00Z', 'event': 'engine_sample',
                  'prometheus': '# ' + 'x' * 100000 + '\nvllm:num_requests_running 4\n'
                  'vllm:generation_tokens_total 123\nvllm:iteration_tokens_total_sum 500\n',
                  'nvidia_smi_csv': 'name, utilization.gpu [%]\nL4, 90 %\n'}
        result = compact_engine_sample(record)
        encoded = json.dumps(result).encode()
        self.assertLess(len(encoded), 8192)
        self.assertEqual(json.loads(encoded)['engine_metrics']['vllm:num_requests_running'], 4)
        self.assertEqual(result['engine_metrics']['vllm:generation_tokens_total'], 123)
        self.assertEqual(result['nvidia_smi_csv'], record['nvidia_smi_csv'])
        self.assertNotIn('prometheus', result)

    def test_bad_or_oversized_telemetry_stays_unknown(self):
        result = compact_engine_sample({'event': 'engine_sample', 'prometheus': 'broken{',
                                        'nvidia_smi_csv': 'x' * 20000})
        self.assertEqual(result['metrics_error'], 'invalid_prometheus')
        self.assertEqual(result['hardware_error'], 'sample_too_large')
        self.assertNotIn('engine_metrics', result)
        self.assertNotIn('nvidia_smi_csv', result)

    @unittest.skipIf(os.name == 'nt' or not shutil.which('bash'), 'Run Bash checkout regression in Linux/Docker')
    def test_bootstrap_restarts_with_existing_origin_and_modified_overlay(self):
        # Execute the actual generated checkout commands against an offline Git fixture.
        from scripts.prepare_gpu_payload import build_payload
        command = build_payload()['cmd'][0]
        checkout = command.split('git init -q\n', 1)[1].split('python3 -m venv', 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            origin = Path(tmp)/'origin'
            origin.mkdir()
            def git(*args, cwd=origin):
                return subprocess.check_output(['git', *args], cwd=cwd, stderr=subprocess.STDOUT).decode().strip()
            git('init', '-q')
            (origin/'overlay.py').write_text('base')
            git('add', '.')
            git('-c','user.name=fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture')
            sha = git('rev-parse','HEAD')
            checkout = checkout.replace('https://github.com/manishklach/InferenceFlow.git', str(origin))
            checkout = checkout.replace('c62386b2b6347f2555375fbd448d14769d852646', sha)
            target = Path(tmp)/'checkout'
            target.mkdir()
            git('init','-q',cwd=target)
            for _ in range(2):
                subprocess.run(['bash','-euc',checkout],cwd=target,check=True,capture_output=True)
                self.assertEqual((target/'overlay.py').read_text(),'base')
                (target/'overlay.py').write_text('reviewed overlay')
            self.assertEqual(git('remote','get-url','origin',cwd=target),str(origin))


if __name__ == '__main__':
    unittest.main()
