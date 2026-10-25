"""Owner-key encrypted experiment evidence; runner receives only a public key."""

import base64
import hashlib
import json
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AAD = b"inferenceflow-private-evidence-v1"


def seal(payload, public_pem):
    public = serialization.load_pem_public_key(public_pem)
    if not isinstance(public, rsa.RSAPublicKey) or public.key_size < 3072:
        raise ValueError("Owner RSA public key of at least 3072 bits required")
    key, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
    wrapped = public.encrypt(key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),
                                             algorithm=hashes.SHA256(), label=AAD))
    encrypted = AESGCM(key).encrypt(nonce, payload, AAD)
    return json.dumps({"format": "inferenceflow-private-evidence-v1",
                       "recipient_sha256": hashlib.sha256(public_pem).hexdigest(),
                       "wrapped_key": base64.b64encode(wrapped).decode(),
                       "nonce": base64.b64encode(nonce).decode(),
                       "ciphertext": base64.b64encode(encrypted).decode()}).encode()


def unseal(envelope, private_pem):
    record = json.loads(envelope)
    if record["format"] != "inferenceflow-private-evidence-v1":
        raise ValueError("Unsupported evidence format")
    private = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(private, rsa.RSAPrivateKey):
        raise ValueError("Owner RSA private key required")
    key = private.decrypt(base64.b64decode(record["wrapped_key"], validate=True),
                          padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=AAD))
    return AESGCM(key).decrypt(base64.b64decode(record["nonce"], validate=True),
                               base64.b64decode(record["ciphertext"], validate=True), AAD)
