#!/usr/bin/env python3
import os
import sys
import json
import time
import logging
import threading
import argparse
import tempfile
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, Optional, List

# Import core functionality from the package
from dwellir_harvester.core import collect_all, bundled_schema_path, load_collectors
from dwellir_harvester.cli import build_parser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S%z'
)
log = logging.getLogger("dwellir-harvester")

class CollectorDaemon:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.latest_results: Dict[str, Any] = {}
        self.lock = threading.Lock()
        self.running = False
        self.worker_thread: Optional[threading.Thread] = None
        self.httpd: Optional[HTTPServer] = None

    def run_collectors(self) -> Dict[str, Any]:
        """Run all collectors and return the results."""
        try:
            # Get the schema path
            schema_path = self.config.get('schema_path')
            if not schema_path:
                schema_path = str(bundled_schema_path())

            # Run the collectors
            result = collect_all(
                collector_names=self.config['collectors'],
                schema_path=schema_path,
                validate=self.config.get('validate', True)
            )

            # Update the latest results
            with self.lock:
                self.latest_results = result

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
        while self.running:
            try:
                log.info("Running scheduled collection")
                self.run_collectors()
            except Exception as e:
                log.error(f"Error in collector worker: {e}")

            # Wait for the next interval
            time.sleep(self.config.get('interval', 300))  # Default 5 minutes

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
                path = self.path.split('?', 1)[0]
                if path == '/metadata':
                    self._handle_metadata()
                elif path == '/healthz':
                    self._handle_healthz()
                else:
                    self._handle_not_found()

            def _set_headers(self, status_code=200, content_type="application/json"):
                self.send_response(status_code)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
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

            def log_message(self, fmt, *args):
                log.info(f"{self.address_string()} - {fmt % args}")

        return RequestHandler

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Dwellir Harvester Daemon',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        '--collectors',
        nargs='+',
        default=['host'],
        help='List of collectors to run'
    )
    parser.add_argument(
        '--host',
        default='0.0.0.0',
        help='Host to bind the HTTP server to'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=18080,
        help='Port to run the HTTP server on'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=300,
        help='Collection interval in seconds'
    )
    parser.add_argument(
        '--schema',
        help='Path to JSON schema file (defaults to bundled schema)'
    )
    parser.add_argument(
        '--no-validate',
        action='store_false',
        dest='validate',
        help='Disable schema validation'
    )
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Logging level'
    )
    
    return parser.parse_args()

def main():
    """Main entry point."""
    args = parse_args()
    
    # Configure logging
    logging.getLogger().setLevel(args.log_level)
    
    # Create and start the daemon
    daemon = CollectorDaemon({
        'collectors': args.collectors,
        'host': args.host,
        'port': args.port,
        'interval': args.interval,
        'schema_path': args.schema,
        'validate': args.validate
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