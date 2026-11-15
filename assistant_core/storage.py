"""SQLite-backed chat history and user-managed local memories."""

from __future__ import annotations

import sqlite3
import os
import threading
import uuid
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class Message:
    role: str
    content: str


class Store:
    """Small SQLite repository. Each operation owns its connection and transaction."""

    _ENCRYPTED_MAGIC = b"ASTERDP1"

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.encrypted_path = database_path.with_suffix(database_path.suffix + ".enc")
        self._lock = threading.RLock()
        self._encrypted = self.encrypted_path.exists()

    @property
    def encryption_supported(self) -> bool:
        return os.name == "nt"

    def encryption_status(self) -> dict[str, bool]:
        encrypted = self.encrypted_path.exists() or self._encrypted
        return {"supported": self.encryption_supported, "enabled": encrypted}

    @staticmethod
    def _dpapi(data: bytes, *, protect: bool) -> bytes:
        """Protect bytes with the current Windows user's DPAPI master key."""
        if os.name != "nt":
            raise RuntimeError("Database encryption is currently supported on Windows only.")
        import ctypes
        from ctypes import wintypes

        class DataBlob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

        source_buffer = ctypes.create_string_buffer(data, len(data))
        source = DataBlob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
        destination = DataBlob()
        crypt32 = ctypes.windll.crypt32
        if protect:
            ok = crypt32.CryptProtectData(
                ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(destination)
            )
        else:
            description = ctypes.c_wchar_p()
            ok = crypt32.CryptUnprotectData(
                ctypes.byref(source), ctypes.byref(description), None, None, None, 0x1,
                ctypes.byref(destination),
            )
        if not ok:
            raise OSError(ctypes.windll.kernel32.GetLastError(), "Windows could not protect the local database.")
        try:
            return ctypes.string_at(destination.pbData, destination.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(destination.pbData)

    def _read_encrypted_database(self) -> bytes:
        payload = self.encrypted_path.read_bytes()
        if not payload.startswith(self._ENCRYPTED_MAGIC):
            raise ValueError("The encrypted Aster database has an unknown format.")
        raw = bytearray(self._dpapi(payload[len(self._ENCRYPTED_MAGIC):], protect=False))
        return self._sqlite_rollback_header(raw)

    @staticmethod
    def _sqlite_rollback_header(raw: bytearray | bytes) -> bytes:
        """Normalize an in-memory snapshot to rollback-journal header mode before deserialize."""
        value = bytearray(raw)
        if len(value) < 100 or value[:16] != b"SQLite format 3\x00":
            raise ValueError("The encrypted Aster database contents are invalid.")
        value[18:20] = b"\x01\x01"
        return bytes(value)

    def _write_encrypted_database(self, raw_database: bytes) -> None:
        self.encrypted_path.parent.mkdir(parents=True, exist_ok=True)
        normalized = self._sqlite_rollback_header(raw_database)
        encrypted = self._ENCRYPTED_MAGIC + self._dpapi(normalized, protect=True)
        temporary = self.encrypted_path.with_suffix(self.encrypted_path.suffix + ".tmp")
        with temporary.open("wb") as output:
            output.write(encrypted)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, self.encrypted_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self._lock.acquire()
        connection: sqlite3.Connection | None = None
        try:
            encrypted = self.encrypted_path.exists() or self._encrypted
            if encrypted:
                connection = sqlite3.connect(":memory:")
                if self.encrypted_path.exists():
                    connection.deserialize(self._read_encrypted_database())
            else:
                connection = sqlite3.connect(self.database_path, timeout=5)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
            connection.commit()
            if encrypted:
                self._write_encrypted_database(connection.serialize())
        except Exception:
            if connection is not None:
                connection.rollback()
            raise
        finally:
            if connection is not None:
                connection.close()
            self._lock.release()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        if self.encrypted_path.exists():
            if self.database_path.exists():
                raise RuntimeError("Both encrypted and plaintext Aster databases exist; refusing ambiguous startup.")
            self._encrypted = True
        with self._connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_conversation_order
                    ON messages(conversation_id, id);
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 2000),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_embeddings (
                    memory_id TEXT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
                    vector TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS assistant_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK (kind IN ('note', 'todo', 'reminder', 'calendar')),
                    title TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
                    content TEXT NOT NULL DEFAULT '',
                    due_at TEXT,
                    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS assistant_items_due_order
                    ON assistant_items(completed, due_at, id);
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approved_folders (
                    path TEXT PRIMARY KEY,
                    approved_at TEXT NOT NULL
                );
                """
            )

    def enable_encryption(self) -> None:
        """Migrate the SQLite database into a DPAPI-protected in-memory SQLite envelope."""
        if not self.encryption_supported:
            raise RuntimeError("Database encryption is currently supported on Windows only.")
        with self._lock:
            if self.encrypted_path.exists() or self._encrypted:
                return
            if self.database_path.exists():
                source = sqlite3.connect(self.database_path, timeout=5)
                snapshot = sqlite3.connect(":memory:")
                try:
                    source.backup(snapshot)
                    raw_database = snapshot.serialize()
                finally:
                    snapshot.close()
                    source.close()
            else:
                snapshot = sqlite3.connect(":memory:")
                try:
                    raw_database = snapshot.serialize()
                finally:
                    snapshot.close()
            self._write_encrypted_database(raw_database)
            for suffix in ("", "-wal", "-shm"):
                Path(str(self.database_path) + suffix).unlink(missing_ok=True)
            self._encrypted = True

    def disable_encryption(self) -> None:
        """Write an unencrypted SQLite copy. This leaves data readable to the OS account."""
        if not self.encryption_supported:
            raise RuntimeError("Database encryption is currently supported on Windows only.")
        with self._lock:
            if not self.encrypted_path.exists():
                self._encrypted = False
                return
            raw_database = self._read_encrypted_database()
            snapshot = sqlite3.connect(":memory:")
            temporary = self.database_path.with_suffix(self.database_path.suffix + ".tmp")
            target = sqlite3.connect(temporary)
            try:
                snapshot.deserialize(raw_database)
                snapshot.backup(target)
                target.commit()
            finally:
                target.close()
                snapshot.close()
            os.replace(temporary, self.database_path)
            self.encrypted_path.unlink()
            self._encrypted = False

    def add_message(self, conversation_id: str, role: str, content: str) -> int:
        if role not in {"user", "assistant"}:
            raise ValueError("Only user and assistant messages can be stored.")
        timestamp = _now()
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO conversations(id, created_at, updated_at) VALUES (?, ?, ?)",
                (conversation_id, timestamp, timestamp),
            )
            cursor = db.execute(
                "INSERT INTO messages(conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (conversation_id, role, content, timestamp),
            )
            db.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (timestamp, conversation_id),
            )
            return int(cursor.lastrowid)

    def get_messages(self, conversation_id: str, limit: int = 200) -> list[dict[str, str | int]]:
        bounded_limit = max(1, min(limit, 500))
        with self._connect() as db:
            rows = db.execute(
                """SELECT id, role, content, created_at FROM messages
                   WHERE conversation_id = ? ORDER BY id DESC LIMIT ?""",
                (conversation_id, bounded_limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def get_context(self, conversation_id: str, limit: int) -> list[Message]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT role, content FROM messages WHERE conversation_id = ?
                   ORDER BY id DESC LIMIT ?""",
                (conversation_id, max(1, min(limit, 100))),
            ).fetchall()
        return [Message(role=row["role"], content=row["content"]) for row in reversed(rows)]

    def list_conversations(self, limit: int = 50) -> list[dict[str, str | int]]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT c.id, c.created_at, c.updated_at,
                          COUNT(m.id) AS message_count,
                          COALESCE((SELECT substr(content, 1, 100) FROM messages
                                    WHERE conversation_id = c.id ORDER BY id LIMIT 1), '') AS preview
                   FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id
                   GROUP BY c.id ORDER BY c.updated_at DESC LIMIT ?""",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_conversation(self, conversation_id: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    def save_memory(self, content: str, memory_id: str | None = None) -> str:
        value = content.strip()
        if not 1 <= len(value) <= 2000:
            raise ValueError("A memory must contain 1 to 2000 characters.")
        identifier = memory_id or str(uuid.uuid4())
        timestamp = _now()
        with self._connect() as db:
            db.execute(
                """INSERT INTO memories(id, content, created_at, updated_at) VALUES (?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET content = excluded.content,
                                                updated_at = excluded.updated_at""",
                (identifier, value, timestamp, timestamp),
            )
        return identifier

    def list_memories(self) -> list[dict[str, str]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, content, created_at, updated_at FROM memories ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def search_memories(self, query: str, limit: int = 4) -> list[str]:
        """Return simple local keyword matches; semantic embeddings arrive in a later phase."""
        words = [word.strip(".,!?;:'\"()[]{}") for word in query.lower().split()]
        words = [word for word in words if len(word) > 2][:8]
        if not words:
            return []
        clauses = " OR ".join("lower(content) LIKE ?" for _ in words)
        values = [f"%{word}%" for word in words]
        with self._connect() as db:
            rows = db.execute(
                f"SELECT content FROM memories WHERE {clauses} ORDER BY updated_at DESC LIMIT ?",
                (*values, max(1, min(limit, 20))),
            ).fetchall()
        return [str(row["content"]) for row in rows]

    def save_memory_embedding(self, memory_id: str, embedding: list[float]) -> None:
        if not embedding or len(embedding) > 4096 or any(not isinstance(value, (int, float)) for value in embedding):
            raise ValueError("Invalid memory embedding.")
        encoded = json.dumps(embedding, separators=(",", ":"))
        with self._connect() as db:
            if not db.execute("SELECT 1 FROM memories WHERE id=?", (memory_id,)).fetchone():
                return
            db.execute(
                """INSERT INTO memory_embeddings(memory_id,vector) VALUES (?,?)
                   ON CONFLICT(memory_id) DO UPDATE SET vector=excluded.vector""",
                (memory_id, encoded),
            )

    def search_memories_by_embedding(self, embedding: list[float], limit: int = 4) -> list[str]:
        if not embedding or len(embedding) > 4096:
            return []
        with self._connect() as db:
            rows = db.execute(
                """SELECT m.content,e.vector FROM memories m JOIN memory_embeddings e ON e.memory_id=m.id
                   ORDER BY m.updated_at DESC LIMIT 1000"""
            ).fetchall()
        scored: list[tuple[float, str]] = []
        query_norm = sum(float(value) ** 2 for value in embedding) ** 0.5
        if not query_norm:
            return []
        for row in rows:
            try:
                vector = json.loads(row["vector"])
                if not isinstance(vector, list) or len(vector) != len(embedding):
                    continue
                norm = sum(float(value) ** 2 for value in vector) ** 0.5
                if not norm:
                    continue
                score = sum(float(left) * float(right) for left, right in zip(embedding, vector)) / (query_norm * norm)
                scored.append((score, str(row["content"])))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        scored.sort(key=lambda item: item[0], reverse=True)
        return [content for score, content in scored[:max(1, min(limit, 20))] if score > 0.2]

    def delete_memory(self, memory_id: str) -> bool:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            return cursor.rowcount > 0

    def forget_everything(self) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM messages")
            db.execute("DELETE FROM conversations")
            db.execute("DELETE FROM memories")
            db.execute("DELETE FROM assistant_items")
            db.execute("DELETE FROM approved_folders")
            db.execute("DELETE FROM settings")

    def create_item(self, kind: str, title: str, content: str = "", due_at: str | None = None) -> int:
        if kind not in {"note", "todo", "reminder", "calendar"}:
            raise ValueError("Unsupported local item type.")
        clean_title = title.strip()
        if not 1 <= len(clean_title) <= 120:
            raise ValueError("Item titles must contain 1 to 120 characters.")
        clean_content = content.strip()
        if len(clean_content) > 4000:
            raise ValueError("Item content is limited to 4000 characters.")
        normalized_due = None
        if due_at:
            try:
                parsed = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Due dates must use ISO 8601 format.") from exc
            if parsed.tzinfo is None:
                parsed = parsed.astimezone()
            normalized_due = parsed.astimezone(UTC).isoformat(timespec="seconds")
        timestamp = _now()
        with self._connect() as db:
            cursor = db.execute(
                """INSERT INTO assistant_items(kind,title,content,due_at,created_at,updated_at)
                   VALUES (?,?,?,?,?,?)""",
                (kind, clean_title, clean_content, normalized_due, timestamp, timestamp),
            )
            return int(cursor.lastrowid)

    def list_items(self, limit: int = 50) -> list[dict[str, str | int | None]]:
        with self._connect() as db:
            rows = db.execute(
                """SELECT id,kind,title,content,due_at,completed,created_at,updated_at
                   FROM assistant_items ORDER BY completed, CASE WHEN due_at IS NULL THEN 1 ELSE 0 END,
                   due_at, updated_at DESC LIMIT ?""",
                (max(1, min(limit, 100)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def search_items(self, kind: str, query: str, limit: int = 10) -> list[dict[str, str | int | None]]:
        if kind not in {"note", "todo", "reminder", "calendar"}:
            raise ValueError("Unsupported local item type.")
        needle = f"%{query.strip()[:200]}%"
        with self._connect() as db:
            rows = db.execute(
                """SELECT id,kind,title,content,due_at,completed,created_at,updated_at
                   FROM assistant_items WHERE kind=? AND (lower(title) LIKE lower(?) OR lower(content) LIKE lower(?))
                   ORDER BY updated_at DESC LIMIT ?""",
                (kind, needle, needle, max(1, min(limit, 50))),
            ).fetchall()
        return [dict(row) for row in rows]

    def complete_item(self, item_id: int) -> bool:
        timestamp = _now()
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE assistant_items SET completed=1,updated_at=? WHERE id=? AND kind IN ('todo','reminder')",
                (timestamp, item_id),
            )
        return cursor.rowcount > 0

    def delete_item(self, item_id: int) -> bool:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM assistant_items WHERE id=?", (item_id,))
        return cursor.rowcount > 0

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        if not 1 <= len(key) <= 100 or len(value) > 8000:
            raise ValueError("Invalid setting size.")
        timestamp = _now()
        with self._connect() as db:
            db.execute(
                """INSERT INTO settings(key,value,updated_at) VALUES (?,?,?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
                (key, value, timestamp),
            )

    def add_approved_folder(self, path: str) -> str:
        from pathlib import Path

        resolved = Path(path).expanduser().resolve(strict=True)
        if not resolved.is_dir():
            raise ValueError("Choose an existing folder.")
        normalized = str(resolved)
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO approved_folders(path,approved_at) VALUES (?,?)", (normalized, _now()))
        return normalized

    def list_approved_folders(self) -> list[str]:
        with self._connect() as db:
            rows = db.execute("SELECT path FROM approved_folders ORDER BY approved_at").fetchall()
        return [str(row["path"]) for row in rows]

    def remove_approved_folder(self, path: str) -> bool:
        from pathlib import Path

        normalized = str(Path(path).expanduser().resolve(strict=False))
        with self._connect() as db:
            cursor = db.execute("DELETE FROM approved_folders WHERE path=?", (normalized,))
        return cursor.rowcount > 0

    def export_data(self) -> dict[str, object]:
        with self._connect() as db:
            conversations = db.execute(
                "SELECT id,created_at,updated_at FROM conversations ORDER BY created_at"
            ).fetchall()
            messages = db.execute(
                "SELECT id,conversation_id,role,content,created_at FROM messages ORDER BY id"
            ).fetchall()
            memories = db.execute(
                "SELECT id,content,created_at,updated_at FROM memories ORDER BY created_at"
            ).fetchall()
            items = db.execute(
                "SELECT id,kind,title,content,due_at,completed,created_at,updated_at FROM assistant_items ORDER BY id"
            ).fetchall()
            settings = db.execute("SELECT key,value,updated_at FROM settings ORDER BY key").fetchall()
            folders = db.execute("SELECT path,approved_at FROM approved_folders ORDER BY approved_at").fetchall()
        return {
            "format": "aster-local-export-v1",
            "conversations": [dict(row) for row in conversations],
            "messages": [dict(row) for row in messages],
            "memories": [dict(row) for row in memories],
            "agenda": [dict(row) for row in items],
            "settings": [dict(row) for row in settings],
            "approved_folders": [dict(row) for row in folders],
        }

