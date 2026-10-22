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
    return hmac.new(settings().secret_key.encode(), s.encode(), hashlib.sha256).hexdigest()


def crypt():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings().secret_key.encode()).digest()))


def encrypt(obj):
    return crypt().encrypt(json.dumps(obj).encode()).decode()


def decrypt(value):
    return json.loads(crypt().decrypt(value.encode()))


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
