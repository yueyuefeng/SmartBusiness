"""SQLite 工作单元：聚合、幂等结果及审计事件在同一事务提交。"""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from .domain import Conflict


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Repository:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS entities (
                    kind TEXT NOT NULL, id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS commands (
                    key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL);
                PRAGMA user_version = 1;
            """)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def get(db, kind, entity_id):
        if not isinstance(entity_id, str):
            raise ValueError("记录 ID 必须为文本")
        row = db.execute("SELECT body FROM entities WHERE kind=? AND id=?", (kind, entity_id)).fetchone()
        if not row:
            raise ValueError("找不到关联记录: " + kind)
        return json.loads(row[0])

    @staticmethod
    def save(db, kind, entity):
        db.execute("INSERT INTO entities(kind,id,body) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                   (kind, entity["id"], encoded(entity)))

    @staticmethod
    def replay(db, key, fingerprint):
        row = db.execute("SELECT fingerprint,result FROM commands WHERE key=?", (key,)).fetchone()
        if row:
            if row[0] != fingerprint:
                raise Conflict("幂等键已用于不同命令、参数或操作身份")
            return json.loads(row[1])
        return None

    @staticmethod
    def commit_command(db, key, fingerprint, result, event):
        db.execute("INSERT INTO commands VALUES (?,?,?)", (key, fingerprint, encoded(result)))
        db.execute("INSERT INTO events(body) VALUES (?)", (encoded(event),))

    def snapshot(self):
        with self.transaction() as db:
            result = {kind: [] for kind in ("signals", "opportunities", "resources", "contents", "contacts", "notes", "tasks")}
            for kind, body in db.execute("SELECT kind,body FROM entities ORDER BY rowid DESC"):
                result[kind].append(json.loads(body))
            result["events"] = [json.loads(row[0]) for row in db.execute("SELECT body FROM events ORDER BY seq DESC")]
            return result
