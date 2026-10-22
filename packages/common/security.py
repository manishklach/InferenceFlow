import base64
import hashlib
import hmac
import json
import secrets
import socket
import ipaddress
from urllib.parse import urlsplit
from cryptography.fernet import Fernet
from packages.common.config import settings


def digest(s):
    key = settings().credential_hash_key or settings().secret_key
    return hmac.new(key.encode(), s.encode(), hashlib.sha256).hexdigest()


def digest_candidates(s):
    cfg = settings()
    keys = [cfg.credential_hash_key or cfg.secret_key, *cfg.credential_hash_previous_keys]
    return [hmac.new(k.encode(), s.encode(), hashlib.sha256).hexdigest() for k in keys]


def crypt():
    cfg = settings()
    if cfg.encryption_active_key:
        return Fernet(cfg.encryption_keys[cfg.encryption_active_key].encode())
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(cfg.secret_key.encode()).digest()))


def encrypt(obj):
    value = crypt().encrypt(json.dumps(obj).encode()).decode()
    key = settings().encryption_active_key
    return "v1:" + key + ":" + value if key else value


def decrypt(value):
    cfg = settings()
    if value.startswith("v1:"):
        _, key, ciphertext = value.split(":", 2)
        return json.loads(Fernet(cfg.encryption_keys[key].encode()).decrypt(ciphertext.encode()))
    # Explicit legacy key permits staged migration without coupling new encryption to JWT keys.
    legacy = cfg.encryption_legacy_secret or cfg.secret_key
    cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(legacy.encode()).digest()))
    return json.loads(cipher.decrypt(value.encode()))


def token(prefix="if_live_"):
    return prefix + secrets.token_urlsafe(32)


def validate_url(url):
    u = urlsplit(url)
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.fragment or u.port not in (None, 443):
        raise ValueError("HTTPS port 443 without credentials required")
    addresses = sorted({x[4][0] for x in socket.getaddrinfo(u.hostname, 443, type=socket.SOCK_STREAM)})
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError("Only public destination IPs allowed")
    return addresses
