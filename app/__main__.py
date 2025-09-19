# this is the code that actually runs the app

import argparse
import time

from .config import cfg
from .crypto_secure import Crypto
from .db import init_db
from .engine import Engine, TagEvent
from .reader_adapter import RealReader
from .ui_main import run_ui


def main():
    parser = argparse.ArgumentParser(description="Key Fob Checkin/Out")
    parser.add_argument("--cli", action="store_true", help="Run in CLI reader loop")
    parser.add_argument("--mock", action="store_true", help="Run UI with mock reader")
    args = parser.parse_args()

    init_db()

    if not args.cli:
        # Default: run UI
        run_ui(mock=args.mock)
        return

    # Legacy CLI loop
    crypto = Crypto(cfg.secret_key_path)
    reader = RealReader()
    engine = Engine(crypto, reader)

    while True:
        print("Place your card on the reader...")
        card_id, text = reader.read()
        event: TagEvent = TagEvent(int(card_id), str(text).strip())
        engine.process_card(event)
        time.sleep(1)  # debounce


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Exiting...")
        raise SystemExit(0)
