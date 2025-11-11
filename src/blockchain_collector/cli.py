
import argparse
import json
from .core import run_collector, bundled_schema_path

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="blockchain-collector", description="Collect blockchain node metadata into a JSON file.")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="Run a collector and emit JSON output.")
    c.add_argument("--schema", required=False, help="Path to JSON Schema file (defaults to bundled).")
    c.add_argument("--collector", required=True, help="Collector name (e.g., reth).")
    c.add_argument("--output", required=False, help="Output JSON path (default: stdout).")
    c.add_argument("--no-validate", action="store_true", help="Skip JSON Schema validation.")
    c.add_argument("--meta", action="append", default=[], help="Extra metadata k=v (can repeat).")
    return p

def parse_meta(kv_list):
    md = {}
    for item in kv_list:
        if "=" not in item:
            raise SystemExit(f"--meta must be k=v, got: {item}")
        k, v = item.split("=", 1)
        md[k] = v
    return md

def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.cmd == "collect":
        extra = parse_meta(args.meta)
        data = run_collector(
            collector_name=args.collector,
            schema_path=(args.schema or bundled_schema_path()),
            validate=not args.no_validate,
            extra_metadata=extra or None,
        )
        out = json.dumps(data, indent=2, sort_keys=False)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(out + "\n")
        else:
            print(out)
    else:
        raise SystemExit(2)

if __name__ == "__main__":
    main()
