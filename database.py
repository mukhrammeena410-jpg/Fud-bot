"""
Advanced SQLite database module for hathixfud bot.

Features:
  * Users, user history, payments, batch jobs, analytics
  * Rate limiting, anti-spam tracking
  * Migration from JSON
"""
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path

logger = logging.getLogger("hathixfud-bot.db")
_local = threading.local()


def _get_conn(db_path: str) -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(db_path, timeout=10)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA busy_timeout=5000")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_tables()

    def _init_tables(self):
        conn = _get_conn(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                protected INTEGER DEFAULT 0,
                plan_until REAL DEFAULT 0,
                apks_left INTEGER DEFAULT 0,
                name TEXT DEFAULT '',
                bonus_free INTEGER DEFAULT 0,
                ref_count INTEGER DEFAULT 0,
                ref_points INTEGER DEFAULT 0,
                joined REAL DEFAULT 0,
                ref TEXT DEFAULT '',
                referred_by TEXT DEFAULT '',
                redeemed TEXT DEFAULT '',
                reminder_sent INTEGER DEFAULT 0,
                lang TEXT DEFAULT 'en',
                total_spent REAL DEFAULT 0,
                last_active REAL DEFAULT 0,
                warnings INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS user_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                ts REAL DEFAULT 0,
                name TEXT DEFAULT '',
                file_size INTEGER DEFAULT 0,
                build_time REAL DEFAULT 0,
                status TEXT DEFAULT 'ok',
                FOREIGN KEY (chat_id) REFERENCES users(chat_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                amount TEXT DEFAULT '',
                plan_type TEXT DEFAULT '',
                plan_value INTEGER DEFAULT 0,
                proof_file_id TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                created_at REAL DEFAULT 0,
                processed_at REAL DEFAULT 0,
                processed_by INTEGER DEFAULT 0,
                note TEXT DEFAULT '',
                FOREIGN KEY (chat_id) REFERENCES users(chat_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS batch_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                status TEXT DEFAULT 'queued',
                total_apks INTEGER DEFAULT 0,
                completed INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                created_at REAL DEFAULT 0,
                started_at REAL DEFAULT 0,
                finished_at REAL DEFAULT 0,
                FOREIGN KEY (chat_id) REFERENCES users(chat_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS rate_limits (
                chat_id INTEGER PRIMARY KEY,
                apk_count INTEGER DEFAULT 0,
                window_start REAL DEFAULT 0,
                warnings INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT DEFAULT '',
                chat_id INTEGER DEFAULT 0,
                data TEXT DEFAULT '',
                ts REAL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_history_chat ON user_history(chat_id);
            CREATE INDEX IF NOT EXISTS idx_history_ts ON user_history(ts);
            CREATE INDEX IF NOT EXISTS idx_payments_chat ON payments(chat_id);
            CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
            CREATE INDEX IF NOT EXISTS idx_analytics_type ON analytics(event_type);
            CREATE INDEX IF NOT EXISTS idx_analytics_ts ON analytics(ts);

            CREATE TABLE IF NOT EXISTS apk_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_apk TEXT DEFAULT '',
                category TEXT DEFAULT '',
                pattern_type TEXT DEFAULT '',
                pattern_data TEXT DEFAULT '',
                effectiveness REAL DEFAULT 50,
                use_count INTEGER DEFAULT 0,
                created_at REAL DEFAULT 0,
                last_used REAL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_kb_category ON apk_knowledge(category);
            CREATE INDEX IF NOT EXISTS idx_kb_type ON apk_knowledge(pattern_type);
            CREATE INDEX IF NOT EXISTS idx_kb_effectiveness ON apk_knowledge(effectiveness DESC);
        """)
        conn.commit()
        logger.info("Database initialized at %s", self.db_path)

    # ---------------------- user CRUD ----------------------

    def get_user(self, chat_id: int):
        conn = _get_conn(self.db_path)
        row = conn.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def get_or_create_user(self, chat_id: int) -> dict:
        u = self.get_user(chat_id)
        if u:
            return u
        default = {
            "protected": 0, "plan_until": 0, "apks_left": 0, "name": "",
            "bonus_free": 0, "ref_count": 0, "ref_points": 0,
            "joined": 0, "ref": "", "referred_by": "",
            "redeemed": "", "reminder_sent": 0, "lang": "en",
            "total_spent": 0, "last_active": 0, "warnings": 0, "is_banned": 0,
        }
        conn = _get_conn(self.db_path)
        conn.execute(
            """INSERT INTO users (chat_id, protected, plan_until, apks_left,
               name, bonus_free, ref_count, ref_points, joined, ref,
               referred_by, redeemed, reminder_sent, lang, total_spent,
               last_active, warnings, is_banned)
               VALUES (?, 0, 0, 0, '', 0, 0, 0, 0, '', '', '', 0, 'en', 0, 0, 0, 0)""",
            (chat_id,),
        )
        conn.commit()
        return default

    def save_user(self, chat_id: int, data: dict):
        conn = _get_conn(self.db_path)
        conn.execute(
            """INSERT OR REPLACE INTO users
               (chat_id, protected, plan_until, apks_left, name,
                bonus_free, ref_count, ref_points, joined, ref,
                referred_by, redeemed, reminder_sent, lang, total_spent,
                last_active, warnings, is_banned)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chat_id,
                data.get("protected", 0),
                data.get("plan_until", 0),
                data.get("apks_left", 0),
                data.get("name", ""),
                data.get("bonus_free", 0),
                data.get("ref_count", 0),
                data.get("ref_points", 0),
                data.get("joined", 0),
                data.get("ref", ""),
                data.get("referred_by", ""),
                data.get("redeemed", ""),
                1 if data.get("reminder_sent") else 0,
                data.get("lang", "en"),
                data.get("total_spent", 0),
                data.get("last_active", 0),
                data.get("warnings", 0),
                1 if data.get("is_banned") else 0,
            ),
        )
        conn.commit()

    def save_all_users(self, users: dict):
        conn = _get_conn(self.db_path)
        conn.executemany(
            """INSERT OR REPLACE INTO users
               (chat_id, protected, plan_until, apks_left, name,
                bonus_free, ref_count, ref_points, joined, ref,
                referred_by, redeemed, reminder_sent, lang, total_spent,
                last_active, warnings, is_banned)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    int(uid),
                    u.get("protected", 0),
                    u.get("plan_until", 0),
                    u.get("apks_left", 0),
                    u.get("name", ""),
                    u.get("bonus_free", 0),
                    u.get("ref_count", 0),
                    u.get("ref_points", 0),
                    u.get("joined", 0),
                    u.get("ref", ""),
                    u.get("referred_by", ""),
                    u.get("redeemed", ""),
                    1 if u.get("reminder_sent") else 0,
                    u.get("lang", "en"),
                    u.get("total_spent", 0),
                    u.get("last_active", 0),
                    u.get("warnings", 0),
                    1 if u.get("is_banned") else 0,
                )
                for uid, u in users.items()
            ],
        )
        conn.commit()

    def delete_user(self, chat_id: int):
        conn = _get_conn(self.db_path)
        conn.execute("DELETE FROM users WHERE chat_id = ?", (chat_id,))
        conn.execute("DELETE FROM user_history WHERE chat_id = ?", (chat_id,))
        conn.commit()

    def get_all_users(self) -> dict:
        conn = _get_conn(self.db_path)
        rows = conn.execute("SELECT * FROM users").fetchall()
        return {str(row["chat_id"]): self._row_to_dict(row) for row in rows}

    def count_users(self) -> int:
        conn = _get_conn(self.db_path)
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def update_last_active(self, chat_id: int):
        conn = _get_conn(self.db_path)
        conn.execute("UPDATE users SET last_active = ? WHERE chat_id = ?",
                     (time.time(), chat_id))
        conn.commit()

    # ---------------------- history ----------------------

    def add_history(self, chat_id: int, ts: float, name: str,
                    file_size: int = 0, build_time: float = 0, status: str = "ok"):
        conn = _get_conn(self.db_path)
        conn.execute(
            """INSERT INTO user_history (chat_id, ts, name, file_size, build_time, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (chat_id, ts, name, file_size, build_time, status),
        )
        conn.commit()

    def get_history(self, chat_id: int, limit: int = 20) -> list:
        conn = _get_conn(self.db_path)
        rows = conn.execute(
            "SELECT ts, name, file_size, build_time, status FROM user_history "
            "WHERE chat_id = ? ORDER BY ts DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def trim_history(self, chat_id: int, keep: int = 20):
        conn = _get_conn(self.db_path)
        conn.execute(
            """DELETE FROM user_history WHERE chat_id = ? AND id NOT IN
               (SELECT id FROM user_history WHERE chat_id = ?
                ORDER BY ts DESC LIMIT ?)""",
            (chat_id, chat_id, keep),
        )
        conn.commit()

    # ---------------------- payments ----------------------

    def add_payment(self, chat_id: int, amount: str, plan_type: str,
                    plan_value: int, proof_file_id: str = "") -> int:
        conn = _get_conn(self.db_path)
        cur = conn.execute(
            """INSERT INTO payments (chat_id, amount, plan_type, plan_value,
               proof_file_id, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
            (chat_id, amount, plan_type, plan_value, proof_file_id, time.time()),
        )
        conn.commit()
        return cur.lastrowid

    def get_pending_payments(self) -> list:
        conn = _get_conn(self.db_path)
        rows = conn.execute(
            "SELECT * FROM payments WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
        return [dict(row) for row in rows]

    def process_payment(self, payment_id: int, approved: bool, processed_by: int):
        conn = _get_conn(self.db_path)
        status = "approved" if approved else "rejected"
        conn.execute(
            "UPDATE payments SET status = ?, processed_at = ?, processed_by = ? WHERE id = ?",
            (status, time.time(), processed_by, payment_id),
        )
        conn.commit()

    def get_user_payments(self, chat_id: int, limit: int = 10) -> list:
        conn = _get_conn(self.db_path)
        rows = conn.execute(
            "SELECT * FROM payments WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_payment_stats(self) -> dict:
        conn = _get_conn(self.db_path)
        total = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
        pending = conn.execute(
            "SELECT COUNT(*) FROM payments WHERE status = 'pending'"
        ).fetchone()[0]
        approved = conn.execute(
            "SELECT COUNT(*) FROM payments WHERE status = 'approved'"
        ).fetchone()[0]
        return {"total": total, "pending": pending, "approved": approved}

    # ---------------------- batch jobs ----------------------

    def create_batch_job(self, chat_id: int, total_apks: int) -> int:
        conn = _get_conn(self.db_path)
        cur = conn.execute(
            """INSERT INTO batch_jobs (chat_id, status, total_apks, created_at)
               VALUES (?, 'queued', ?, ?)""",
            (chat_id, total_apks, time.time()),
        )
        conn.commit()
        return cur.lastrowid

    def update_batch_job(self, job_id: int, **kwargs):
        conn = _get_conn(self.db_path)
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [job_id]
        conn.execute(f"UPDATE batch_jobs SET {sets} WHERE id = ?", vals)
        conn.commit()

    def get_batch_jobs(self, chat_id: int) -> list:
        conn = _get_conn(self.db_path)
        rows = conn.execute(
            "SELECT * FROM batch_jobs WHERE chat_id = ? ORDER BY created_at DESC LIMIT 5",
            (chat_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    # ---------------------- rate limiting ----------------------

    def check_rate_limit(self, chat_id: int, max_per_hour: int = 5) -> bool:
        conn = _get_conn(self.db_path)
        now = time.time()
        window = now - 3600
        row = conn.execute(
            "SELECT * FROM rate_limits WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        if not row or row["window_start"] < window:
            conn.execute(
                """INSERT OR REPLACE INTO rate_limits
                   (chat_id, apk_count, window_start, warnings)
                   VALUES (?, 1, ?, 0)""",
                (chat_id, now),
            )
            conn.commit()
            return True
        if row["apk_count"] >= max_per_hour:
            return False
        conn.execute(
            "UPDATE rate_limits SET apk_count = apk_count + 1 WHERE chat_id = ?",
            (chat_id,),
        )
        conn.commit()
        return True

    def get_rate_limit(self, chat_id: int) -> dict:
        conn = _get_conn(self.db_path)
        row = conn.execute(
            "SELECT * FROM rate_limits WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        return dict(row) if row else {"apk_count": 0, "window_start": 0, "warnings": 0}

    # ---------------------- analytics ----------------------

    def log_event(self, event_type: str, chat_id: int = 0, data: str = ""):
        conn = _get_conn(self.db_path)
        conn.execute(
            "INSERT INTO analytics (event_type, chat_id, data, ts) VALUES (?, ?, ?, ?)",
            (event_type, chat_id, data, time.time()),
        )
        conn.commit()

    def get_events(self, event_type: str, since: float = 0, limit: int = 100) -> list:
        conn = _get_conn(self.db_path)
        rows = conn.execute(
            "SELECT * FROM analytics WHERE event_type = ? AND ts >= ? "
            "ORDER BY ts DESC LIMIT ?",
            (event_type, since, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def count_events(self, event_type: str, since: float = 0) -> int:
        conn = _get_conn(self.db_path)
        return conn.execute(
            "SELECT COUNT(*) FROM analytics WHERE event_type = ? AND ts >= ?",
            (event_type, since),
        ).fetchone()[0]

    # ---------------------- queries ----------------------

    def get_paying_users(self) -> list:
        now = time.time()
        conn = _get_conn(self.db_path)
        rows = conn.execute("SELECT * FROM users WHERE plan_until > ?", (now,)).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_limited_users(self) -> list:
        conn = _get_conn(self.db_path)
        rows = conn.execute("SELECT * FROM users WHERE apks_left > 0").fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_new_users_since(self, since: float) -> int:
        conn = _get_conn(self.db_path)
        return conn.execute(
            "SELECT COUNT(*) FROM users WHERE joined >= ?", (since,)
        ).fetchone()[0]

    def count_protected_today(self, since: float) -> int:
        conn = _get_conn(self.db_path)
        return conn.execute(
            "SELECT COUNT(*) FROM user_history WHERE ts >= ?", (since,)
        ).fetchone()[0]

    def total_protected(self) -> int:
        conn = _get_conn(self.db_path)
        return conn.execute(
            "SELECT COALESCE(SUM(protected), 0) FROM users"
        ).fetchone()[0]

    def get_all_user_ids(self) -> list:
        conn = _get_conn(self.db_path)
        rows = conn.execute("SELECT chat_id FROM users").fetchall()
        return [row["chat_id"] for row in rows]

    def get_active_users(self, since: float) -> list:
        conn = _get_conn(self.db_path)
        rows = conn.execute(
            "SELECT * FROM users WHERE last_active >= ? ORDER BY last_active DESC",
            (since,),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_top_users(self, limit: int = 10) -> list:
        conn = _get_conn(self.db_path)
        rows = conn.execute(
            "SELECT * FROM users ORDER BY protected DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    # ---------------------- migration ----------------------

    def migrate_from_json(self, json_path: str) -> int:
        try:
            data = json.loads(Path(json_path).read_text())
        except Exception as e:
            logger.warning("Could not read JSON file %s: %s", json_path, e)
            return 0
        if not data:
            return 0
        count = 0
        for uid_str, u in data.items():
            try:
                chat_id = int(uid_str)
            except (ValueError, TypeError):
                continue
            history = u.pop("history", [])
            self.save_user(chat_id, u)
            for h in history:
                self.add_history(chat_id, h.get("ts", 0), h.get("name", ""))
            self.trim_history(chat_id, keep=20)
            count += 1
        logger.info("Migrated %d users from JSON to SQLite", count)
        return count

    # ---------------------- knowledge base ----------------------

    def add_kb_pattern(self, source_apk: str, category: str, pattern_type: str,
                       pattern_data: str, effectiveness: float = 50) -> int:
        conn = _get_conn(self.db_path)
        cur = conn.execute(
            """INSERT INTO apk_knowledge
               (source_apk, category, pattern_type, pattern_data, effectiveness, use_count, created_at, last_used)
               VALUES (?, ?, ?, ?, ?, 0, ?, ?)""",
            (source_apk, category, pattern_type, pattern_data, effectiveness, time.time(), time.time()),
        )
        conn.commit()
        return cur.lastrowid

    def get_kb_patterns(self, category: str, pattern_type: str, limit: int = 50) -> list:
        conn = _get_conn(self.db_path)
        rows = conn.execute(
            """SELECT * FROM apk_knowledge
               WHERE category = ? AND pattern_type = ?
               ORDER BY effectiveness DESC, use_count DESC
               LIMIT ?""",
            (category, pattern_type, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_kb_best_pattern(self, category: str, pattern_type: str) -> dict | None:
        conn = _get_conn(self.db_path)
        row = conn.execute(
            """SELECT * FROM apk_knowledge
               WHERE category = ? AND pattern_type = ?
               ORDER BY effectiveness DESC, use_count ASC
               LIMIT 1""",
            (category, pattern_type),
        ).fetchone()
        return dict(row) if row else None

    def get_kb_weighted_random(self, category: str, pattern_type: str) -> dict | None:
        conn = _get_conn(self.db_path)
        rows = conn.execute(
            """SELECT * FROM apk_knowledge
               WHERE category = ? AND pattern_type = ?
               ORDER BY effectiveness DESC""",
            (category, pattern_type),
        ).fetchall()
        if not rows:
            return None
        weights = [max(1, r["effectiveness"]) for r in rows]
        total = sum(weights)
        import random
        pick = random.uniform(0, total)
        cumulative = 0
        for row, w in zip(rows, weights):
            cumulative += w
            if pick <= cumulative:
                return dict(row)
        return dict(rows[-1])

    def update_kb_score(self, pattern_id: int, success: bool):
        conn = _get_conn(self.db_path)
        delta = 10 if success else -5
        conn.execute(
            """UPDATE apk_knowledge
               SET effectiveness = MIN(100, MAX(10, effectiveness + ?)),
                   use_count = use_count + 1,
                   last_used = ?
               WHERE id = ?""",
            (delta, time.time(), pattern_id),
        )
        conn.commit()

    def get_kb_stats(self) -> dict:
        conn = _get_conn(self.db_path)
        total = conn.execute("SELECT COUNT(*) FROM apk_knowledge").fetchone()[0]
        by_cat = {}
        for cat in ("encryption", "poison", "wrapper"):
            count = conn.execute(
                "SELECT COUNT(*) FROM apk_knowledge WHERE category = ?", (cat,)
            ).fetchone()[0]
            avg = conn.execute(
                "SELECT COALESCE(AVG(effectiveness), 0) FROM apk_knowledge WHERE category = ?", (cat,)
            ).fetchone()[0]
            by_cat[cat] = {"count": count, "avg_score": round(avg, 1)}
        return {"total": total, "by_category": by_cat}

    def clear_kb(self):
        conn = _get_conn(self.db_path)
        conn.execute("DELETE FROM apk_knowledge")
        conn.commit()

    # ---------------------- helpers ----------------------

    @staticmethod
    def _row_to_dict(row) -> dict:
        d = dict(row)
        d["reminder_sent"] = bool(d.get("reminder_sent", 0))
        d["is_banned"] = bool(d.get("is_banned", 0))
        return d
