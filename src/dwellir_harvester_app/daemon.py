#!/usr/bin/env python3
import os
import sys
import json
import time
import logging
import threading
import argparse
import hmac
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, Optional, List, Tuple

# Import core functionality from the package
from dwellir_harvester.core import collect_all, bundled_schema_path

# Configure logging
def setup_logging(debug=False):
    """Configure logging with the specified debug level."""
    log_level = logging.DEBUG if debug else logging.INFO
    
    # Configure the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clear any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create a console handler
    console = logging.StreamHandler()
    console.setLevel(log_level)
    
    # Set the formatter
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S%z'
    )
    console.setFormatter(formatter)
    
    # Add the handler to the root logger
    root_logger.addHandler(console)
    
    # Get the main logger
    log = logging.getLogger("dwellir-harvester")
    log.setLevel(log_level)
    
    return log

# Initialize logging with default level (will be updated in main)
log = logging.getLogger("dwellir-harvester")

class CollectorDaemon:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.latest_results: Dict[str, Any] = {}
        self.lock = threading.Lock()
        self.running = False
        self.worker_thread: Optional[threading.Thread] = None
        self.httpd: Optional[HTTPServer] = None
        self.output_file = config.get('output_file', '/var/lib/dwellir-harvester/harvested-data.json')
        self.auth_tokens = self._load_auth_tokens(config)
        self.collector_paths = config.get('collector_paths', [])
        self.collector_kwargs = config.get('collector_kwargs', {})
        
        # Ensure output directory exists
        if self.output_file:
            output_dir = os.path.dirname(self.output_file)
            os.makedirs(output_dir, exist_ok=True)

    def _load_auth_tokens(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Load allowed auth tokens from env/config/file.
        
        Returns a list of dicts: {"token": str, "label": Optional[str], "enabled": bool}
        Empty list means auth disabled.
        """
        tokens: List[Dict[str, Any]] = []

        token_file = config.get("auth_token_file") or os.environ.get("DAEMON_AUTH_TOKEN_FILE")
        if token_file:
            path = Path(token_file)
            if not path.exists():
                log.error(f"Auth token file {token_file} does not exist; auth disabled")
                return []
            try:
                raw = path.read_text()
                parsed: Any = None
                try:
                    parsed = json.loads(raw)
                except Exception:
                    try:
                        import yaml  # type: ignore
                        parsed = yaml.safe_load(raw)
                    except Exception as e:
                        log.error(f"Failed to parse auth token file {token_file}: {e}; auth disabled")
                        return []
                if not isinstance(parsed, list):
                    log.error(f"Auth token file {token_file} must be a list of objects; auth disabled")
                    return []
                for entry in parsed:
                    if not isinstance(entry, dict) or "token" not in entry:
                        log.warning(f"Skipping invalid token entry in {token_file}: {entry!r}")
                        continue
                    tokens.append(
                        {
                            "token": str(entry["token"]),
                            "label": entry.get("label"),
                            "enabled": bool(entry.get("enabled", True)),
                        }
                    )
            except Exception as e:
                log.error(f"Failed to read auth token file {token_file}: {e}; auth disabled")
                return []
        else:
            env_tokens = config.get("auth_tokens") or os.environ.get("DAEMON_AUTH_TOKENS")
            if env_tokens:
                if isinstance(env_tokens, str):
                    items = [t.strip() for t in env_tokens.split(",") if t.strip()]
                elif isinstance(env_tokens, list):
                    items = [str(t).strip() for t in env_tokens if str(t).strip()]
                else:
                    items = []
                for idx, tok in enumerate(items):
                    tokens.append({"token": tok, "label": f"env-{idx+1}", "enabled": True})

        if tokens:
            log.info(f"Auth enabled with {len(tokens)} token(s)")
        else:
            log.info("Auth disabled (no tokens configured)")
        return tokens

    def _extract_presented_token(self, headers) -> Optional[str]:
        """Extract token from Authorization Bearer or X-Auth-Token."""
        auth_header = headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            return auth_header.split(" ", 1)[1].strip()
        alt = headers.get("X-Auth-Token")
        if alt:
            return alt.strip()
        return None

    def _authorize(self, headers) -> Tuple[bool, Optional[str], str]:
        """Check request headers against configured tokens.
        
        Returns (allowed, label, reason)
        """
        if not self.auth_tokens:
            return True, None, "auth_disabled"

        presented = self._extract_presented_token(headers)
        if not presented:
            return False, None, "missing_token"

        for entry in self.auth_tokens:
            token = entry.get("token")
            enabled = entry.get("enabled", True)
            label = entry.get("label")
            if hmac.compare_digest(str(presented), str(token)):
                if enabled:
                    return True, label, "ok"
                return False, label, "revoked"

        return False, None, "invalid_token"

    def run_collectors(self) -> Dict[str, Any]:
        """Run all collectors and return the results."""
        debug = self.config.get('debug', False)
        if debug:
            log.setLevel(logging.DEBUG)
            log.debug("Debug mode enabled")
            log.debug(f"Running collectors: {self.config['collectors']}")
            log.debug(f"Validation is {'enabled' if self.config.get('validate', True) else 'disabled'}")
            
        try:
            # Get the schema path
            schema_path = self.config.get('schema_path')
            if not schema_path:
                schema_path = str(bundled_schema_path())
                if debug:
                    log.debug(f"Using bundled schema from: {schema_path}")
            else:
                if debug:
                    log.debug(f"Using custom schema from: {schema_path}")

            if debug:
                log.debug("Starting collection...")
                start_time = time.time()

            # Run the collectors
            result = collect_all(
                collector_names=self.config['collectors'],
                schema_path=schema_path,
                validate=self.config.get('validate', True),
                debug=debug,
                plugin_paths=self.collector_paths,
                collector_kwargs=self.collector_kwargs,
            )

            # Update the latest results
            with self.lock:
                self.latest_results = result
                
                # Write results to file if output_file is set
                if self.output_file:
                    try:
                        with open(self.output_file, 'w') as f:
                            json.dump(result, f, indent=2)
                        log.debug(f"Wrote collected data to {self.output_file}")
                    except Exception as e:
                        log.error(f"Failed to write to output file {self.output_file}: {e}")

            return result

        except Exception as e:
            log.error(f"Failed to run collectors: {e}")
            with self.lock:
                self.latest_results = {
                    "error": str(e),
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z")
                }
            return self.latest_results

    def _worker_loop(self):
        """Background worker that runs collectors on a schedule."""
        debug = self.config.get('debug', False)
        interval = self.config.get('interval', 300)
        
        if debug:
            log.debug(f"Starting worker loop with {interval}s interval")
            
        while self.running:
            try:
                start_time = time.time()
                log.info("Running scheduled collection")
                if debug:
                    log.debug(f"Collection started at {time.ctime(start_time)}")
                    
                self.run_collectors()
                
                if debug:
                    duration = time.time() - start_time
                    log.debug(f"Collection completed in {duration:.2f} seconds")
                    
            except Exception as e:
                log.error(f"Error in collector worker: {e}")
                if debug:
                    import traceback
                    log.debug(f"Full traceback:\n{traceback.format_exc()}")

            # Wait for the next interval
            sleep_time = max(0, interval - (time.time() - start_time))
            if debug and sleep_time > 0:
                log.debug(f"Sleeping for {sleep_time:.1f} seconds until next collection")
                
            time.sleep(sleep_time)

    def start(self):
        """Start the daemon and HTTP server."""
        if self.running:
            log.warning("Daemon is already running")
            return

        self.running = True

        # Initial collection
        log.info("Running initial collection")
        self.run_collectors()

        # Start the background worker
        self.worker_thread = threading.Thread(
            target=self._worker_loop,
            name="collector-worker",
            daemon=True
        )
        self.worker_thread.start()

        # Start the HTTP server
        addr = (self.config.get('host', ''), self.config.get('port', 18080))
        httpd = HTTPServer(addr, self._make_handler())
        self.httpd = httpd

        log.info(f"Starting HTTP server on {addr[0]}:{addr[1]}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            log.info("Shutting down...")
        finally:
            self.stop()

    def stop(self):
        """Stop the daemon and clean up."""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()

    def _make_handler(self):
        """Create a request handler with access to this daemon instance."""
        daemon = self

        class RequestHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                allowed, label, reason = daemon._authorize(self.headers)
                if not allowed:
                    self._handle_unauthorized(label, reason)
                    return

                path = self.path.split('?', 1)[0]
                if path == '/metadata':
                    self._handle_metadata()
                elif path == '/healthz':
                    self._handle_healthz()
                else:
                    self._handle_not_found()

            def _set_headers(self, status_code=200, content_type="application/json", extra_headers: Optional[Dict[str, str]] = None):
                self.send_response(status_code)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                if extra_headers:
                    for k, v in extra_headers.items():
                        self.send_header(k, v)
                self.end_headers()

            def _handle_metadata(self):
                with daemon.lock:
                    data = json.dumps(daemon.latest_results, indent=2).encode('utf-8')
                
                self._set_headers()
                self.wfile.write(data)

            def _handle_healthz(self):
                self._set_headers(content_type="text/plain")
                self.wfile.write(b"ok\n")

            def _handle_not_found(self):
                self._set_headers(404)
                self.wfile.write(json.dumps({
                    "error": "Not found",
                    "endpoints": ["/metadata", "/healthz"]
                }).encode('utf-8'))

            def _handle_unauthorized(self, label: Optional[str], reason: str):
                # Do not log tokens; log label if available
                msg = f"Unauthorized request from {self.address_string()} reason={reason}"
                if label:
                    msg += f" label={label}"
                log.warning(msg)
                self._set_headers(
                    401,
                    extra_headers={"WWW-Authenticate": "Bearer"}
                )
                body = {"error": "unauthorized", "reason": reason}
                if label:
                    body["label"] = label
                self.wfile.write(json.dumps(body).encode("utf-8"))

            def log_message(self, fmt, *args):
                log.info(f"{self.address_string()} - {fmt % args}")

        return RequestHandler

def _load_collector_args(raw: Optional[str], file_path: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """Parse collector args from JSON string/file/env."""
    data = None
    if file_path:
        try:
            data = Path(file_path).read_text()
        except Exception:
            data = None
    if raw:
        data = raw
    if data is None:
        data = os.environ.get("HARVESTER_COLLECTOR_ARGS")
    if not data:
        return {}
    try:
        parsed = json.loads(data)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return {}
    return {}


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Dwellir Harvester Daemon')
    parser.add_argument('--collectors', nargs='+', default=['host'],
                      help='List of collectors to run (default: host)')
    parser.add_argument(
        '--collector-path',
        action='append',
        dest='collector_paths',
        default=[],
        help='Additional paths to search for collectors (can be repeated). Also honors HARVESTER_COLLECTOR_PATHS.'
    )
    parser.add_argument('--host', default='0.0.0.0',
                      help='Host to bind the HTTP server to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=18080,
                      help='Port to run the HTTP server on (default: 18080)')
    parser.add_argument('--interval', type=int, default=300,
                      help='Collection interval in seconds (default: 300)')
    parser.add_argument('--output', default='/var/lib/dwellir-harvester/harvested-data.json',
                      help='Path to output file for collected data (default: /var/lib/dwellir-harvester/harvested-data.json)')
    parser.add_argument('--schema', help='Path to JSON schema file (defaults to bundled schema)')
    parser.add_argument('--auth-token', action='append', dest='auth_tokens',
                      help='Bearer token to require for HTTP access (can be specified multiple times)')
    parser.add_argument('--auth-token-file',
                      help='Path to JSON/YAML file containing token entries: [{"token": "...", "label": "...", "enabled": true}]')
    parser.add_argument('--no-validate', action='store_false', dest='validate',
                      help='Disable schema validation')
    parser.add_argument('--debug', action='store_true',
                      help='Enable debug output (overrides --log-level)')
    parser.add_argument('--log-level', default='INFO',
                      choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                      help='Logging level (default: INFO, ignored if --debug is used)')
    parser.add_argument(
        '--collector-args',
        dest='collector_args',
        default=None,
        help='JSON mapping of collector name to kwargs for CollectorCls.create(**kwargs). Also honors HARVESTER_COLLECTOR_ARGS.',
    )
    parser.add_argument(
        '--collector-args-file',
        dest='collector_args_file',
        default=None,
        help='Path to JSON file containing collector kwargs mapping.',
    )
    
    return parser.parse_args()

def main():
    """Main entry point."""
    args = parse_args()
    collector_kwargs = _load_collector_args(args.collector_args, args.collector_args_file)
    
    # Configure logging
    log_level = logging.DEBUG if args.debug else getattr(logging, args.log_level)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%dT%H:%M:%S%z'
    )
    
    if args.debug:
        log.info("Debug mode enabled")
        log.debug(f"Command line arguments: {sys.argv}")
    
    # Create and start the daemon
    daemon = CollectorDaemon({
        'collectors': args.collectors,
        'collector_paths': args.collector_paths,
        'host': args.host,
        'port': args.port,
        'interval': args.interval,
        'validate': args.validate,
        'output_file': args.output,
        'debug': args.debug,
        'schema_path': args.schema,  # Pass the schema path to the daemon
        'auth_tokens': args.auth_tokens,
        'auth_token_file': args.auth_token_file,
        'collector_kwargs': collector_kwargs,
    })
    
    try:
        daemon.start()
    except KeyboardInterrupt:
        log.info("Shutting down...")
    except Exception as e:
        log.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        daemon.stop()

if __name__ == '__main__':
    main()
