"""Shared helpers: config, drafts, ledger, X API (OAuth 1.0a), GitHub API.

Standard library only so GitHub Actions needs no install step.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE_DIR = ROOT / "queue"
POSTED_DIR = QUEUE_DIR / "posted"
MEDIA_DIR = QUEUE_DIR / "media"
MAX_VIDEO_BYTES = 512 * 1024 * 1024   # X limit for tweet_video
LEDGER_PATH = ROOT / "ledger" / "posts.jsonl"
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

THREAD_SPLIT = "---8<---"
X_API = "https://api.x.com/2"
GH_API = "https://api.github.com"

REQUIRED_FIELDS = ("id", "type", "pillar", "product", "scheduled_at")


# --------------------------------------------------------------------------- time

def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_time(value: str) -> dt.datetime:
    v = str(value).strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    t = dt.datetime.fromisoformat(v)
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t.astimezone(dt.timezone.utc)


def iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- config

def load_config(path: Path = CONFIG_PATH) -> dict:
    return json.loads(Path(path).read_text())


# --------------------------------------------------------------------------- drafts

def _parse_value(raw: str):
    v = raw.strip()
    # strip trailing inline comment ("value   # note"), but not '#' inside text
    v = re.sub(r"\s+#.*$", "", v).strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [x.strip().strip("\"'") for x in inner.split(",") if x.strip()] if inner else []
    if v.lower() in ("true", "yes"):
        return True
    if v.lower() in ("false", "no"):
        return False
    return v


def parse_front_matter(text: str) -> tuple[dict, str]:
    """Parse a minimal YAML front-matter block (flat key: value pairs)."""
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing front-matter: file must start with '---'")
    meta: dict = {}
    for i in range(1, len(lines)):
        line = lines[i]
        if line.strip() == "---":
            body = "\n".join(lines[i + 1:]).strip("\n")
            return meta, body
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"bad front-matter line: {line!r}")
        key, raw = line.split(":", 1)
        meta[key.strip()] = _parse_value(raw)
    raise ValueError("unterminated front-matter: missing closing '---'")


@dataclass
class Draft:
    path: Path
    meta: dict
    body: str
    parts: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return str(self.meta.get("id", ""))

    @property
    def scheduled_at(self) -> dt.datetime:
        return parse_time(self.meta["scheduled_at"])

    @property
    def hold(self) -> bool:
        return bool(self.meta.get("hold", False))

    @property
    def media_path(self) -> Path | None:
        """Video attached to the first part: `media:` (repo-relative path) or queue/media/<id>.mp4 if present."""
        rel = self.meta.get("media")
        if rel:
            return ROOT / str(rel)
        guess = MEDIA_DIR / f"{self.id}.mp4"
        return guess if guess.exists() else None


def split_parts(body: str) -> list[str]:
    parts = [p.strip() for p in re.split(rf"^\s*{re.escape(THREAD_SPLIT)}\s*$", body, flags=re.M)]
    return [p for p in parts if p]


def load_draft(path: Path) -> Draft:
    meta, body = parse_front_matter(Path(path).read_text(encoding="utf-8"))
    return Draft(path=Path(path), meta=meta, body=body, parts=split_parts(body))


def draft_paths(queue_dir: Path = QUEUE_DIR) -> list[Path]:
    return sorted(p for p in Path(queue_dir).glob("*.md") if p.name.lower() != "readme.md")


# --------------------------------------------------------------------------- text rules

# twitter-text v3 weighting: these ranges count 1, everything else 2.
_LIGHT_RANGES = ((0, 4351), (8192, 8205), (8208, 8223), (8242, 8247))
URL_RE = re.compile(
    r"(https?://|www\.)\S+|\b[a-z0-9-]+\.(com|net|org|io|ai|app|gg|xyz|co|dev|me|ly|game|games)\b(/\S*)?",
    re.I,
)


def weighted_length(text: str) -> int:
    n = 0
    for ch in text:
        cp = ord(ch)
        n += 1 if any(lo <= cp <= hi for lo, hi in _LIGHT_RANGES) else 2
    return n


def has_url(text: str) -> bool:
    return bool(URL_RE.search(text))


def validate_draft(d: Draft, cfg: dict) -> list[str]:
    """Structural checks for one draft. Returns a list of error strings."""
    errs: list[str] = []
    for f in REQUIRED_FIELDS:
        if f not in d.meta or d.meta[f] in ("", None):
            errs.append(f"missing field '{f}'")
    if d.id and d.id != d.path.stem:
        errs.append(f"id '{d.id}' must equal filename '{d.path.stem}'")
    typ = d.meta.get("type")
    if typ and typ not in ("original", "thread"):
        errs.append(f"type must be original|thread, got '{typ}'")
    if d.meta.get("pillar") and d.meta["pillar"] not in cfg["pillars"]:
        errs.append(f"pillar '{d.meta['pillar']}' not in {cfg['pillars']}")
    if d.meta.get("product") and d.meta["product"] not in cfg["products"]:
        errs.append(f"product '{d.meta['product']}' not in {cfg['products']}")
    if "scheduled_at" in d.meta:
        try:
            d.scheduled_at
        except ValueError:
            errs.append(f"scheduled_at not ISO-8601: {d.meta['scheduled_at']!r}")
    if not d.parts:
        errs.append("post body is empty")
    if typ == "original" and len(d.parts) > 1:
        errs.append(f"type original has {len(d.parts)} parts; use type: thread")
    if len(d.parts) > cfg["max_thread_parts"]:
        errs.append(f"{len(d.parts)} parts > max {cfg['max_thread_parts']}")
    if d.meta.get("persona") == "bot" and d.parts and not d.parts[0].startswith("bot: "):
        errs.append("persona: bot posts must start with 'bot: ' (see brain/persona.md)")
    elif d.meta.get("persona") not in (None, "", "bot"):
        errs.append(f"persona must be 'bot' or empty, got '{d.meta['persona']}'")
    m = d.media_path
    if d.meta.get("media") and (m is None or not m.is_file()):
        errs.append(f"media file not found: {d.meta['media']}")
    elif m is not None:
        if m.suffix.lower() != ".mp4":
            errs.append(f"media must be .mp4, got {m.suffix}")
        elif m.stat().st_size > MAX_VIDEO_BYTES:
            errs.append(f"media is {m.stat().st_size // 1_000_000} MB (> 512 MB)")
        elif m.stat().st_size == 0:
            errs.append("media file is empty")
    for i, p in enumerate(d.parts, 1):
        n = weighted_length(p)
        if n > 280:
            errs.append(f"part {i} is {n} weighted chars (> 280)")
        if has_url(p):
            errs.append(f"part {i} contains a URL (links cost ~13x and belong in bio/pinned post)")
        if "TODO" in p:
            errs.append(f"part {i} still contains a TODO marker")
    return errs


# --------------------------------------------------------------------------- ledger

def load_ledger(path: Path = LEDGER_PATH) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def write_ledger(entries: list[dict], path: Path = LEDGER_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries), encoding="utf-8")
    tmp.replace(p)


def append_ledger(entry: dict, path: Path = LEDGER_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# --------------------------------------------------------------------------- OAuth 1.0a

def _enc(s) -> str:
    return urllib.parse.quote(str(s), safe="")


@dataclass
class XCreds:
    api_key: str
    api_secret: str
    access_token: str
    access_secret: str

    @classmethod
    def from_env(cls) -> "XCreds | None":
        vals = [os.environ.get(k, "").strip() for k in
                ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")]
        return cls(*vals) if all(vals) else None


def oauth1_signature(method: str, url: str, params: dict, consumer_secret: str, token_secret: str) -> str:
    pairs = sorted((_enc(k), _enc(v)) for k, v in params.items())
    param_str = "&".join(f"{k}={v}" for k, v in pairs)
    base = "&".join([method.upper(), _enc(url), _enc(param_str)])
    key = f"{_enc(consumer_secret)}&{_enc(token_secret)}"
    digest = hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def oauth1_header(method: str, url: str, query: dict, creds: XCreds,
                  nonce: str | None = None, timestamp: str | None = None) -> str:
    oauth = {
        "oauth_consumer_key": creds.api_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp or str(int(time.time())),
        "oauth_token": creds.access_token,
        "oauth_version": "1.0",
    }
    # JSON bodies are not part of the signature base string; query params are.
    sig = oauth1_signature(method, url, {**query, **oauth}, creds.api_secret, creds.access_secret)
    oauth["oauth_signature"] = sig
    return "OAuth " + ", ".join(f'{_enc(k)}="{_enc(v)}"' for k, v in sorted(oauth.items()))


class XError(RuntimeError):
    def __init__(self, status: int, body: str):
        super().__init__(f"X API HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body


def x_request(method: str, path: str, creds: XCreds, query: dict | None = None, body: dict | None = None) -> dict:
    return x_request_full(method, path, creds, query, body)[0]


def x_request_full(method: str, path: str, creds: XCreds, query: dict | None = None,
                   body: dict | None = None) -> tuple[dict, dict]:
    """Like x_request but also returns response headers (lower-cased keys)."""
    url = f"{X_API}{path}"
    query = query or {}
    full = url + ("?" + urllib.parse.urlencode(query, quote_via=urllib.parse.quote) if query else "")
    headers = {"Authorization": oauth1_header(method, url, query, creds), "User-Agent": "x-bot-publisher"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(full, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return json.loads(resp.read().decode() or "{}"), headers
    except urllib.error.HTTPError as e:
        raise XError(e.code, e.read().decode(errors="replace")) from None


# --------------------------------------------------------------------------- video upload (X API v2 chunked)

CHUNK_BYTES = 4 * 1024 * 1024


def _multipart(fields: dict, file_field: str, filename: str, data: bytes) -> tuple[bytes, str]:
    boundary = secrets.token_hex(16)
    out = b""
    for k, v in fields.items():
        out += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    out += (f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n").encode() + data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return out, f"multipart/form-data; boundary={boundary}"


def _x_multipart(path: str, creds: XCreds, fields: dict, filename: str, data: bytes) -> None:
    url = f"{X_API}{path}"
    body, ctype = _multipart(fields, "media", filename, data)
    headers = {"Authorization": oauth1_header("POST", url, {}, creds), "Content-Type": ctype,
               "User-Agent": "x-bot-publisher"}
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        raise XError(e.code, e.read().decode(errors="replace")) from None


def _media_id(resp: dict) -> str:
    d = resp.get("data", resp)
    return str(d.get("id") or d.get("media_id_string") or d["media_id"])


def upload_video(path: Path, creds: XCreds, sleep=time.sleep, max_wait_s: int = 300) -> str:
    """Upload an mp4 with the v2 chunked flow (initialize -> append -> finalize -> poll). Returns the media id."""
    data = Path(path).read_bytes()
    init = x_request("POST", "/media/upload/initialize", creds,
                     body={"media_type": "video/mp4", "total_bytes": len(data), "media_category": "tweet_video"})
    mid = _media_id(init)
    for i, off in enumerate(range(0, len(data), CHUNK_BYTES)):
        _x_multipart(f"/media/upload/{mid}/append", creds, {"segment_index": i}, Path(path).name,
                     data[off:off + CHUNK_BYTES])
    fin = x_request("POST", f"/media/upload/{mid}/finalize", creds)
    info = fin.get("data", fin).get("processing_info")
    waited = 0
    while info and info.get("state") in ("pending", "in_progress"):
        if waited > max_wait_s:
            raise RuntimeError(f"video {mid} still processing after {max_wait_s}s")
        wait = int(info.get("check_after_secs", 5))
        sleep(wait)
        waited += wait
        st = x_request("GET", "/media/upload", creds, query={"command": "STATUS", "media_id": mid})
        info = st.get("data", st).get("processing_info")
    if info and info.get("state") == "failed":
        raise RuntimeError(f"video processing failed: {info.get('error', info)}")
    return mid


# --------------------------------------------------------------------------- GitHub approval check

def last_commit_for(path: Path) -> str | None:
    rel = os.path.relpath(path, ROOT)
    out = subprocess.run(["git", "log", "-1", "--format=%H", "--", rel],
                         cwd=ROOT, capture_output=True, text=True, check=False)
    sha = out.stdout.strip()
    return sha or None


def merged_pr_for_commit(sha: str, repo: str, token: str, base: str = "main") -> int | None:
    """Return the number of a merged PR into `base` that contains commit `sha`, else None."""
    req = urllib.request.Request(
        f"{GH_API}/repos/{repo}/commits/{sha}/pulls",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "User-Agent": "x-bot-publisher"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        prs = json.loads(resp.read().decode())
    for pr in prs:
        if pr.get("merged_at") and pr.get("base", {}).get("ref") == base:
            return pr["number"]
    return None
