# this is the code that actually runs the app

from .db import init_db
from mfrc522 import SimpleMFRC522
from .crypto_secure import Crypto
from .config import cfg
from .engine import Engine, TagEvent
import time


def main():
    init_db()

    crypto = Crypto(cfg.secret_key_path)
    reader = SimpleMFRC522()

    engine = Engine(crypto, reader)

    while True:
        print("Place your card on the reader...")
        card_id, text = reader.read()
        # print(f"[DEBUG] Card ID: {card_id}")
        # print(f"[DEBUG] Data on card: {(text or '').strip()!r}")
        event: TagEvent = TagEvent(int(card_id), str(text).strip())
        engine.process_card(event)
        time.sleep(1)  # debounce


if __name__ == "__main__":
    import RPi.GPIO as GPIO

    try:
        main()
    except Exception as e:
        raise e
    except KeyboardInterrupt:
        print("Exiting...")
        exit(0)
    finally:
        GPIO.cleanup()
