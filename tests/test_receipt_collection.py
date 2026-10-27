import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import httpx
from packages.common.receipt_format import canonical_sha256, text_sha256, verify_receipt
from scripts.experiment_receipts import collect


class ReceiptCollectionTests(unittest.TestCase):
    def test_digest_is_order_independent_and_rejects_changed_or_malformed_receipt(self):
        self.assertEqual(canonical_sha256({'b':2,'a':1}), canonical_sha256({'a':1,'b':2}))
        for value in ({}, {'receipt':None,'sha256':'x'}, {'receipt':{'schema':'wrong'},'sha256':2}):
            self.assertFalse(verify_receipt(value))

    def test_stage_receipts_match_outputs_or_fail_closed(self):
        row = {'custom_id':'one','output_text':'synthetic result','usage':{'input_tokens':4,'output_tokens':2},
               'charge_micro_usd':10}
        receipt = {'schema':'inferenceflow.execution-receipt.v1','job_id':'job_owned','custom_id':'one',
            'status':'succeeded','model':{'execution_mode':'vllm'},'usage':row['usage'],
            'hashes':{'output_sha256':text_sha256(row['output_text'])},
            'billing':{'request_settlement_reconciled':True,'capture_records':1,'usage_records':1,'captured':10}}
        for mismatch in (False, True):
            body = json.loads(json.dumps(receipt))
            if mismatch:
                body['billing']['captured'] = 11
            envelope = {'receipt':body,'sha256':canonical_sha256(body)}
            def respond(request):
                self.assertEqual(request.method,'GET')
                self.assertEqual(request.url.path,'/v1/jobs/job_owned/receipts')
                return httpx.Response(200,json={'items':[envelope],'next_cursor':None})
            client = httpx.Client(base_url='https://example.invalid',transport=httpx.MockTransport(respond))
            with TemporaryDirectory() as folder, patch('scripts.experiment_receipts.httpx.Client', return_value=client):
                directory = Path(folder)
                (directory/'jobs.json').write_text(json.dumps([{'id':'job_owned'}]))
                (directory/'results.json').write_text(json.dumps([row]))
                connection = {'CONTROL_PLANE_URL':'https://example.invalid','INFERENCEFLOW_API_KEY':'synthetic-key'}
                if mismatch:
                    with self.assertRaises(RuntimeError):
                        collect(connection,directory)
                    self.assertFalse((directory/'receipts.json').exists())
                else:
                    self.assertEqual(collect(connection,directory),1)
                    self.assertTrue((directory/'receipts.json').exists())


if __name__ == '__main__':
    unittest.main()
