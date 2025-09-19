from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


class ReaderAdapter:
    def read(self) -> Tuple[int, str]:
        raise NotImplementedError

    def write(self, text: str) -> None:
        raise NotImplementedError


class RealReader(ReaderAdapter):
    def __init__(self):
        # Import here so desktop without hardware can still import module
        # this is going to be enforced in production
        from mfrc522 import SimpleMFRC522  # type: ignore

        self._reader = SimpleMFRC522()

    def read(self) -> Tuple[int, str]:
        uid, text = self._reader.read()
        return int(uid), (text or "").strip()

    def write(self, text: str) -> None:
        self._reader.write(text)


@dataclass
class MockState:
    last_uid: Optional[int] = None
    last_text: str = ""


class MockReader(ReaderAdapter):
    """A simple in-memory mock. Use set_next(uid, text) to simulate a tap."""

    def __init__(self, state: Optional[MockState] = None):
        self.state = state or MockState()

    def set_next(self, uid: int, text: str) -> None:
        self.state.last_uid = int(uid)
        self.state.last_text = (text or "").strip()

    def read(self) -> Tuple[int, str]:
        if self.state.last_uid is None:
            raise RuntimeError("No mock tag present. Call set_next(uid, text) first.")
        uid, text = self.state.last_uid, self.state.last_text
        # Clear after read
        self.state.last_uid = None
        self.state.last_text = ""
        return uid, text

    def write(self, text: str) -> None:
        # In the mock, we treat write as success and reflect the data
        self.state.last_text = (text or "").strip()
