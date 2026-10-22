import os
import pytest
from packages.python_sdk import InferenceFlowClient


@pytest.mark.skipif(os.getenv("RUN_GPU_E2E") != "1", reason="Requires explicitly configured real GPU stack")
def test_real_gpu():
    with InferenceFlowClient(
        os.environ["INFERENCEFLOW_API_KEY"], os.getenv("CONTROL_PLANE_URL", "http://localhost:8080")
    ) as c:
        assert c.get_models()["models"][0]["execution_mode"] != "mock"
        j = c.create_job(
            [
                {
                    "custom_id": "gpu-smoke",
                    "messages": [{"role": "user", "content": "Name the capital of France."}],
                    "max_output_tokens": 32,
                }
            ]
        )
        assert c.wait_for_job(j["id"], timeout=600)["status"] == "succeeded"
        r = c.get_results(j["id"])["items"][0]
        assert r["output_text"] and not r["output_text"].startswith("MOCK")
        assert r["usage"]["input_tokens"] > 0 and r["usage"]["output_tokens"] > 0 and r["charge_micro_usd"] > 0
