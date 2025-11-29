# Writing a drop-in collector plugin (filesystem)

This shows how to author a new collector outside the main tree and run it via the CLI or daemon.

## 1) Create a plugin module

Make a directory for plugins and add a collector class.

### Generic collector example

```bash
mkdir -p plugins
cat > plugins/my_plugin.py <<'PY'
from dwellir_harvester.collector_base import GenericCollector

class MyPlugin(GenericCollector):
    NAME = "my-plugin"
    VERSION = "0.1.0"
    COLLECTOR_TYPE = "generic"

    @classmethod
    def create(cls, *args, **kwargs):
        return cls(*args, **kwargs)

    def collect(self):
        # Return a dict with your data
        return {
            "meta": {
                "collector_type": self.COLLECTOR_TYPE,
                "collector_name": self.NAME,
                "collector_version": self.VERSION,
            },
            "data": {
                "message": "hello from my plugin",
                "details": {"foo": "bar"},
            },
            "message": "Optional human-readable note",
        }
PY
```

### Blockchain collector example

```bash
cat > plugins/my_chain.py <<'PY'
from dwellir_harvester.collector_base import BlockchainCollector, CollectResult

class MyChainCollector(BlockchainCollector):
    NAME = "my-chain"
    VERSION = "0.1.0"

    @classmethod
    def create(cls, *args, **kwargs):
        return cls(*args, **kwargs)

    def collect(self):
        # Prepare blockchain/workload sections; validator will enforce required keys
        blockchain = {
            "blockchain_ecosystem": "ExampleNet",
            "blockchain_network_name": "mainnet",
            "chain_id": "example-1",
        }
        workload = {
            "client_name": "exampled",
            "client_version": "v1.2.3",
            "service_data": {"status": "ok"},
        }
        return CollectResult.create(
            collector_name=self.NAME,
            collector_version=self.VERSION,
            data={"blockchain": blockchain, "workload": workload},
        )
PY
```

## 2) Test the plugin directly

Use the SDK runner (bypasses the CLI/daemon) and point to your plugin path:

```bash
source .venv/bin/activate
python -m dwellir_harvester.lib.run my_plugin:MyPlugin --collector-path ./plugins
python -m dwellir_harvester.lib.run my_chain:MyChainCollector --collector-path ./plugins
```

## 3) Run via the CLI

Tell the CLI where to find the plugin and run it like any other collector:

```bash
dwellir-harvester collect my-plugin --collector-path ./plugins --no-validate
dwellir-harvester collect my-chain --collector-path ./plugins --no-validate
```

You can combine built-ins and plugins:

```bash
dwellir-harvester collect host my-plugin --collector-path ./plugins --no-validate
dwellir-harvester collect host my-chain --collector-path ./plugins --no-validate
```

## 4) Run via the daemon

Pass the same path to the daemon so it can load your plugin:

```bash
dwellir-harvester-daemon \
  --collector-path ./plugins \
  --collectors my-plugin \
  --no-validate --debug

dwellir-harvester-daemon \
  --collector-path ./plugins \
  --collectors my-chain \
  --no-validate --debug
```

Then query:

```bash
curl -s http://127.0.0.1:18080/metadata | jq .
```

## Tips

- The `NAME` attribute is the lookup key; keep it unique.
- Use `BlockchainCollector` if you need the blockchain/workload schema validation; otherwise `GenericCollector` is fine.
- If you prefer entry points instead of filesystem paths, publish under the group `dwellir_harvester.collectors`.
