import json
import unittest

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from scripts.sealed_evidence import seal, unseal


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        cls.private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption())
        cls.public = key.public_key().public_bytes(serialization.Encoding.PEM,
                                                   serialization.PublicFormat.SubjectPublicKeyInfo)

    def test_owner_roundtrip_and_no_plaintext(self):
        secret = b'private prompt and database contents'
        envelope = seal(secret, self.public)
        self.assertNotIn(secret, envelope)
        self.assertEqual(unseal(envelope, self.private), secret)
        self.assertNotEqual(seal(secret, self.public), envelope)

    def test_wrong_recipient_fails(self):
        wrong = rsa.generate_private_key(public_exponent=65537, key_size=3072).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        with self.assertRaises(ValueError):
            unseal(seal(b'private', self.public), wrong)

    def test_tampered_ciphertext_fails(self):
        envelope = json.loads(seal(b'private', self.public))
        value = envelope['ciphertext']
        envelope['ciphertext'] = ('A' if value[0] != 'A' else 'B')+value[1:]
        with self.assertRaises(InvalidTag):
            unseal(json.dumps(envelope), self.private)
