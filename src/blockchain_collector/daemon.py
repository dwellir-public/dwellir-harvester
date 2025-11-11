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
        log.warning("snapctl get %s failed: rc=%s stderr=%r", key, e.returncode, e.stderr)
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

# ---------- collector runner ----------
def _run_once():
    collector = _snapctl_get("collector.name", "null")
    validate_flag = _snapctl_get("collector.validate", True)
    schema_path = _snapctl_get("collector.schema_path", None)

    cmd = ["blockchain-collector", "collect", "--collector", collector, "--output", METADATA_PATH]
    if not validate_flag:
        cmd.append("--no-validate")
    if schema_path:
        cmd.extend(["--schema", schema_path])

    env = os.environ.copy()
    log.info("Running collector: %r", cmd)
    log.debug("ENV PATH=%s", env.get("PATH", ""))

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
        if proc.stdout:
            log.debug("collector stdout:\n%s", proc.stdout.strip())
        if proc.stderr:
            log.debug("collector stderr:\n%s", proc.stderr.strip())
        if not os.path.isfile(METADATA_PATH):
            log.warning("Collector succeeded but %s does not exist; creating empty metadata", METADATA_PATH)
            os.makedirs(os.path.dirname(METADATA_PATH), exist_ok=True)
            with open(METADATA_PATH, "w", encoding="utf-8") as f:
                json.dump({"metadata":{"note":"created by daemon fallback"}}, f)
        return {"ok": True, "cmd": cmd}
    except subprocess.CalledProcessError as e:
        os.makedirs(os.path.dirname(METADATA_PATH), exist_ok=True)
        err = (e.stderr or "").strip() or str(e)
        out = (e.stdout or "").strip()
        log.error("Collector FAILED: rc=%s", e.returncode)
        if out:
            log.error("collector stdout:\n%s", out)
        if err:
            log.error("collector stderr:\n%s", err)
        fail_payload = {
            "metadata": {
                "collector_name": collector,
                "last_collect_status": "failed",
                "last_collect_errors": [err],
            },
            "blockchain": {},
            "workload": {},
        }
        try:
            with open(METADATA_PATH, "w", encoding="utf-8") as f:
                json.dump(fail_payload, f)
            log.info("Wrote failure metadata to %s", METADATA_PATH)
        except Exception:
            log.exception("Failed to write failure metadata")
        return {"ok": False, "error": err, "cmd": cmd}
    except FileNotFoundError as e:
        log.exception("Executable not found running %r", cmd)
        return {"ok": False, "error": f"executable missing: {e}", "cmd": cmd}
    except Exception as e:
        log.exception("Unexpected error running collector")
        return {"ok": False, "error": str(e), "cmd": cmd}

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

    port = _snapctl_get("service.port", 8080)
    try:
        port = int(port)
    except Exception:
        log.warning("Invalid service.port=%r, defaulting to 8080", port)
        port = 8080

    addr = ("0.0.0.0", port)
    log.info("HTTP server starting on %s:%s", *addr)
    try:
        HTTPServer(addr, _Handler).serve_forever()
    except Exception:
        log.exception("HTTP server crashed")
        raise

if __name__ == "__main__":
    main()
