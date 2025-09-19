import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class Crypto:
    def __init__(self, key_path: str):
        self.key_path = key_path
        self.key = self._load_or_create_key()

    def _load_or_create_key(self) -> bytes:
        if os.path.exists(self.key_path):
            with open(self.key_path, "rb") as f:
                return f.read()
        key = AESGCM.generate_key(bit_length=256)
        with open(self.key_path, "wb") as f:
            f.write(key)
        return key

    def encrypt_name(self, full_name: str) -> bytes:
        # AES-GCM: nonce 12 bytes + ciphertext+tag
        aes = AESGCM(self.key)
        nonce = os.urandom(12)
        data = full_name.encode("utf-8")
        ct = aes.encrypt(nonce, data, associated_data=None)
        return nonce + ct

    def decrypt_name(self, blob: bytes) -> str:
        aes = AESGCM(self.key)
        nonce, ct = blob[:12], blob[12:]
        pt = aes.decrypt(nonce, ct, associated_data=None)
        return pt.decode("utf-8")
