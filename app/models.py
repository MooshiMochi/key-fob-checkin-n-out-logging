from datetime import datetime
from typing import Optional, Tuple, Union

from .db import get_conn


def verify_tag_content(uid: int, expected_content: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT text_uuid FROM registered_tags WHERE uid = ? AND active = 1 AND text_uuid = ? AND EXISTS (SELECT 1 FROM uuid_to_encrypted_content WHERE uuid = registered_tags.text_uuid) LIMIT 1",
            (uid, expected_content),
        )
        return cur.fetchone() is not None


def get_tag_info(uid: int) -> Union[Tuple[str, bool], Tuple[None, None]]:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT type, active FROM registered_tags WHERE uid = ? LIMIT 1",
            (uid,),
        )
        row = cur.fetchone()
        if row:
            return row["type"], bool(row["active"])
        return None, None


def activate_tag(uid: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE registered_tags SET active = 1, updated_at = CURRENT_TIMESTAMP WHERE uid = ?",
            (uid,),
        )


def register_or_overwrite_tag(
    uid: int, tag_type: str, text_uuid: str, encrypted_content: str | bytes
):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO registered_tags (uid, text_uuid, type, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(uid)
            DO UPDATE SET
                text_uuid = excluded.text_uuid,
                type = excluded.type,
                updated_at = CURRENT_TIMESTAMP;
            """,
            (uid, text_uuid, tag_type),
        )

        conn.execute(
            """
            INSERT INTO uuid_to_encrypted_content (uuid, encrypted_content)
            VALUES (?, ?)
            ON CONFLICT(uuid) DO NOTHING;
            """,
            (text_uuid, encrypted_content),
        )


def get_key_log_times(
    uid: int, text_uuid: str
) -> Tuple[Optional[datetime], Optional[datetime]]:
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT checkOutTime, checkInTime FROM logs
            WHERE tag_uid = ? AND text_uuid = ?
            ORDER BY checkOutTime DESC
            LIMIT 1
            """,
            (uid, text_uuid),
        )
        row = cur.fetchone()
        if row:
            return row["checkOutTime"], row["checkInTime"]
        return None, None


def check_in_key(uid: int, text_uuid: str):
    with get_conn() as conn:
        # Verify the key is checked out to the employee
        cur = conn.execute(
            """
            SELECT id FROM logs
            WHERE tag_uid = ? AND text_uuid = ? AND checkInTime IS NULL
            ORDER BY checkOutTime DESC
            LIMIT 1
            """,
            (uid, text_uuid),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("This key is not checked out to you.")

        log_id = row["id"]

        # Perform check-in
        conn.execute(
            """
            UPDATE logs
            SET checkInTime = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (log_id,),
        )


def check_out_key(uid: int, text_uuid: str, employee_uid: int):
    with get_conn() as conn:
        # Verify the key is not already checked out
        cur = conn.execute(
            """
            SELECT id FROM logs
            WHERE tag_uid = ? AND text_uuid = ? AND checkInTime IS NULL
            LIMIT 1
            """,
            (uid, text_uuid),
        )
        row = cur.fetchone()
        if row:
            raise ValueError("This key is already checked out.")

        # Perform check-out
        conn.execute(
            """
            INSERT INTO logs (tag_uid, text_uuid, employee_text_uuid)
            VALUES (?, ?, (SELECT text_uuid FROM registered_tags WHERE uid = ?))
            """,
            (uid, text_uuid, employee_uid),
        )
