# blockchain-collector

An extensible Python tool to collect metadata from **local blockchain nodes** and output a JSON file that conforms to a shared JSON Schema.

> All timestamps use RFC 3339 / ISO 8601 with timezone.

## Quick start (local dev)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e .

# Run with the safe default "null" collector (no local node required)
blockchain-collector collect   --schema schema/blockchain_node_metadata.schema.json   --collector null   --output out.json
```

Open `out.json` to see the collected data.

## Adding a new collector

Create a new module under `src/blockchain_collector/collectors/` and implement a class
that derives from `BaseCollector`. Example:

```python
from blockchain_collector.core import BaseCollector, CollectResult

class MyCollector(BaseCollector):
    NAME = "my_chain_client"
    VERSION = "1.0.0"

    def collect(self) -> CollectResult:
        return CollectResult(
            blockchain={
                "blockchain_ecosystem": "MyChain",
                "blockchain_network_name": "mainnet",
                "chain_id": 4242,
            },
            workload={
                "client_name": "myclient",
                "client_version": "v1.2.3",
            },
        )
```

Export it by adding it to `__all__` in `collectors/__init__.py` so the CLI can find it
by `--collector my_chain_client`.

### Built-in collectors

- `null` — static, schema-valid placeholder; **default** and requires no node.
- `reth` — queries a local Reth JSON-RPC and `reth --version` (best-effort).
- `op-reth` — same logic as `reth`, only `workload.client_name` differs.
- `bera-reth` — same logic as `reth`, only `workload.client_name` differs.
- `substrate` — generic Substrate collector; queries `system_version`, `system_chain`, `chain_getBlockHash(0)`, and uses `system_name` for client_name when not overridden.
- `ajuna` — Substrate wrapper that hardcodes `workload.client_name` to `ajuna`.
- `dummychain` — Dummychain testing chain. (Must sudo snap connect blockchain-collector:dummychain-bins dummychain:bins)
 
All Reth variants use the same environment variable for RPC:
- `RETH_RPC_URL` (default: `http://127.0.0.1:8545`)
 
All Substrate variants use the same environment variable for RPC:
- `SUBSTRATE_RPC_URL` (default: `http://127.0.0.1:9933`)
 
Examples:
 
```bash
# default reth
blockchain-collector collect --collector reth
 
# Optimism reth
blockchain-collector collect --collector op-reth
 
# Bera reth
blockchain-collector collect --collector bera-reth
 
# Generic substrate node (Polkadot/Kusama/Westend/etc.)
blockchain-collector collect --collector substrate

# Ajuna substrate node
blockchain-collector collect --collector ajuna
```


## Validation

We validate output with `jsonschema`. You can disable validation via `--no-validate`.

---

## Snap: packaged daemon

The snap ships a small HTTP daemon that periodically runs the collector and serves the latest metadata.

### Files & paths

- Read-only snap payload: `$SNAP`
- Writable data: `$SNAP_COMMON` → `/var/snap/blockchain-collector/common`
  - Metadata JSON: `/var/snap/blockchain-collector/common/metadata.json`
  - Daemon log: `/var/snap/blockchain-collector/common/daemon.log`

### Install

```bash
sudo snap install blockchain-collector --channel=edge
# or: sudo snap install ./blockchain-collector_*.snap --dangerous
```

### Configure (snap settings)

These keys are read dynamically by the daemon; no rebuild needed.

| Key                      | Type     | Default | Purpose |
|--------------------------|----------|---------|---------|
| `collector.name`         | string   | `null`  | Which collector to run (e.g., `null`, `reth`, `op-reth`, `bera-reth`, `substrate`, `ajuna`). |
| `collector.validate`     | bool     | `true`  | Validate output JSON against the schema. |
| `collector.schema_path`  | string   | *(none)*| Path to JSON Schema file inside the snap or on disk. |
| `collector.interval`     | int sec  | `300`   | Background run interval in seconds (min 5). |
| `service.port`           | int      | `18080`  | HTTP server listen port. |
| `log.level`              | string   | `INFO`  | One of: `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG`. |

#### Examples

```bash
# Use the safe default
sudo snap set blockchain-collector collector.name=null

# Switch to Reth later
sudo snap set blockchain-collector collector.name=reth

# Point to a schema (path must be accessible to the snap)
sudo snap set blockchain-collector collector.schema_path=$SNAP/schema/blockchain_node_metadata.schema.json

# Turn off validation
sudo snap set blockchain-collector collector.validate=false

# Run every minute
sudo snap set blockchain-collector collector.interval=60

# Change HTTP port
sudo snap set blockchain-collector service.port=28080

# Increase verbosity
sudo snap set blockchain-collector log.level=DEBUG

# Inspect current config
snap get blockchain-collector
```

> After changing settings, the daemon will pick them up on the next cycle. To force now:  
> `sudo snap restart blockchain-collector.daemon`

### Start / stop / status

```bash
# Check services
snap services blockchain-collector

# Start / stop / restart the daemon
sudo snap start blockchain-collector.daemon
sudo snap stop blockchain-collector.daemon
sudo snap restart blockchain-collector.daemon

# Systemd status (advanced)
systemctl status snap.blockchain-collector.daemon.service
```

### Logs

```bash
# Journald (live)
snap logs blockchain-collector.daemon -f
# or
journalctl -u snap.blockchain-collector.daemon.service -o cat -f

# File log
sudo tail -F /var/snap/blockchain-collector/common/daemon.log
```

### Shell inside the snap environment

```bash
sudo snap run --shell blockchain-collector.daemon
env | grep ^SNAP
ls -al "$SNAP" "$SNAP_COMMON"
exit
```

---

## HTTP API

The daemon exposes a small HTTP API on `0.0.0.0:<service.port>` (default `:18080`).

### Endpoints

- `GET /healthz` → plain text `"ok"` if the daemon is serving.
- `GET /metadata` → the latest JSON document (200) or `{"error":"metadata not found"}` (404).
- `GET /env` → JSON with selected environment details (debugging aid).
- `POST /run` → triggers a collection run immediately; returns JSON status (200 on success, 500 on failure).

### `curl` examples

```bash
# Health
curl -s http://127.0.0.1:18080/healthz

# Current metadata (pretty-print)
curl -s http://127.0.0.1:18080/metadata | jq .

# Trigger an on-demand collection
curl -s -X POST http://127.0.0.1:18080/run | jq .

# Inspect runtime env (debug)
curl -s http://127.0.0.1:18080/env | jq .
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
python -m pip install build twine
python -m build  # creates dist/*.tar.gz and dist/*.whl

# upload to TestPyPI first (recommended)
python -m twine upload -r testpypi dist/*

# then to PyPI
python -m twine upload dist/*
```

---

## Notes

- The framework fills `metadata.last_collect_attempt_at`, `metadata.last_collect_status`,
  and `metadata.last_successful_collect_at` automatically.
- Collectors should **only** return the `blockchain` and `workload` portions.
- For recoverable issues, raise `CollectorPartialError` with warnings; the run will be marked `partial` and still emit output.
- For unrecoverable issues, raise `CollectorFailedError`.
- The `null` collector is intended for smoke tests, CI, and “no local client” deployments.
