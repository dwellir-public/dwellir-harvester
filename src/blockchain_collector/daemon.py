#!/usr/bin/env python3
# stdlib-only HTTP daemon that runs the configured collector and serves /metadata
import os
import sys
import json
import time
import shutil
import socket
import logging
import threading
import subprocess
from logging.handlers import RotatingFileHandler
from http.server import HTTPServer, BaseHTTPRequestHandler

SNAP = os.environ.get("SNAP", "")
SNAP_COMMON = os.environ.get("SNAP_COMMON", "/var/snap/blockchain-collector/common")
METADATA_PATH = os.path.join(SNAP_COMMON, "metadata.json")
LOG_PATH = os.path.join(SNAP_COMMON, "daemon.log")

# ---------- snapctl helper (NO LOGGING) ----------
def _snapctl_get_nolog(key: str, default=None):
    """Safe to call before logging is configured."""
    try:
        out = subprocess.check_output(["snapctl", "get", key], text=True).strip()
        if out == "":
            return default
        try:
            return json.loads(out)
        except Exception:
            return out
    except Exception:
        return default

# ---------- logging ----------
def _setup_logging():
    os.makedirs(SNAP_COMMON, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # temporary until we read level

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    # 1) Stream to stderr (captured by journald)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    # 2) Rotate to file in SNAP_COMMON
    fh = RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Read desired level without using logging
    lvl = _snapctl_get_nolog("log.level", "INFO")
    level_map = {"CRITICAL":50,"ERROR":40,"WARNING":30,"INFO":20,"DEBUG":10,"NOTSET":0}
    root.setLevel(level_map.get(str(lvl).upper(), 20))

_setup_logging()
log = logging.getLogger("collector-daemon")

# ---------- snapctl helper (WITH LOGGING) ----------
def _snapctl_get(key: str, default=None):
    try:
        log.debug("snapctl get %s", key)
        out = subprocess.check_output(["snapctl", "get", key], text=True).strip()
        log.debug("snapctl get %s -> %r", key, out)
        if out == "":
            return default
        try:
            return json.loads(out)
        except Exception:
            return out
    except FileNotFoundError as e:
        log.warning("snapctl not found (%s). Using default for %s=%r", e, key, default)
        return default
    except subprocess.CalledProcessError as e:
        log.warning("snapctl get %s failed (not set yet?): rc=%s stderr=%r", key, e.returncode, e.stderr)
        return default
    except Exception:
        log.exception("snapctl get %s crashed", key)
        return default

def _dump_startup_env():
    try:
        log.info("==== Startup environment dump ====")
        log.info("Python: %s", sys.version.replace("\n", " "))
        log.info("Executable: %s", sys.executable)
        log.info("CWD: %s", os.getcwd())
        log.info("EUID: %s", os.geteuid() if hasattr(os, "geteuid") else "n/a")
        log.info("User: %s", os.environ.get("USER", "n/a"))
        log.info("Hostname: %s", socket.gethostname())
        for k in sorted([k for k in os.environ if k.startswith("SNAP")]):
            log.info("%s=%s", k, os.environ[k])
        log.info("PATH=%s", os.environ.get("PATH", ""))
        log.info("METADATA_PATH=%s", METADATA_PATH)
        log.info("LOG_PATH=%s", LOG_PATH)
        # sanity checks
        for path in [SNAP, SNAP_COMMON, os.path.dirname(METADATA_PATH)]:
            if path:
                try:
                    st = os.stat(path)
                    log.info("stat(%s): mode=%o uid=%s gid=%s", path, st.st_mode & 0o777, st.st_uid, st.st_gid)
                except Exception as e:
                    log.warning("stat(%s) failed: %s", path, e)
        # helpful "which"
        for name in ("python3", "blockchain-collector", "snapctl"):
            log.info("which %s -> %s", name, shutil.which(name))
    except Exception:
        log.exception("Startup env dump failed")

def _find_collector_exe() -> str:
    """Prefer the snap's venv binary; fall back to PATH."""
    # SNAP/venv/bin/...
    snap = os.environ.get("SNAP")
    if snap:
        candidate = os.path.join(snap, "venv", "bin", "blockchain-collector")
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    # PATH
    exe = shutil.which("blockchain-collector")
    return exe or "blockchain-collector"

def _summarize_error(stderr: str) -> str:
    """
    Strip Python tracebacks and return a concise reason.
    Keeps the full text in the logs; HTTP response only gets the summary.
    """
    if not stderr:
        return "collector failed (no stderr)"
    lines = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
    # Try to extract the last exception line
    for ln in reversed(lines):
        # e.g. "blockchain_collector.core.CollectorFailedError: message"
        if ":" in ln and "Traceback" not in ln:
            return ln
    # Fallback: first and last line
    if len(lines) >= 2:
        return f"{lines[0]} … {lines[-1]}"
    return lines[-1]

def _read_metadata_status(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        md = data.get("metadata", {})
        status = md.get("last_collect_status", "unknown")
        errors = md.get("last_collect_errors", [])
        return status, errors
    except FileNotFoundError:
        return "missing", ["metadata file not found"]
    except Exception as e:
        log.exception("Failed to read/parse metadata.json")
        return "invalid", [f"invalid metadata: {e}"]


def _run_once():
    collector = _snapctl_get("collector.name", "null")
    validate_flag = _snapctl_get("collector.validate", True)
    schema_path = _snapctl_get("collector.schema_path", None)
    timeout_sec = _snapctl_get("collector.timeout", 60)

    try:
        timeout_sec = int(timeout_sec)
    except Exception:
        log.warning("Invalid collector.timeout=%r, defaulting to 60", timeout_sec)
        timeout_sec = 60

    exe = _find_collector_exe()
    cmd = [exe, "collect", "--collector", collector, "--output", METADATA_PATH]
    if not validate_flag:
        cmd.append("--no-validate")
    if schema_path:
        cmd.extend(["--schema", schema_path])

    env = os.environ.copy()
    if env.get("SNAP"):
        env["PATH"] = os.pathsep.join([os.path.join(env["SNAP"], "venv", "bin"), env.get("PATH", "")])

    log.info("Running collector: %r", cmd)

    try:
        # Do NOT use check=True so we can still inspect the produced file
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        log.error("Collector timeout after %ss", timeout_sec)
        os.makedirs(os.path.dirname(METADATA_PATH), exist_ok=True)
        with open(METADATA_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "metadata": {
                    "collector_name": collector,
                    "last_collect_status": "failed",
                    "last_collect_errors": [f"timeout after {timeout_sec}s"],
                },
                "blockchain": {},
                "workload": {},
            }, f)
        return {"ok": False, "error": f"timeout after {timeout_sec}s", "cmd": cmd}

    # Log outputs for debugging
    if proc.stdout:
        log.debug("collector stdout:\n%s", proc.stdout.strip())
    if proc.stderr:
        log.debug("collector stderr:\n%s", proc.stderr.strip())

    # Ensure file exists (create minimal one if needed)
    if not os.path.isfile(METADATA_PATH):
        os.makedirs(os.path.dirname(METADATA_PATH), exist_ok=True)
        with open(METADATA_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "metadata": {
                    "collector_name": collector,
                    "last_collect_status": "failed",
                    "last_collect_errors": ["collector produced no output file"],
                },
                "blockchain": {},
                "workload": {},
            }, f)

    # Decide success/partial/failed based on the file’s metadata
    status, errors = _read_metadata_status(METADATA_PATH)

    if status != "success":
        # Treat partial/failed/missing/invalid as error
        brief = errors[0] if errors else f"status={status}"
        log.warning("Collector not successful (status=%s): %s", status, brief)
        return {
            "ok": False,
            "status": status,
            "error": brief,
            "cmd": cmd,
        }

    # Also fail if the process had a non-zero exit even though file says success
    if proc.returncode != 0:
        log.warning("Collector exit code=%s despite status=success", proc.returncode)
        return {
            "ok": False,
            "status": status,
            "error": f"exit_code={proc.returncode}",
            "cmd": cmd,
        }

    return {"ok": True, "cmd": cmd}



def _worker():
    interval = _snapctl_get("collector.interval", 300)
    try:
        interval = int(interval)
    except Exception:
        log.warning("Invalid collector.interval=%r, using 300", interval)
        interval = 300
    log.info("Background worker started; interval=%s seconds", interval)
    while True:
        try:
            _run_once()
        except Exception:
            log.exception("_run_once crashed")
        time.sleep(max(5, interval))

# ---------- HTTP ----------
class _Handler(BaseHTTPRequestHandler):
    server_version = "CollectorHTTP/1.0"

    def log_message(self, fmt, *args):
        log.info("%s - - %s", self.address_string(), fmt % args)

    def _set(self, code=200, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        log.debug("HTTP GET %s", path)
        if path == "/metadata":
            try:
                with open(METADATA_PATH, "rb") as f:
                    data = f.read()
                self._set(200, "application/json")
                self.wfile.write(data)
            except FileNotFoundError:
                log.warning("Metadata not found at %s", METADATA_PATH)
                self._set(404)
                self.wfile.write(b'{"error":"metadata not found"}')
        elif path == "/healthz":
            self._set(200, "text/plain")
            self.wfile.write(b"ok")
        elif path == "/env":
            self._set(200, "application/json")
            payload = {
                "snap": {k: os.environ[k] for k in os.environ if k.startswith("SNAP")},
                "path": os.environ.get("PATH", ""),
                "metadata_path": METADATA_PATH,
                "log_path": LOG_PATH,
            }
            self.wfile.write(json.dumps(payload, indent=2).encode())
        else:
            self._set(404)
            self.wfile.write(b'{"error":"not found"}')

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        log.debug("HTTP POST %s", path)
        if path == "/run":
            res = _run_once()
            self._set(200 if res.get("ok") else 500)
            self.wfile.write(json.dumps(res).encode())
        else:
            self._set(404)
            self.wfile.write(b'{"error":"not found"}')

def main():
    _dump_startup_env()

    # Initial run so the file exists
    try:
        log.info("Initial _run_once()")
        _run_once()
    except Exception:
        log.exception("Initial run failed")

    # Background loop
    t = threading.Thread(target=_worker, name="collector-worker", daemon=True)
    t.start()

    port = _snapctl_get("service.port", 18080)
    try:
        port = int(port)
    except Exception:
        log.warning("Invalid service.port=%r, defaulting to 18080", port)
        port = 18080

    addr = ("0.0.0.0", port)
    log.info("HTTP server starting on %s:%s", *addr)
    try:
        HTTPServer(addr, _Handler).serve_forever()
    except Exception:
        log.exception("HTTP server crashed")
        raise

if __name__ == "__main__":
    main()
