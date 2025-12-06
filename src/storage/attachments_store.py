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

    def add(self, original_name: str, stored_path: str, mime_type: str, size_bytes: int) -> int:
        cur = self._db.conn.cursor()
        cur.execute(
            """
            INSERT INTO attachments (original_name, stored_path, mime_type, size_bytes, created_at)
            VALUES (?, ?, ?, ?, ?);
            """,
            (
                original_name,
                stored_path,
                mime_type,
                size_bytes,
                datetime.utcnow().isoformat(),
            ),
        )
        self._db.conn.commit()
        return int(cur.lastrowid)

    def get(self, attachment_id: int) -> Optional[Dict[str, Any]]:
        cur = self._db.conn.cursor()
        cur.execute(
            """
            SELECT id, original_name, stored_path, mime_type, size_bytes, created_at
            FROM attachments WHERE id = ?;
            """,
            (attachment_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "original_name": row[1],
            "stored_path": row[2],
            "mime_type": row[3],
            "size_bytes": row[4],
            "created_at": row[5],
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
        att_id = self.add(upload_file.filename or rand_name, dest_path, upload_file.content_type or "application/octet-stream", size)
        return {"id": att_id, "original_name": upload_file.filename, "size": size}


attachments_store = AttachmentsStore()
