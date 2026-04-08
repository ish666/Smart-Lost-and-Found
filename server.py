"""
Smart Lost & Found System
Zero external dependencies — runs with plain Python 3.8+

Usage:
    python server.py

Then open: http://localhost:8000
API docs:  http://localhost:8000/api
"""

import base64
import hashlib
import hmac
import http.server
import json
import mimetypes
import os
import re
import sqlite3
import time
import urllib.parse
from datetime import datetime, timezone

# ─── CONFIG ──────────────────────────────────────────────────────────────────
HOST        = "0.0.0.0"
PORT = int(os.environ.get("PORT", 10000))
SECRET_KEY  = "change-this-secret-in-production"
TOKEN_TTL   = 3600          # seconds (1 hour)
DB_PATH     = "lostfound.db"
UPLOAD_DIR  = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

CATEGORIES = ["Electronics", "Clothing", "Accessories", "Books", "Keys", "Sports", "Other"]
ITEM_STATUSES  = ["active", "approved", "rejected", "returned", "closed"]
QUERY_STATUSES = ["pending", "in_progress", "resolved"]


# ═══════════════════════════════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            email       TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'user',
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS lost_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            name        TEXT NOT NULL,
            description TEXT,
            category    TEXT,
            location    TEXT,
            date_lost   TEXT,
            image_path  TEXT,
            status      TEXT NOT NULL DEFAULT 'active',
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS found_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            name        TEXT NOT NULL,
            description TEXT,
            category    TEXT,
            location    TEXT,
            date_found  TEXT,
            image_path  TEXT,
            status      TEXT NOT NULL DEFAULT 'active',
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS queries (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL REFERENCES users(id),
            item_id        INTEGER NOT NULL REFERENCES lost_items(id),
            message        TEXT NOT NULL,
            admin_response TEXT,
            status         TEXT NOT NULL DEFAULT 'pending',
            created_at     TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    # Seed admin if none exists
    row = c.execute("SELECT id FROM users WHERE role='admin'").fetchone()
    if not row:
        pwd = hash_password("admin123")
        c.execute(
            "INSERT INTO users(name, email, password, role) VALUES (?,?,?,?)",
            ("Admin", "admin@lostfound.com", pwd, "admin")
        )
        print("✅  Default admin → email: admin@lostfound.com  password: admin123")
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  AUTH  (HMAC-SHA256 "JWT-like" tokens — no PyJWT needed)
# ═══════════════════════════════════════════════════════════════════════════════

def hash_password(plain: str) -> str:
    salt = os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 260_000)
    return f"{salt}${h.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    try:
        salt, h_hex = stored.split("$", 1)
        h = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 260_000)
        return hmac.compare_digest(h.hex(), h_hex)
    except Exception:
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _sign(msg: str) -> str:
    return _b64(hmac.new(SECRET_KEY.encode(), msg.encode(), hashlib.sha256).digest())


def create_token(user_id: int) -> str:
    header  = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64(json.dumps({"sub": user_id, "exp": int(time.time()) + TOKEN_TTL}).encode())
    sig     = _sign(f"{header}.{payload}")
    return f"{header}.{payload}.{sig}"


def decode_token(token: str):
    """Returns user_id int or None."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header, payload, sig = parts
        if not hmac.compare_digest(sig, _sign(f"{header}.{payload}")):
            return None
        pad = "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload + pad))
        if data.get("exp", 0) < time.time():
            return None
        return data["sub"]
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  SMART MATCHING ALGORITHM
# ═══════════════════════════════════════════════════════════════════════════════

def _tokens(text: str) -> set:
    if not text:
        return set()
    return set(re.sub(r"[^\w\s]", " ", text.lower()).split())


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def match_items(lost: dict, found_items: list, threshold: float = 0.12) -> list:
    results = []
    ln = _tokens(lost.get("name", ""))
    ld = _tokens(lost.get("description", ""))
    lc = (lost.get("category") or "").lower().strip()

    for fi in found_items:
        fn = _tokens(fi.get("name", ""))
        fd = _tokens(fi.get("description", ""))
        fc = (fi.get("category") or "").lower().strip()

        name_score = _jaccard(ln, fn)
        desc_score = _jaccard(ld, fd)
        score = name_score * 0.45 + desc_score * 0.35

        reasons = []
        if name_score > 0.25:
            common = ln & fn
            reasons.append(f"Name match ({name_score:.0%}): shared words {list(common)[:4]}")
        if desc_score > 0.18:
            common = ld & fd
            reasons.append(f"Description overlap ({desc_score:.0%}): {list(common)[:5]}")
        if lc and fc:
            if lc == fc:
                score += 0.20
                reasons.append(f"Exact category: '{lc}'")
            elif lc in fc or fc in lc:
                score += 0.10
                reasons.append(f"Partial category: '{lc}' ↔ '{fc}'")

        if score >= threshold:
            results.append({**fi, "_score": round(score, 4), "_reasons": reasons})

    results.sort(key=lambda x: x["_score"], reverse=True)
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  HTTP SERVER
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_multipart(body: bytes, boundary: str):
    """Parse multipart/form-data into {field: value} and {field: (filename, bytes)}."""
    fields, files = {}, {}
    boundary_bytes = ("--" + boundary).encode()
    parts = body.split(boundary_bytes)
    for part in parts[1:]:
        if part in (b"--\r\n", b"--"):
            break
        if part.startswith(b"\r\n"):
            part = part[2:]
        if b"\r\n\r\n" not in part:
            continue
        headers_raw, content = part.split(b"\r\n\r\n", 1)
        if content.endswith(b"\r\n"):
            content = content[:-2]
        headers_str = headers_raw.decode("utf-8", errors="replace")
        cd = {}
        for line in headers_str.split("\r\n"):
            if line.lower().startswith("content-disposition:"):
                for seg in line.split(";"):
                    seg = seg.strip()
                    if "=" in seg:
                        k, v = seg.split("=", 1)
                        cd[k.strip().lower()] = v.strip().strip('"')
        name = cd.get("name", "")
        filename = cd.get("filename")
        if filename:
            files[name] = (filename, content)
        else:
            fields[name] = content.decode("utf-8", errors="replace")
    return fields, files


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  {self.command} {self.path} → {args[1] if len(args)>1 else ''}")

    # ── helpers ──────────────────────────────────────────────────────────────
    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def _json_body(self):
        try:
            return json.loads(self._body())
        except Exception:
            return {}

    def _auth_user(self):
        auth = self.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        uid = decode_token(token)
        if uid is None:
            return None
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        conn.close()
        return dict(user) if user else None

    def _send(self, code: int, data, headers: dict = None):
        body = json.dumps(data, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
        if headers:
            for k, v in headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _ok(self, data):   self._send(200, data)
    def _created(self, d): self._send(201, d)
    def _err(self, code, msg): self._send(code, {"detail": msg})

    def _require_auth(self):
        user = self._auth_user()
        if not user:
            self._err(401, "Not authenticated")
        return user

    def _require_admin(self):
        user = self._require_auth()
        if user and user["role"] != "admin":
            self._err(403, "Admin access required")
            return None
        return user

    # ── routing ──────────────────────────────────────────────────────────────
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
        self.end_headers()

    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/")
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

        # Static frontend
        if p == "" or p == "/":
            return self._serve_file("frontend/index.html")
        if p.startswith("/uploads/"):
            return self._serve_file(p.lstrip("/"))
        if p.startswith("/frontend/"):
            return self._serve_file(p.lstrip("/"))

        # API
        if p == "/api":               return self._api_info()
        if p == "/health":            return self._ok({"status": "ok"})
        if p == "/me":                return self._get_me()
        if p == "/items/lost":        return self._list_items("lost")
        if p == "/items/found":       return self._list_items("found")
        if p == "/search":            return self._search(qs)
        if p == "/queries":           return self._my_queries()
        if re.match(r"^/queries/\d+$", p): return self._get_query(int(p.split("/")[-1]))
        if re.match(r"^/match/\d+$",  p): return self._get_matches(int(p.split("/")[-1]))
        if p == "/admin/items/lost":  return self._admin_items("lost")
        if p == "/admin/items/found": return self._admin_items("found")
        if p == "/admin/queries":     return self._admin_queries()
        if p == "/admin/analytics":   return self._admin_analytics()
        if p == "/admin/users":       return self._admin_users()
        self._err(404, "Not found")

    def do_POST(self):
        p = self.path.split("?")[0].rstrip("/")
        if p == "/register":          return self._register()
        if p == "/login":             return self._login()
        if p == "/report-lost":       return self._report_item("lost")
        if p == "/report-found":      return self._report_item("found")
        if p == "/query":             return self._create_query()
        if p == "/admin/respond-query": return self._admin_respond_query()
        self._err(404, "Not found")

    def do_PUT(self):
        p = self.path.split("?")[0].rstrip("/")
        if p == "/admin/update-status": return self._admin_update_status()
        self._err(404, "Not found")

    # ── static file server ───────────────────────────────────────────────────
    def _serve_file(self, path: str):
        if ".." in path:
            return self._err(403, "Forbidden")
        if not os.path.isfile(path):
            return self._err(404, f"File not found: {path}")
        mime, _ = mimetypes.guess_type(path)
        mime = mime or "application/octet-stream"
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _api_info(self):
        self._ok({
            "name": "Smart Lost & Found API",
            "version": "2.0",
            "endpoints": {
                "auth":  ["POST /register", "POST /login", "GET /me"],
                "items": ["POST /report-lost", "POST /report-found",
                          "GET /items/lost", "GET /items/found",
                          "GET /search?keyword=&category=&item_type=",
                          "GET /match/{lost_item_id}"],
                "queries": ["POST /query", "GET /queries", "GET /queries/{id}"],
                "admin": ["GET /admin/items/lost", "GET /admin/items/found",
                          "PUT /admin/update-status", "GET /admin/queries",
                          "POST /admin/respond-query", "GET /admin/analytics",
                          "GET /admin/users"],
            }
        })

    # ─────────────────────────────────────────────────────────────────────────
    #  AUTH
    # ─────────────────────────────────────────────────────────────────────────
    def _register(self):
        d = self._json_body()
        name  = (d.get("name") or "").strip()
        email = (d.get("email") or "").strip().lower()
        pw    = d.get("password", "")
        if not name or not email or not pw:
            return self._err(400, "name, email and password are required")
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return self._err(400, "Invalid email format")
        if len(pw) < 6:
            return self._err(400, "Password must be at least 6 characters")
        conn = get_db()
        if conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
            conn.close(); return self._err(409, "Email already registered")
        cur = conn.execute(
            "INSERT INTO users(name,email,password) VALUES(?,?,?)",
            (name, email, hash_password(pw))
        )
        user = conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
        conn.commit(); conn.close()
        self._created(_user_out(user))

    def _login(self):
        d = self._json_body()
        email = (d.get("email") or "").strip().lower()
        pw    = d.get("password", "")
        conn  = get_db()
        user  = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        if not user or not verify_password(pw, user["password"]):
            return self._err(401, "Invalid email or password")
        token = create_token(user["id"])
        self._ok({"access_token": token, "token_type": "bearer", "user": _user_out(user)})

    def _get_me(self):
        user = self._require_auth()
        if user: self._ok(_user_out(user))

    # ─────────────────────────────────────────────────────────────────────────
    #  ITEMS
    # ─────────────────────────────────────────────────────────────────────────
    def _report_item(self, itype: str):
        user = self._require_auth()
        if not user: return

        ct = self.headers.get("Content-Type", "")
        if "multipart/form-data" in ct:
            boundary = ct.split("boundary=")[-1].strip()
            fields, files = _parse_multipart(self._body(), boundary)
        else:
            fields = self._json_body()
            files  = {}

        name = (fields.get("name") or "").strip()
        if not name:
            return self._err(400, "name is required")

        image_path = None
        if "image" in files:
            fname, fdata = files["image"]
            ext = os.path.splitext(fname)[-1].lower()
            if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
                return self._err(400, "Invalid image format")
            import uuid
            safe = f"{uuid.uuid4()}{ext}"
            fpath = os.path.join(UPLOAD_DIR, safe)
            with open(fpath, "wb") as f:
                f.write(fdata)
            image_path = fpath

        conn = get_db()
        if itype == "lost":
            cur = conn.execute(
                "INSERT INTO lost_items(user_id,name,description,category,location,date_lost,image_path)"
                " VALUES(?,?,?,?,?,?,?)",
                (user["id"], name, fields.get("description"), fields.get("category"),
                 fields.get("location"), fields.get("date_lost"), image_path)
            )
            row = conn.execute("SELECT * FROM lost_items WHERE id=?", (cur.lastrowid,)).fetchone()
        else:
            cur = conn.execute(
                "INSERT INTO found_items(user_id,name,description,category,location,date_found,image_path)"
                " VALUES(?,?,?,?,?,?,?)",
                (user["id"], name, fields.get("description"), fields.get("category"),
                 fields.get("location"), fields.get("date_found"), image_path)
            )
            row = conn.execute("SELECT * FROM found_items WHERE id=?", (cur.lastrowid,)).fetchone()
        conn.commit(); conn.close()
        self._created(dict(row))

    def _list_items(self, itype: str):
        user = self._require_auth()
        if not user: return
        table = "lost_items" if itype == "lost" else "found_items"
        conn = get_db()
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY created_at DESC").fetchall()
        conn.close()
        self._ok([dict(r) for r in rows])

    def _search(self, qs: dict):
        user = self._require_auth()
        if not user: return
        keyword   = (qs.get("keyword",   [""])[0] or "").strip()
        category  = (qs.get("category",  [""])[0] or "").strip()
        item_type = (qs.get("item_type", [""])[0] or "").strip()

        conn = get_db()
        results = {"lost": [], "found": []}

        def _q(table):
            sql = f"SELECT * FROM {table} WHERE 1=1"
            params = []
            if keyword:
                sql += " AND (name LIKE ? OR description LIKE ? OR location LIKE ?)"
                params += [f"%{keyword}%"] * 3
            if category:
                sql += " AND category LIKE ?"
                params.append(f"%{category}%")
            sql += " ORDER BY created_at DESC"
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

        if item_type != "found":
            results["lost"]  = _q("lost_items")
        if item_type != "lost":
            results["found"] = _q("found_items")
        conn.close()
        self._ok(results)

    def _get_matches(self, lost_id: int):
        user = self._require_auth()
        if not user: return
        conn = get_db()
        lost = conn.execute("SELECT * FROM lost_items WHERE id=?", (lost_id,)).fetchone()
        if not lost:
            conn.close(); return self._err(404, "Lost item not found")
        found = [dict(r) for r in conn.execute("SELECT * FROM found_items").fetchall()]
        conn.close()
        matches = match_items(dict(lost), found)
        self._ok({"lost_item": dict(lost), "matches": matches})

    # ─────────────────────────────────────────────────────────────────────────
    #  QUERIES
    # ─────────────────────────────────────────────────────────────────────────
    def _create_query(self):
        user = self._require_auth()
        if not user: return
        d = self._json_body()
        item_id = d.get("item_id")
        message = (d.get("message") or "").strip()
        if not item_id or not message:
            return self._err(400, "item_id and message are required")
        conn = get_db()
        if not conn.execute("SELECT id FROM lost_items WHERE id=?", (item_id,)).fetchone():
            conn.close(); return self._err(404, "Lost item not found")
        cur = conn.execute(
            "INSERT INTO queries(user_id,item_id,message) VALUES(?,?,?)",
            (user["id"], item_id, message)
        )
        row = conn.execute("SELECT * FROM queries WHERE id=?", (cur.lastrowid,)).fetchone()
        conn.commit(); conn.close()
        self._created(dict(row))

    def _my_queries(self):
        user = self._require_auth()
        if not user: return
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM queries WHERE user_id=? ORDER BY created_at DESC", (user["id"],)
        ).fetchall()
        conn.close()
        self._ok([dict(r) for r in rows])

    def _get_query(self, qid: int):
        user = self._require_auth()
        if not user: return
        conn = get_db()
        q = conn.execute("SELECT * FROM queries WHERE id=?", (qid,)).fetchone()
        conn.close()
        if not q:
            return self._err(404, "Query not found")
        if q["user_id"] != user["id"] and user["role"] != "admin":
            return self._err(403, "Access denied")
        self._ok(dict(q))

    # ─────────────────────────────────────────────────────────────────────────
    #  ADMIN
    # ─────────────────────────────────────────────────────────────────────────
    def _admin_items(self, itype: str):
        user = self._require_admin()
        if not user: return
        table = "lost_items" if itype == "lost" else "found_items"
        conn = get_db()
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY created_at DESC").fetchall()
        conn.close()
        self._ok([dict(r) for r in rows])

    def _admin_update_status(self):
        user = self._require_admin()
        if not user: return
        d = self._json_body()
        itype  = d.get("item_type", "")
        iid    = d.get("item_id")
        status = d.get("status", "")
        if itype not in ("lost", "found"):
            return self._err(400, "item_type must be 'lost' or 'found'")
        if status not in ITEM_STATUSES:
            return self._err(400, f"status must be one of {ITEM_STATUSES}")
        table = "lost_items" if itype == "lost" else "found_items"
        conn = get_db()
        if not conn.execute(f"SELECT id FROM {table} WHERE id=?", (iid,)).fetchone():
            conn.close(); return self._err(404, "Item not found")
        conn.execute(f"UPDATE {table} SET status=? WHERE id=?", (status, iid))
        conn.commit(); conn.close()
        self._ok({"message": f"Status updated to '{status}'", "item_id": iid})

    def _admin_queries(self):
        user = self._require_admin()
        if not user: return
        conn = get_db()
        rows = conn.execute("SELECT * FROM queries ORDER BY created_at DESC").fetchall()
        conn.close()
        self._ok([dict(r) for r in rows])

    def _admin_respond_query(self):
        user = self._require_admin()
        if not user: return
        d      = self._json_body()
        qid    = d.get("query_id")
        resp   = (d.get("response") or "").strip()
        status = d.get("status", "in_progress")
        if not qid or not resp:
            return self._err(400, "query_id and response are required")
        if status not in QUERY_STATUSES:
            return self._err(400, f"status must be one of {QUERY_STATUSES}")
        conn = get_db()
        if not conn.execute("SELECT id FROM queries WHERE id=?", (qid,)).fetchone():
            conn.close(); return self._err(404, "Query not found")
        conn.execute(
            "UPDATE queries SET admin_response=?, status=? WHERE id=?",
            (resp, status, qid)
        )
        conn.commit(); conn.close()
        self._ok({"message": "Response recorded", "query_id": qid})

    def _admin_analytics(self):
        user = self._require_auth()   # allow any logged-in for home stats
        if not user: return
        conn = get_db()
        def cnt(sql): return conn.execute(sql).fetchone()[0]
        data = {
            "total_lost":     cnt("SELECT COUNT(*) FROM lost_items"),
            "total_found":    cnt("SELECT COUNT(*) FROM found_items"),
            "resolved_cases": cnt("SELECT COUNT(*) FROM lost_items WHERE status IN ('returned','closed')"),
            "active_cases":   cnt("SELECT COUNT(*) FROM lost_items WHERE status='active'") +
                              cnt("SELECT COUNT(*) FROM found_items WHERE status='active'"),
            "pending_queries":cnt("SELECT COUNT(*) FROM queries WHERE status='pending'"),
        }
        conn.close()
        self._ok(data)

    def _admin_users(self):
        user = self._require_admin()
        if not user: return
        conn = get_db()
        rows = conn.execute("SELECT id,name,email,role,created_at FROM users ORDER BY created_at DESC").fetchall()
        conn.close()
        self._ok([dict(r) for r in rows])


def _user_out(u) -> dict:
    d = dict(u)
    d.pop("password", None)
    return d


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    init_db()
    server = http.server.HTTPServer((HOST, PORT), Handler)
    print(f"""
╔══════════════════════════════════════════════════════╗
║       Smart Lost & Found System  v2.0               ║
╠══════════════════════════════════════════════════════╣
║  Frontend  →  http://localhost:{PORT}                  ║
║  API Info  →  http://localhost:{PORT}/api              ║
║  Health    →  http://localhost:{PORT}/health           ║
╠══════════════════════════════════════════════════════╣
║  Admin login:  admin@lostfound.com / admin123       ║
╚══════════════════════════════════════════════════════╝
Press Ctrl+C to stop
""")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
