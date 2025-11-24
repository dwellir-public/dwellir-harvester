#!/usr/bin/env python3
import os
import sys
import json
import time
import logging
import threading
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, Optional

# Import core functionality from the package
from dwellir_harvester.core import collect_all, bundled_schema_path

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
        self.output_file = config.get('output_file', '/var/lib/dwellir-harvester/harvested-data.json')
        
        # Ensure output directory exists
        if self.output_file:
            output_dir = os.path.dirname(self.output_file)
            os.makedirs(output_dir, exist_ok=True)

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
                debug=debug
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
    parser = argparse.ArgumentParser(description='Dwellir Harvester Daemon')
    parser.add_argument('--collectors', nargs='+', default=['host'],
                      help='List of collectors to run (default: host)')
    parser.add_argument('--host', default='0.0.0.0',
                      help='Host to bind the HTTP server to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=18080,
                      help='Port to run the HTTP server on (default: 18080)')
    parser.add_argument('--interval', type=int, default=300,
                      help='Collection interval in seconds (default: 300)')
    parser.add_argument('--output', default='/var/lib/dwellir-harvester/harvested-data.json',
                      help='Path to output file for collected data (default: /var/lib/dwellir-harvester/harvested-data.json)')
    parser.add_argument('--schema', help='Path to JSON schema file (defaults to bundled schema)')
    parser.add_argument('--no-validate', action='store_false', dest='validate',
                      help='Disable schema validation')
    parser.add_argument('--debug', action='store_true',
                      help='Enable debug output (overrides --log-level)')
    parser.add_argument('--log-level', default='INFO',
                      choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                      help='Logging level (default: INFO, ignored if --debug is used)')
    
    return parser.parse_args()

def main():
    """Main entry point."""
    args = parse_args()
    
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
        'host': args.host,
        'port': args.port,
        'interval': args.interval,
        'validate': args.validate,
        'output_file': args.output,
        'debug': args.debug,
        'schema_path': args.schema  # Pass the schema path to the daemon
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