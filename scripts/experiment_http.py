"""Bounded retries for experiment reads only; never retries submissions."""
import time

import httpx


def retry_read(operation):
    for attempt in range(3):
        try:
            return operation()
        except httpx.HTTPStatusError as error:
            if error.response.status_code not in {429, 502, 503, 504} or attempt == 2:
                raise
        except httpx.TransportError:
            if attempt == 2:
                raise
        time.sleep(attempt+1)


def get(client, path, **kwargs):
    def read():
        response = client.get(path, **kwargs)
        response.raise_for_status()
        return response
    return retry_read(read)


def failure_receipt(error):
    receipt = {"error_type": type(error).__name__}
    if isinstance(error, httpx.HTTPError):
        try:
            request = error.request
        except RuntimeError:
            request = None
        if request is not None:
            receipt.update(http_method=request.method, http_host=request.url.host,
                           http_path=request.url.path)
        if isinstance(error, httpx.HTTPStatusError):
            receipt["http_status"] = error.response.status_code
    return receipt
