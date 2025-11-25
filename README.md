# Dwellir Harvester

An extensible Python tool to collect metadata from **local blockchain nodes** and output a JSON file that conforms to a shared JSON Schema.

> All timestamps use RFC 3339 / ISO 8601 with timezone.

## System Requirements

- Python 3.9 or higher
- Systemd (for running as a service)

## Installation

### From Source

1. Clone the repository:
   ```bash
   git clone https://github.com/your-org/dwellir-harvester.git
   cd dwellir-harvester
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install the package in development mode:
   ```bash
   pip install -e .
   ```

### System-wide Installation

For production use, you can install the package system-wide:

```bash
sudo pip install .
```

## Quick Start

### Run a Single Collection

```bash
# Run with the safe default "host" collector (basic system information)
dwellir-harvester collect host null --output out.json
```

### Run the Daemon

The harvester can run as a daemon that periodically collects data and serves it via HTTP:

```bash
# Start the daemon (runs in foreground)
dwellir-harvester-daemon
```

By default, the daemon:
- Runs on `0.0.0.0:18080`
- Collects data every 5 minutes
- Uses the "host" collector
- Validates output against the schema

## Configuration

### Command Line Arguments

```
usage: dwellir-harvester-daemon [-h] [--collectors COLLECTORS [COLLECTORS ...]] [--host HOST] [--port PORT] [--debug]
                               [--interval INTERVAL] [--schema SCHEMA] [--no-validate] [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}]

Dwellir Harvester Daemon

options:
  -h, --help            show this help message and exit
  --collectors COLLECTORS [COLLECTORS ...]
                        List of collectors to run (default: ['host'])
  --host HOST           Host to bind the HTTP server to (default: 0.0.0.0)
  --port PORT           Port to run the HTTP server on (default: 18080)
  --interval INTERVAL   Collection interval in seconds (default: 300)
  --schema SCHEMA       Path to JSON schema file (defaults to bundled schema)
  --no-validate         Disable schema validation
  --debug               Enable debug logging
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Logging level (default: INFO)
```

### Environment Variables

- `DATA_DIR`: Directory to store data files (default: `/var/lib/dwellir-harvester`)
- `LOG_LEVEL`: Logging level (default: `INFO`)
- `PORT`: HTTP server port (default: `18080`)
- `INTERVAL`: Collection interval in seconds (default: `300`)
- `COLLECTORS`: Space-separated list of collectors to run (default: `host`)
- `VALIDATE`: Enable/disable schema validation (default: `true`)
- `DEBUG`: Enable debug logging (default: `false`)

## Running as a Systemd Service

1. Install the service using the provided script:
   ```bash
   sudo scripts/install-service.sh
   ```

2. The service will be installed with default settings. You can customize it by editing:
   ```bash
   sudo nano /etc/dwellir-harvester/config
   ```

3. Start and enable the service:
   ```bash
   sudo systemctl start dwellir-harvester
   sudo systemctl enable dwellir-harvester
   ```

4. Check the status:
   ```bash
   systemctl status dwellir-harvester
   ```

5. View logs:
   ```bash
   journalctl -u dwellir-harvester -f
   ```

## Available Collectors

- `host` - Collects basic system information (default)
- `null` - A dummy collector
- `dummychain` - Collects data from a dummychain (snap install dummychain --edge)

## API Endpoints

- `GET /metadata` - Get the latest collected data
- `GET /healthz` - Health check endpoint

## Development

### Setting Up for Development

1. Clone the repository and install development dependencies:
   ```bash
   git clone https://github.com/your-org/dwellir-harvester.git
   cd dwellir-harvester
   python -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. Run tests:
   ```bash
   pytest
   ```

3. Run linters:
   ```bash
   black .
   isort .
   mypy .
   ```

### Adding a New Collector

1. Create a new Python file in `src/dwellir_harvester/collectors/`
2. Implement a class using the Dummycollector `BlockchainCollector` or Nullcollector `GenericCollector`
3. Add it to `__all__` in `collectors/__init__.py`

## License

MIT

---

## HTTP API

The daemon exposes a small HTTP API on `0.0.0.0:<service.port>` (default `:18080`).

### Endpoints

- `GET /healthz` → plain text `"ok"` if the daemon is serving.
- `GET /metadata` → the latest JSON document (200) or `{"error":"metadata not found"}` (404).

### `curl` examples

```bash
# Health
curl -s http://127.0.0.1:18080/healthz

# Current metadata (pretty-print)
curl -s http://127.0.0.1:18080/metadata | jq .

```

> If you changed the port via `service.port`, replace `18080` in the examples.

---

## Testing

```bash
python -m pip install -e .
pip install pytest
pytest -q
```

## Build & publish (Python package)

```bash
# build
python3 -m pip install build twine
python3 -m build  # creates dist/*.tar.gz and dist/*.whl

# upload to TestPyPI first (recommended)
python3 -m twine upload -r testpypi dist/*

# Install from testpypi
python3 -m venv .venv
source .venv/bin/activate
# Pull in deps from real, this is needed only on testpypi 
pip3 install jsonschema>=4.25.1 psutil>=7.1.3 requests>=2.32.5
# Install from testpypi
pip3 install --index-url https://test.pypi.org/simple/ --no-deps dwellir-harvester

# then to PyPI
python3 -m twine upload dist/*
```

---

## Notes

- The framework fills `metadata.last_collect_attempt_at`, `metadata.last_collect_status`,
  and `metadata.last_successful_collect_at` automatically.
- Collectors should **only** return the `blockchain` and `workload` portions.
- For recoverable issues, raise `CollectorPartialError` with warnings; the run will be marked `partial` and still emit output.
- For unrecoverable issues, raise `CollectorFailedError`.
- The `null` collector is intended for smoke tests, CI, and “no local client” deployments.
