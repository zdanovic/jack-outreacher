"""
Small helper for optional at-rest encryption of sensitive text blobs.

If DATA_ENCRYPTION_KEY is set, values passed through DataCipher will
be encrypted before persisting to disk (e.g. messages). Decryption
is transparent for readers. Errors during decrypt return an empty
string to avoid leaking garbage to the UI.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Optional

try:
    from cryptography.fernet import Fernet  # type: ignore
except Exception:  # pragma: no cover
    Fernet = None  # type: ignore


class DataCipher:
    def __init__(self, key: Optional[str]) -> None:
        self.enabled = bool(key and Fernet is not None)
        self._fernet: Optional[Fernet] = None
        if self.enabled and key:
            # Derive a 32-byte key from the provided secret to keep config simple.
            digest = hashlib.sha256(key.encode()).digest()
            derived = base64.urlsafe_b64encode(digest)
            self._fernet = Fernet(derived)

    def encrypt(self, value: str) -> str:
        if not self.enabled or not self._fernet:
            return value
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        if not self.enabled or not self._fernet:
            return value
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except Exception:
            # If decryption fails (e.g., legacy plaintext rows), return empty string.
            return ""
