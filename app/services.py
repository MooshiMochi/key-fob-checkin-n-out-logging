from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from .db import get_conn


@dataclass
class LogRow:
    id: int
    key_uid: int
    key_uuid: str
    emp_uuid: Optional[str]
    key_label: str
    employee_name: Optional[str]
    check_out: datetime
    check_in: Optional[datetime]


def _decrypt_or_none(crypto, blob: Optional[bytes]) -> Optional[str]:
    if blob is None:
        return None
    try:
        # sqlite may return TEXT or BLOB; ensure bytes
        if isinstance(blob, str):
            # If somehow stored as text via repr, this will fail; expect bytes normally
            blob_bytes = blob.encode("latin1")
        else:
            blob_bytes = blob
        return crypto.decrypt_name(blob_bytes)
    except Exception:
        return None


def fetch_logs(
    crypto,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 200,
) -> List[LogRow]:
    where = []
    params: list = []
    if start is not None:
        where.append("checkOutTime >= ?")
        params.append(start)
    if end is not None:
        where.append("checkOutTime <= ?")
        params.append(end)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""

    sql = f"""
        SELECT l.id,
               l.tag_uid,
               l.text_uuid,
               l.employee_text_uuid,
               l.checkOutTime,
               l.checkInTime,
               kblob.encrypted_content AS key_blob,
               eblob.encrypted_content AS emp_blob
        FROM logs l
        LEFT JOIN uuid_to_encrypted_content kblob ON kblob.uuid = l.text_uuid
        LEFT JOIN uuid_to_encrypted_content eblob ON eblob.uuid = l.employee_text_uuid
        {where_sql}
        ORDER BY l.checkOutTime DESC
        LIMIT ?
    """
    params.append(limit)

    out: List[LogRow] = []
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        for r in cur.fetchall():
            key_label = _decrypt_or_none(crypto, r["key_blob"]) or "(unknown)"
            employee_name = (
                _decrypt_or_none(crypto, r["emp_blob"])
                if r["employee_text_uuid"]
                else None
            )
            out.append(
                LogRow(
                    id=r["id"],
                    key_uid=r["tag_uid"],
                    key_uuid=r["text_uuid"],
                    emp_uuid=r["employee_text_uuid"],
                    key_label=key_label,
                    employee_name=employee_name,
                    check_out=r["checkOutTime"],
                    check_in=r["checkInTime"],
                )
            )
    return out


@dataclass
class TagRow:
    uid: int
    uuid: str
    type: str  # 'emp' or 'key'
    active: bool
    label: str


def fetch_registered_tags(crypto) -> List[TagRow]:
    sql = """
        SELECT t.uid, t.text_uuid, t.type, t.active, b.encrypted_content
        FROM registered_tags t
        LEFT JOIN uuid_to_encrypted_content b ON b.uuid = t.text_uuid
        ORDER BY t.type, t.uid
    """
    out: List[TagRow] = []
    with get_conn() as conn:
        for r in conn.execute(sql).fetchall():
            label = _decrypt_or_none(crypto, r["encrypted_content"]) or "(unknown)"
            out.append(
                TagRow(
                    uid=r["uid"],
                    uuid=r["text_uuid"],
                    type=r["type"],
                    active=bool(r["active"]),
                    label=label,
                )
            )
    return out


def set_tag_active(uid: int, active: bool) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE registered_tags SET active = ?, updated_at = CURRENT_TIMESTAMP WHERE uid = ?",
            (1 if active else 0, uid),
        )


def lookup_uuid_encrypted(uuid: str) -> Optional[bytes]:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT encrypted_content FROM uuid_to_encrypted_content WHERE uuid = ?",
            (uuid,),
        )
        r = cur.fetchone()
        return r[0] if r else None
