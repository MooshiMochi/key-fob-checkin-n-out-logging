import traceback
from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from datetime import datetime, timedelta


from .models import (
    verify_tag_content,
    get_tag_info,
    activate_tag,
    register_or_overwrite_tag,
    get_key_log_times,
    check_in_key,
    check_out_key,
)
from .reader_adapter import ReaderAdapter


@dataclass
class SessionState:
    active_employee_card_id: Optional[int] = None
    window_expires_at: Optional[datetime] = None


@dataclass
class TagEvent:
    uid: int  # the UID of the tag/card
    text: str  # the text data on the tag/card


class Engine:
    CHECKOUT_WINDOW = timedelta(seconds=20)
    CHECKIN_MIN_AGE = timedelta(minutes=2)

    def __init__(self, crypto, reader: ReaderAdapter):
        self.state = SessionState()
        self.crypto = crypto
        self.reader = reader

    def _prompt(self, prompt: str, options: list[str]) -> int:
        print(
            prompt
            + "\n"
            + "\n".join(f"[{num+1}] {opt}".ljust(4) for num, opt in enumerate(options))
            + "\nEnter choice number:"
        )
        while True:
            try:
                choice = int(input().strip())
                if 1 <= choice <= len(options):
                    return choice
            except ValueError:
                pass
            print(
                f"[PROMPT]> Invalid choice. Please enter a number corresponding to your choice (between 1 to {len(options)})."
            )

    def process_card(self, evt: TagEvent):
        now = datetime.now()

        tag_type, is_active = get_tag_info(evt.uid)
        if tag_type is None:
            print(f"[REGISTRATION]> Unregistered tag UID {evt.uid}.")
            if (
                self._prompt(
                    "[REGISTRATION]> Would you like to register the tag?", ["Yes", "No"]
                )
                == 1
            ):
                self.register_tag(evt.uid)
            else:
                print("[REGISTRATION]> Ignoring unregistered tag.")
            return

        if not is_active:
            print(f"[ERROR]> Tag UID {evt.uid} is inactive.")
            if (
                self._prompt(
                    "[REGISTRATION]> Would you like to re-activate the tag?",
                    ["Yes", "No"],
                )
                == 1
            ):
                activate_tag(evt.uid)
                print(f"[REGISTRATION]> Tag UID {evt.uid} re-activated.")
            else:
                print("[REGISTRATION]> Ignoring inactive tag.")
            return
        # print(f"[DEBUG] Tag UID {evt.uid} identified as {tag_type}.")

        is_valid = verify_tag_content(evt.uid, evt.text)
        if not is_valid:
            print(
                f"[ERROR]> Tag UID {evt.uid} does not have a valid registered content. Possible tampering detected. Would you like to re-register it? (y/n)"
            )
            if self._prompt("[REGISTRATION]> Re-register tag?", ["Yes", "No"]) == 1:
                self.register_tag(evt.uid)
            else:
                print("[REGISTRATION]> Ignoring tag.")
            return

        if tag_type == "emp":
            self.process_emp_tag(evt, now)
        elif tag_type == "key":
            self.process_key_tag(evt, now)
        else:
            # doubt it's going to happen unless the DB is manually edited
            print(
                f"[ERROR]> Unknown tag type {tag_type} for UID {evt.uid}. Did you edit the database? Ignoring."
            )

    def process_emp_tag(self, evt: TagEvent, now: datetime):
        if self.state.active_employee_card_id == evt.uid:
            # same employee card tapped again
            if self.state.window_expires_at and now <= self.state.window_expires_at:
                print(
                    f"[Check OUT]> Employee card UID {evt.uid} tapped again within checkout window. Cancelling checkout session."
                )
                self.state.active_employee_card_id = None
                self.state.window_expires_at = None
                return
            # same employee card tapped after checkout window expired
            # new session

        self.state.active_employee_card_id = evt.uid
        self.state.window_expires_at = now + self.CHECKOUT_WINDOW
        print(
            f"[Check OUT]> Active employee card set to UID {evt.uid}. Checkout window expires at {self.state.window_expires_at.strftime('%H:%M:%S (in %d seconds)')}."
        )

    def process_key_tag(self, evt: TagEvent, now: datetime):
        # get whether the key is checked in or out first
        check_out: Optional[datetime]
        check_in: Optional[datetime]

        check_out, check_in = get_key_log_times(evt.uid, evt.text)
        # print("[DEBUG] Key log times:", check_out, check_in)

        # Key is currently in the office.
        if (not check_out and not check_in) or (check_in and check_out):
            # the user wants to checkout the key
            if self.state.active_employee_card_id is None or (
                self.state.window_expires_at is None
                or now > self.state.window_expires_at
            ):
                print(
                    "[Check Out]> Failed! No active employee card. Please tap your employee card first to checkout the key."
                )
                self.state.active_employee_card_id = None
                self.state.window_expires_at = None
                return
            employee_uid = self.state.active_employee_card_id
            try:
                check_out_key(evt.uid, evt.text, employee_uid)
            except ValueError as ve:
                print(f"[Check Out]> Failed! Error checking out key: {ve}")
                return

            print(
                f"[Check OUT]> Success! The key can be checked in again after { self.CHECKIN_MIN_AGE.total_seconds() } seconds."
            )
            return

        # Key is currently checked out.
        if check_out and not check_in:
            # the user wants to check in the key
            print(check_out.strftime("%H:%M:%S"))
            if check_out + self.CHECKIN_MIN_AGE > now:
                print(
                    f"[Check IN]> Failed! The key was checked out at {check_out.strftime('%H:%M:%S')}. It can only be checked in after { (check_out + self.CHECKIN_MIN_AGE - now).total_seconds() } seconds. Please wait."
                )
                return
            check_in_key(evt.uid, evt.text)

            # if the key was checked out, and the current user wants to check it out as well

            # if (
            #     self.state.active_employee_card_id is not None
            #     and self.state.window_expires_at is not None
            #     and self.state.window_expires_at > now
            # ):
            #     print("[DEBUG]> Attempting automatic checkout...")
            #     self.process_card(evt)

            print(f"[Check IN]> Success! Key is now checked in.")
            return

        print(
            "[ERROR]> Unexpected state encountered while processing key tag. Please contact the administrator."
        )

    def register_tag(self, uid: int):
        # print(f"[DEBUG] Registering new tag with UID {uid}.")
        tag_type = self._prompt(
            "[REGISTRATION]> Select tag type:", ["Employee tag", "Key tag"]
        )
        if tag_type == 1:
            tag_type = "emp"
        else:
            tag_type = "key"

        text = input(
            "[REGISTRATION]> Enter the name or identifier for this tag: "
        ).strip()
        if not text:
            print("[REGISTRATION]> No input provided. Aborting registration.")
            return
        encrypted_content = self.crypto.encrypt_name(text)
        uuid_key = str(uuid4()).replace("-", "")

        register_or_overwrite_tag(uid, tag_type, uuid_key, encrypted_content)
        print("[REGISTRATION]> Tap the tag again to finalize the registration...")
        while True:
            try:
                self.reader.write(uuid_key)
                _id, _text = self.reader.read()
                if _id == uid and (_text or "").strip() == uuid_key:
                    break
                print(f"Failed to write to tag UID {uid}. Please tap your card again!")
            except Exception as e:
                print(f"Error writing to tag UID {uid}: Please tap your card again!")
                traceback.print_tb(e.__traceback__)
                continue
        # print(f"[DEBUG] Wrote '{uuid_key}' to tag UID {uid}.")
        print(f"[REGISTRATION]> Success! Tag UID {uid} is now registered.")
