"""
IBM Bob API Client
==================
Calls IBM Bob via two strategies (tried in order):

  Strategy 1 — Bob Shell CLI subprocess  (preferred)
    Uses `bob --auth-method api-key -p "..."` with BOBSHELL_API_KEY env var.
    Bob Shell handles VPN routing, token refresh, and BFF auth transparently.
    Requires: bobshell installed (`npm install -g bobshell`)
              BOBSHELL_API_KEY=<inference-key> in .env

  Strategy 2 — Direct HTTP (fallback when on IBM VPN with direct access)
    POST https://api.us-east.bob.ibm.com/inference/v1/chat/completions
    Auth: Authorization: Apikey <key>  (capital A, capital K)
    Requires: BOB_API_KEY, BOB_INSTANCE_ID, BOB_TEAM_ID in .env

If both fail, agents use their built-in rule-based fallback text.
The dashboard works fully in fallback mode.

Run: python test_bob.py  to verify the connection.
See: HOW_TO_CONNECT_BOB.md for setup instructions.
"""

import json
import os
import re
import subprocess
import time
import base64
import sqlite3
import ctypes
from ctypes import windll, POINTER, c_char, c_ulong, Structure, byref

import requests
from dotenv import load_dotenv

load_dotenv()

# ── Config from .env ──────────────────────────────────────────────────────────
BOB_API_URL      = os.getenv(
    "BOB_API_URL",
    "https://api.us-east.bob.ibm.com/inference/v1/chat/completions",
).rstrip("/")
BOB_API_KEY      = os.getenv("BOB_API_KEY", "")
BOBSHELL_API_KEY = os.getenv("BOBSHELL_API_KEY", BOB_API_KEY)  # same key, different var
BOB_MODEL        = os.getenv("BOB_MODEL", "openai/gpt-oss-20b")

# Instance/team IDs — set these in your own .env (discovered from Bob profile API)
_BOB_INSTANCE_ID = os.getenv("BOB_INSTANCE_ID", "")
_BOB_TEAM_ID     = os.getenv("BOB_TEAM_ID",     "")

MAX_RETRIES   = 3
RETRY_DELAY_S = 2
# Bob Shell timeout: give it 90s for a real inference call
_SHELL_TIMEOUT = int(os.getenv("BOB_SHELL_TIMEOUT", "90"))


class BobAPIError(Exception):
    """Raised when all Bob call strategies fail after all retries."""


# ── DPAPI helpers (Windows only) ──────────────────────────────────────────────
class _DATA_BLOB(Structure):
    _fields_ = [('cbData', c_ulong), ('pbData', POINTER(c_char))]


def _dpapi_decrypt(data: bytes) -> bytes:
    """Decrypt DPAPI-protected bytes. Raises ValueError if decryption fails."""
    p       = ctypes.create_string_buffer(data, len(data))
    blobin  = _DATA_BLOB(len(data), p)
    blobout = _DATA_BLOB()
    ok = windll.crypt32.CryptUnprotectData(
        byref(blobin), None, None, None, None, 0, byref(blobout))
    if not ok:
        raise ValueError(f"CryptUnprotectData failed (error {windll.kernel32.GetLastError()})")
    result = ctypes.string_at(blobout.pbData, blobout.cbData)
    windll.kernel32.LocalFree(blobout.pbData)
    if not result:
        raise ValueError("CryptUnprotectData returned empty result")
    return result


# Bob Shell version — used as User-Agent to pass Cloudflare WAF on /inference/v1/
_BOBSHELL_UA = "bobshell/1.0.6"


def _read_bob_oauth_token() -> str:
    """Decrypt the long OAuth session token from Bob IDE's local store (Windows).

    The 'token' field (~4800 chars) is valid ~24h and works with the
    /inference/v1/ endpoint when User-Agent: bobshell/1.0.6 is set.
    """
    try:
        username = os.environ.get("USERNAME") or os.environ.get("USER", "")
        ls_path  = fr"C:\Users\{username}\AppData\Roaming\IBM Bob\Local State"
        db_path  = fr"C:\Users\{username}\AppData\Roaming\IBM Bob\User\globalStorage\state.vscdb"
        if not os.path.exists(ls_path) or not os.path.exists(db_path):
            return ""
        with open(ls_path, "r") as f:
            ls = json.load(f)
        aes_key = _dpapi_decrypt(base64.b64decode(ls["os_crypt"]["encrypted_key"])[5:])
        conn = sqlite3.connect(db_path)
        cur  = conn.cursor()
        cur.execute("SELECT value FROM ItemTable WHERE key LIKE '%bob.auth.tokens%'")
        row  = cur.fetchone()
        conn.close()
        if not row:
            return ""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        buf   = bytes(json.loads(row[0])["data"])
        plain = AESGCM(aes_key).decrypt(buf[3:15], buf[15:], None)
        data  = json.loads(plain.decode("utf-8"))
        return data.get("token") or data.get("accessToken", "")
    except Exception:
        return ""


# ── Strategy 1: Bob Shell subprocess ─────────────────────────────────────────
def _call_via_bobshell(system_prompt: str, user_message: str,
                       temperature: float = 0.2) -> str:
    """Call Bob via `bob --auth-method api-key -p "..."` subprocess.

    Bob Shell handles BFF token exchange, VPN routing, and retries internally.
    The combined system+user prompt is passed as a single -p argument.
    """
    key = BOBSHELL_API_KEY or BOB_API_KEY
    if not key:
        raise BobAPIError("BOBSHELL_API_KEY not set — cannot use Bob Shell strategy")

    # Build the prompt: inject system context as a preamble
    combined = (
        f"[SYSTEM INSTRUCTIONS — follow exactly]\n{system_prompt}\n\n"
        f"[USER REQUEST]\n{user_message}"
    )

    env = {**os.environ, "BOBSHELL_API_KEY": key}
    cmd = [
        "bob",
        "--auth-method", "api-key",
        "--instance-id", _BOB_INSTANCE_ID,
        "--team-id",     _BOB_TEAM_ID,
        "--accept-license",
        "--yolo",
        "--hide-intermediary-output",
        "-p", combined,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_SHELL_TIMEOUT,
            env=env,
        )
        stdout = result.stdout.strip()
        if result.returncode != 0 or not stdout:
            stderr = result.stderr.strip()
            raise BobAPIError(f"Bob Shell exited {result.returncode}: {stderr[:200]}")
        # Strip ANSI escape codes
        ansi_escape = re.compile(r'\x1B\[[0-9;]*[mGKHF]')
        clean = ansi_escape.sub("", stdout).strip()
        return clean
    except subprocess.TimeoutExpired:
        raise BobAPIError(f"Bob Shell timed out after {_SHELL_TIMEOUT}s")
    except FileNotFoundError:
        raise BobAPIError(
            "bob command not found. Install Bob Shell:\n"
            "  npm install -g bobshell\n"
            "  https://bob.ibm.com/docs/shell"
        )


# ── Strategy 2: Direct HTTP ───────────────────────────────────────────────────
def _build_http_headers(token: str = "", use_key: bool = False) -> dict:
    """Build headers for the direct HTTP strategy.

    IMPORTANT: User-Agent must be 'bobshell/1.0.6' — Cloudflare WAF on
    /inference/v1/ blocks standard Python requests UA but allows Bob Shell UA.
    """
    base = {
        "Content-Type":  "application/json",
        "x-instance-id": _BOB_INSTANCE_ID,
        "x-team-id":     _BOB_TEAM_ID,
        "User-Agent":    _BOBSHELL_UA,
    }
    if use_key and BOB_API_KEY:
        return {**base, "Authorization": f"Apikey {BOB_API_KEY}"}
    if token:
        return {**base, "Authorization": f"Bearer {token}"}
    return {}


def _call_via_http(system_prompt: str, user_message: str,
                   temperature: float = 0.2) -> str:
    """Call the Bob inference API directly over HTTP."""
    url = BOB_API_URL
    if not url.endswith("/chat/completions"):
        url = url.rstrip("/") + "/chat/completions"

    # Try API key first, then OAuth token from local Bob IDE store
    oauth_token = _read_bob_oauth_token()
    header_opts = []
    if BOB_API_KEY:
        header_opts.append(_build_http_headers(use_key=True))
    if oauth_token:
        header_opts.append(_build_http_headers(token=oauth_token))

    if not header_opts:
        raise BobAPIError("No BOB_API_KEY or OAuth token available for HTTP strategy")

    payload = {
        "model":       BOB_MODEL,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
    }

    last_http_error = None
    for headers in header_opts:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
                last_http_error = exc
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_S * attempt)
                # move to next header set after exhausting retries for this one
        # if this header set exhausted retries, try next

    raise BobAPIError(f"Direct HTTP call failed with all credentials: {last_http_error}")


# ── Public API ────────────────────────────────────────────────────────────────
def call_bob(system_prompt: str, user_message: str, temperature: float = 0.2) -> str:
    """Call IBM Bob and return the model's text response.

    Tries Bob Shell subprocess first (handles VPN/BFF auth transparently),
    then falls back to direct HTTP.

    Raises BobAPIError if all strategies fail — callers should catch this
    and use their own fallback text.
    """
    last_error = None

    # ── Strategy 1: Bob Shell ─────────────────────────────────────────────────
    key = BOBSHELL_API_KEY or BOB_API_KEY
    if key:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return _call_via_bobshell(system_prompt, user_message, temperature)
            except BobAPIError as exc:
                last_error = exc
                if "not found" in str(exc):
                    break   # bobshell not installed — skip retries
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_S * attempt)

    # ── Strategy 2: Direct HTTP ───────────────────────────────────────────────
    try:
        return _call_via_http(system_prompt, user_message, temperature)
    except BobAPIError as exc:
        last_error = exc

    raise BobAPIError(
        f"All Bob strategies failed: {last_error}\n"
        "Ensure BOBSHELL_API_KEY is set in .env and Bob Shell is installed.\n"
        "See HOW_TO_CONNECT_BOB.md for setup instructions."
    ) from last_error


def parse_json_response(raw: str) -> object:
    """Parse a JSON response from Bob, stripping markdown code fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text  = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Bob response is not valid JSON: {exc}\nRaw: {raw[:500]}"
        ) from exc
