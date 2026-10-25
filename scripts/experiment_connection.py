"""Minimal owner-encrypted connection handoff; never exports database/Auth0 keys."""

import json
from urllib.parse import urlsplit

from scripts.sealed_evidence import seal


def connection_payload(origin, bootstrap, metrics, api_key):
    url = urlsplit(origin)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path not in ("", "/")):
        raise ValueError("Bare approved HTTPS control-plane origin required")
    if any(not isinstance(value, str) or len(value) < 32 or "\n" in value or "\r" in value
           for value in (bootstrap, metrics, api_key)):
        raise ValueError("Strong experiment-only credentials required")
    return {"CONTROL_PLANE_URL": origin.rstrip("/"), "WORKER_BOOTSTRAP_TOKEN": bootstrap,
            "METRICS_TOKEN": metrics, "INFERENCEFLOW_API_KEY": api_key}


def seal_connection(origin, bootstrap, metrics, api_key, public_pem):
    return seal(json.dumps(connection_payload(origin, bootstrap, metrics, api_key)).encode(), public_pem)
