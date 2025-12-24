from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from .state_db import get_state_db, DATA_DIR


ATTACH_DIR = os.path.join(DATA_DIR, "attachments")


class AttachmentsStore:
    def __init__(self) -> None:
        self._db = get_state_db()
        os.makedirs(ATTACH_DIR, exist_ok=True)

    def add(self, original_name: str, stored_path: str, mime_type: str, size_bytes: int) -> Dict[str, Any]:
        public_id = uuid.uuid4().hex
        cur = self._db.conn.cursor()
        cur.execute(
            """
            INSERT INTO attachments (public_id, original_name, stored_path, mime_type, size_bytes, created_at)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                public_id,
                original_name,
                stored_path,
                mime_type,
                size_bytes,
                datetime.utcnow().isoformat(),
            ),
        )
        self._db.conn.commit()
        return {"id": public_id, "legacy_id": int(cur.lastrowid)}

    def get(self, attachment_id: str) -> Optional[Dict[str, Any]]:
        # Prefer public UUID; fall back to numeric legacy id if provided.
        cur = self._db.conn.cursor()
        if attachment_id.isdigit():
            cur.execute(
                """
                SELECT id, public_id, original_name, stored_path, mime_type, size_bytes, created_at
                FROM attachments WHERE id = ?;
                """,
                (int(attachment_id),),
            )
        else:
            cur.execute(
                """
                SELECT id, public_id, original_name, stored_path, mime_type, size_bytes, created_at
                FROM attachments WHERE public_id = ?;
                """,
                (attachment_id,),
            )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "legacy_id": row[0],
            "id": row[1],
            "original_name": row[2],
            "stored_path": row[3],
            "mime_type": row[4],
            "size_bytes": row[5],
            "created_at": row[6],
        }

    def safe_store_upload(self, upload_file) -> Dict[str, Any]:
        """
        Save an UploadFile to disk with a random name and register metadata.
        """
        os.makedirs(ATTACH_DIR, exist_ok=True)
        suffix = os.path.splitext(upload_file.filename or "")[1]
        rand_name = f"{uuid.uuid4().hex}{suffix}"
        dest_path = os.path.join(ATTACH_DIR, rand_name)
        with open(dest_path, "wb") as out_f:
            shutil.copyfileobj(upload_file.file, out_f)
        size = os.path.getsize(dest_path)
        att = self.add(upload_file.filename or rand_name, dest_path, upload_file.content_type or "application/octet-stream", size)
        return {
            "id": att["id"],
            "legacy_id": att["legacy_id"],
            "original_name": upload_file.filename,
            "size": size,
        }


attachments_store = AttachmentsStore()
