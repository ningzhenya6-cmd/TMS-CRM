"""Knowledge store - SQLite backed storage for knowledge entries."""
import json
import os
import sqlite3
import time
import re
import math
import threading
from collections import Counter

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "knowledge.db")
KB_FILE = os.path.join(DATA_DIR, "kb.json")  # kept for migration

os.makedirs(DATA_DIR, exist_ok=True)

# Thread-local DB connections for safe concurrent access
_local = threading.local()


def _get_db():
    """Get thread-local SQLite connection."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
    return _local.conn


def _init_db():
    """Create tables if they don't exist."""
    db = _get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'general',
            tags TEXT NOT NULL DEFAULT '[]',
            related_questions TEXT NOT NULL DEFAULT '[]',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    # Create FTS5 virtual table for full-text search
    _ensure_fts5()
    db.commit()


def _row_to_entry(row):
    """Convert SQLite row to entry dict."""
    return {
        "id": row["id"],
        "title": row["title"],
        "content": row["content"],
        "category": row["category"],
        "tags": json.loads(row["tags"]) if row["tags"] else [],
        "related_questions": json.loads(row["related_questions"]) if row["related_questions"] else [],
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
    }


def _migrate_from_json():
    """Migrate data from kb.json to SQLite if db is empty and json exists."""
    if not os.path.exists(KB_FILE):
        return
    db = _get_db()
    count = db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    if count > 0:
        return  # already migrated
    try:
        with open(KB_FILE, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, IOError):
        return
    if not entries:
        return
    for e in entries:
        db.execute(
            "INSERT OR REPLACE INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                e.get("id", ""),
                e.get("title", ""),
                e.get("content", ""),
                e.get("category", "general"),
                json.dumps(e.get("tags", []), ensure_ascii=False),
                json.dumps(e.get("related_questions", []), ensure_ascii=False),
                1 if e.get("is_active", True) else 0,
                e.get("created_at", ""),
                "",
            ),
        )
    db.commit()
    print(f"[store] 已从 kb.json 迁移 {len(entries)} 条到 SQLite")


def _tokenize(text):
    """Simple Chinese + English tokenizer using character n-grams for Chinese."""
    text = text.lower()
    tokens = []

    # Split into Chinese and non-Chinese segments
    segments = re.findall(r"[一-鿿]+|[a-z0-9]+", text)

    for seg in segments:
        if re.match(r"^[一-鿿]+$", seg):
            # Chinese: use character bigrams and trigrams
            if len(seg) <= 2:
                tokens.append(seg)
            for i in range(len(seg)):
                tokens.append(seg[i])  # unigrams
            for i in range(len(seg) - 1):
                tokens.append(seg[i : i + 2])  # bigrams
            for i in range(len(seg) - 2):
                tokens.append(seg[i : i + 3])  # trigrams
        else:
            # English: split words
            tokens.extend([w for w in seg.split("_") if len(w) > 1])
            tokens.append(seg)

    return tokens


def _search_text(entry):
    """Combine entry fields into one searchable text string."""
    return "{} {} {} {}".format(
        entry.get("title", ""),
        entry.get("content", ""),
        " ".join(entry.get("tags", [])),
        " ".join(entry.get("related_questions", [])),
    )


def _fts5_text(entry):
    """Combine entry fields with spaces between CJK characters for FTS5 indexing.

    The unicode61 tokenizer in SQLite FTS5 (before 3.52) does not tokenize
    CJK ideographs as individual tokens. By inserting spaces between consecutive
    CJK characters, each character becomes its own FTS5 token, enabling
    character-level matching for Chinese/Japanese/Korean text.
    """
    text = _search_text(entry)
    # Insert space between any two consecutive CJK characters
    text = re.sub(r"(?<=[一-鿿])(?=[一-鿿])", " ", text)
    return text


def _build_fts5_query(query):
    """Build FTS5 MATCH query from user query string.

    Uses OR between Chinese bigrams (recall-focused) and AND with English terms.
    BM25 ranking naturally favors entries matching more bigrams.
    """
    q = query.lower().strip()
    if not q:
        return ""

    segments = re.findall(r"[一-鿿]+|[a-z0-9]+", q)
    chinese_groups = []
    english_terms = []

    for seg in segments:
        if re.match(r"^[一-鿿]+$", seg):
            # Chinese segment: generate bigrams as OR group
            bigrams = []
            for i in range(len(seg) - 1):
                bigrams.append('"{}"'.format(" ".join(seg[i : i + 2])))
            # Also add unigrams for short segments
            if len(seg) <= 2:
                bigrams.append('"{}"'.format(" ".join(seg)))
            if bigrams:
                chinese_groups.append("({})".format(" OR ".join(bigrams)))
        else:
            # English/numeric terms
            if len(seg) >= 2:
                english_terms.append('"{}"'.format(seg))

    groups = []
    if chinese_groups:
        # OR all Chinese bigram groups (for recall)
        groups.append("({})".format(" OR ".join(chinese_groups)))
    if english_terms:
        # AND English terms (for precision)
        groups.append("({})".format(" AND ".join(english_terms)))

    if not groups:
        return ""

    return " AND ".join(groups)


def _ensure_fts5():
    """Create FTS5 virtual table if it doesn't exist. Returns True if available."""
    db = _get_db()
    try:
        db.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS fts5_entries USING fts5("
            "  entry_id UNINDEXED,"
            "  search_text,"
            "  tokenize='unicode61'"
            ")"
        )
        db.commit()
        return True
    except Exception:
        return False


def _rebuild_fts5(entries):
    """Rebuild the FTS5 index from a list of entry dicts."""
    db = _get_db()
    try:
        db.execute("DELETE FROM fts5_entries")
        for e in entries:
            if not e.get("is_active", True):
                continue
            text = _fts5_text(e)
            db.execute(
                "INSERT INTO fts5_entries(entry_id, search_text) VALUES (?, ?)",
                (e["id"], text),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise


def _upsert_fts5_entry(entry):
    """Add or update a single entry in the FTS5 index."""
    db = _get_db()
    text = _fts5_text(entry)
    db.execute(
        "INSERT OR REPLACE INTO fts5_entries(entry_id, search_text) VALUES (?, ?)",
        (entry["id"], text),
    )
    db.commit()


def _delete_fts5_entry(entry_id):
    """Remove an entry from the FTS5 index."""
    db = _get_db()
    db.execute("DELETE FROM fts5_entries WHERE entry_id = ?", (entry_id,))
    db.commit()


class KnowledgeStore:
    def __init__(self, use_fts5=True):
        _init_db()
        self.entries = []
        self._idf_cache = {}
        self._dirty = False
        self._lock = threading.Lock()
        self._use_fts5 = use_fts5 and _ensure_fts5()
        self.load()

    def load(self):
        """Load all entries from SQLite into memory and rebuild indexes."""
        db = _get_db()
        rows = db.execute("SELECT * FROM entries ORDER BY created_at").fetchall()
        self.entries = [_row_to_entry(r) for r in rows]
        self._build_index()
        if self._use_fts5:
            _rebuild_fts5(self.entries)

    def save(self):
        """Sync in-memory entries to SQLite and rebuild FTS5 index."""
        db = _get_db()
        with self._lock:
            db.execute("BEGIN")
            try:
                db.execute("DELETE FROM entries")
                for e in self.entries:
                    db.execute(
                        "INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            e.get("id", ""),
                            e.get("title", ""),
                            e.get("content", ""),
                            e.get("category", "general"),
                            json.dumps(e.get("tags", []), ensure_ascii=False),
                            json.dumps(e.get("related_questions", []), ensure_ascii=False),
                            1 if e.get("is_active", True) else 0,
                            e.get("created_at", ""),
                            "",
                        ),
                    )
                if self._use_fts5:
                    _rebuild_fts5(self.entries)
                db.commit()
            except Exception:
                db.rollback()
                raise
        self._dirty = False

    def _build_index(self):
        """Build IDF cache from all entries."""
        doc_count = len(self.entries)
        if doc_count == 0:
            self._idf_cache = {}
            return

        word_doc_counts = Counter()
        for entry in self.entries:
            text = "{} {} {} {}".format(
                entry.get("title", ""),
                entry.get("content", ""),
                " ".join(entry.get("tags", [])),
                " ".join(entry.get("related_questions", [])),
            )
            words = set(_tokenize(text))
            for w in words:
                word_doc_counts[w] += 1

        self._idf_cache = {
            w: math.log((doc_count + 1) / (count + 1)) + 1
            for w, count in word_doc_counts.items()
        }

    def add_entry(self, entry):
        """Add a single knowledge entry."""
        eid = entry.get(
            "id", "kb-{}-{}".format(int(time.time()), len(self.entries))
        )
        entry["id"] = eid
        entry["created_at"] = entry.get(
            "created_at", time.strftime("%Y-%m-%d")
        )
        entry["is_active"] = entry.get("is_active", True)
        with self._lock:
            self.entries.append(entry)
            self._dirty = True
            self._build_index()
            if self._use_fts5:
                _upsert_fts5_entry(entry)
        return eid

    def add_entries(self, entries):
        for e in entries:
            e["id"] = e.get("id", "kb-{}-{}".format(int(time.time()), len(self.entries)))
            e["created_at"] = e.get(
                "created_at", time.strftime("%Y-%m-%d")
            )
            e["is_active"] = e.get("is_active", True)
        with self._lock:
            self.entries.extend(entries)
            self._dirty = True
            self._build_index()
            if self._use_fts5:
                for e in entries:
                    _upsert_fts5_entry(e)

    def update_entry(self, entry_id, updates):
        with self._lock:
            for e in self.entries:
                if e["id"] == entry_id:
                    e.update(updates)
                    self._dirty = True
                    self._build_index()
                    if self._use_fts5:
                        _upsert_fts5_entry(e)
                    return True
        return False

    def delete_entry(self, entry_id):
        with self._lock:
            self.entries = [e for e in self.entries if e["id"] != entry_id]
            self._dirty = True
            self._build_index()
            if self._use_fts5:
                _delete_fts5_entry(entry_id)

    def get_entry(self, entry_id):
        for e in self.entries:
            if e["id"] == entry_id:
                return e
        return None

    def _detect_query_categories(self, query):
        """Detect which known categories the query relates to."""
        q = query.lower()
        matches = set()
        for cat in self.get_categories():
            cat_lower = cat.lower()
            # Check if category words appear in query
            cat_words = re.findall(r'[a-z0-9]+|[一-鿿]+', cat_lower)
            for w in cat_words:
                if len(w) >= 2 and w in q:
                    matches.add(cat)
                    break
        return matches

    def _rerank_with_signals(self, results, query, top_k):
        """Re-rank FTS5 results with title/tag/category boosting."""
        q = query.lower().strip()
        query_tokens = set(_tokenize(q))
        query_cats = self._detect_query_categories(q)

        scored = []
        for entry, bm25_score in results:
            boost = 1.0

            # Title exact match: big boost
            title = entry.get("title", "").lower()
            if q in title:
                boost *= 2.0
            elif any(word in title for word in q.split()):
                boost *= 1.5

            # Title token overlap boost
            title_tokens = set(_tokenize(title))
            overlap = len(query_tokens & title_tokens)
            if overlap > 0:
                boost *= 1.0 + (overlap * 0.2)

            # Tag match boost
            tags_lower = [t.lower() for t in entry.get("tags", [])]
            for tag in tags_lower:
                if tag in q:
                    boost *= 1.3
                    break

            # Category match boost
            cat = entry.get("category", "").lower()
            if cat in query_cats:
                boost *= 1.4

            # Related questions match boost
            for rq in entry.get("related_questions", []):
                if any(t in rq.lower() for t in query_tokens if len(t) > 1):
                    boost *= 1.2
                    break

            scored.append((entry, bm25_score * boost))

        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]

    def _ft_search(self, query, top_k=10):
        """FTS5-based search with signal re-ranking. Returns list of (entry, score) pairs."""
        if not self._use_fts5 or not query.strip():
            return None

        fts5_q = _build_fts5_query(query)
        if not fts5_q:
            return None

        db = _get_db()
        try:
            # Query FTS5 with BM25 ranking (lower rank = better match)
            # Fetch more candidates for re-ranking
            rows = db.execute(
                "SELECT entry_id, rank FROM fts5_entries "
                "WHERE fts5_entries MATCH ? ORDER BY rank LIMIT ?",
                (fts5_q, top_k * 3),
            ).fetchall()
            if not rows:
                return None

            # Build entry_id → entry lookup
            entry_map = {e["id"]: e for e in self.entries if e.get("is_active", True)}

            results = []
            for r in rows:
                entry = entry_map.get(r["entry_id"])
                if entry:
                    # BM25: lower rank = better. Convert to similarity score.
                    rank = abs(r["rank"])
                    score = 1.0 / (1.0 + rank)
                    results.append((entry, score))

            # Re-rank with title/tag/category signals
            results = self._rerank_with_signals(results, query, top_k)
            return results
        except Exception:
            return None

    def _tfidf_search(self, query, top_k=10):
        """Original TF-IDF based search (used as fallback)."""
        if not self.entries or not query.strip():
            return []

        query_tokens = _tokenize(query)
        query_tf = Counter(query_tokens)
        query_magnitude = math.sqrt(sum(v * v for v in query_tf.values()))
        if query_magnitude == 0:
            return []

        query_vec = {w: v / query_magnitude for w, v in query_tf.items()}

        scored = []
        for entry in self.entries:
            if not entry.get("is_active", True):
                continue

            text = _search_text(entry)
            doc_tokens = _tokenize(text)
            doc_tf = Counter(doc_tokens)
            doc_magnitude = math.sqrt(sum(v * v for v in doc_tf.values()))
            if doc_magnitude == 0:
                continue

            doc_vec = {w: v / doc_magnitude for w, v in doc_tf.items()}

            score = 0
            for w, qv in query_vec.items():
                if w in doc_vec:
                    idf = self._idf_cache.get(w, 1)
                    score += qv * doc_vec[w] * idf

            if score > 0:
                scored.append((entry, score))

        scored.sort(key=lambda x: -x[1])
        return scored[:top_k]

    def search(self, query, top_k=10):
        """Search knowledge entries. Uses FTS5 with TF-IDF fallback.

        Returns list of (entry, score) pairs, highest score first.
        """
        if not query.strip():
            return []

        # Try FTS5 first (fast, good ranking)
        results = self._ft_search(query, top_k)
        if results is not None:
            return results

        # Fall back to TF-IDF
        return self._tfidf_search(query, top_k)

    def get_categories(self):
        cats = set()
        for e in self.entries:
            if e.get("category"):
                cats.add(e["category"])
        return sorted(cats)

    def get_stats(self):
        by_category = Counter(e.get("category", "") for e in self.entries)
        return {
            "total": len(self.entries),
            "active": sum(
                1 for e in self.entries if e.get("is_active", True)
            ),
            "categories": self.get_categories(),
            "by_category": dict(by_category.most_common()),
        }

    def get_all_entries(self):
        return self.entries


# Global singleton
_store = None


def get_store():
    global _store
    if _store is None:
        # Migrate from JSON BEFORE initializing the store
        if os.path.exists(KB_FILE):
            _init_db()
            _migrate_from_json()
        _store = KnowledgeStore()
    return _store


def get_db():
    """Get the shared SQLite connection (for use by other modules)."""
    _init_db()
    return _get_db()
