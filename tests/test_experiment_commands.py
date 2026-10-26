from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import httpx
import json

from scripts.experiment_commands import Mailbox, validate, read_command, receipt_for_log, COMMAND_URL


def command(**changes):
    return {"run_id": "123-1", "sequence": 1, "policy": "adaptive",
            "expires_at": (datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(), **changes}


class CommandTests(unittest.TestCase):
    def test_authenticated_read_is_fixed_to_main_and_never_logs_credentials(self):
        with TemporaryDirectory() as folder:
            runtime = Path(folder)

            def respond(request):
                self.assertEqual(str(request.url).split('?')[0], COMMAND_URL)
                self.assertEqual(request.url.params['ref'], 'main')
                self.assertEqual(request.headers['authorization'], 'Bearer test-only')
                return httpx.Response(200, json=command())

            def factory(**kwargs):
                return httpx.Client(transport=httpx.MockTransport(respond), **kwargs)

            self.assertEqual(read_command('test-only', runtime, factory)['sequence'], 1)
            self.assertNotIn('test-only', (runtime/'command-read-status.json').read_text())
            record = {**command(), 'status': 'verified', 'observed_at': 'fixture', 'private_audit': 'never-log'}
            (runtime/'command-receipt.json').write_text(json.dumps(record))
            self.assertNotIn('never-log', json.dumps(receipt_for_log(runtime)))

    def test_wrong_host_replay_expiry_and_extra_fields(self):
        now = datetime.now(timezone.utc)
        for c in (command(run_id="321-1"), command(sequence=2), command(sequence=True),
                  command(expires_at=(now-timedelta(seconds=1)).isoformat()),
                  command(expires_at=(now+timedelta(hours=1)).isoformat())):
            self.assertFalse(validate(c, "123-1", 0, now))
        with self.assertRaises(ValueError):
            validate(command(shell="injected"), "123-1", 0, now)

    def test_single_execution_and_restart_deduplication(self):
        with TemporaryDirectory() as folder:
            calls = []
            runtime = Path(folder)
            def transition(*args):
                calls.append(args[0])
            box = Mailbox(runtime, "https://unused.invalid", "123-1", transition=transition)
            box.tick(fetch=command)
            restarted = Mailbox(runtime, "https://unused.invalid", "123-1", transition=transition)
            restarted.tick(fetch=command)
            self.assertEqual(calls, ["adaptive"])

    def test_failed_transition_consumes_command_and_stops_host(self):
        with TemporaryDirectory() as folder:
            runtime = Path(folder)

            def fail(*args):
                raise RuntimeError("Injected failure")

            box = Mailbox(runtime, "https://unused.invalid", "123-1", transition=fail)
            with self.assertRaises(RuntimeError):
                box.tick(fetch=command)
            self.assertTrue((runtime / "STOP").exists())
            self.assertEqual(box.previous, 1)

    def test_failed_audit_blocks_policy_and_audit_command_never_restarts(self):
        for passed in (True, False):
            with TemporaryDirectory() as folder:
                calls = []

                def transition(*args):
                    calls.append(args)

                box = Mailbox(Path(folder), "https://unused.invalid", "123-1", transition=transition,
                              audit=lambda: {"passed": passed, "accepted_requests": 10})
                if passed:
                    box.tick(fetch=lambda: command(policy="audit"))
                else:
                    with self.assertRaises(RuntimeError):
                        box.tick(fetch=command)
                self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
