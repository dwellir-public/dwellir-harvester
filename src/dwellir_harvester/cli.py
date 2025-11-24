import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

try:
    from .core import collect_all, bundled_schema_path, load_collectors, run_collector
except ImportError:
    from core import collect_all, bundled_schema_path, load_collectors, run_collector

def build_parser() -> argparse.ArgumentParser:
    """Build the command line argument parser."""
    parser = argparse.ArgumentParser(
        prog="dwellir-harvester",
        description="Collect blockchain node metadata into a JSON file."
    )
    
    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest="cmd", required=True)
    
    # 'collect' command
    collect_parser = subparsers.add_parser(
        "collect",
        help="Run one or more collectors and output the results."
    )
    collect_parser.add_argument(
        "collectors",
        nargs="+",
        help="One or more collector names to run (e.g., dummychain system)."
    )
    collect_parser.add_argument(
        "--schema",
        help="Path to JSON Schema file (defaults to bundled schema).",
        default=None
    )
    collect_parser.add_argument(
        "--output", "-o",
        help="Output file path (default: stdout).",
        type=Path,
        default=None
    )
    collect_parser.add_argument(
        "--no-validate",
        action="store_false",
        dest="validate",
        help="Disable schema validation of the output."
    )
    collect_parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output with detailed error information."
    )
    
    return parser

def main(args: Optional[List[str]] = None) -> int:
    """Main entry point for the CLI."""
    parser = build_parser()
    parsed_args = parser.parse_args(args)
    
    if parsed_args.cmd == "collect":
        start_time = datetime.now(timezone.utc)
        
        if parsed_args.debug:
            print(f"[DEBUG] Starting collection process at {start_time.isoformat()}", file=sys.stderr)
            print(f"[DEBUG] Python version: {sys.version}", file=sys.stderr)
            print(f"[DEBUG] Command line arguments: {sys.argv}", file=sys.stderr)
            print(f"[DEBUG] Parsed arguments: {vars(parsed_args)}", file=sys.stderr)
        
        try:
            # Get the schema path (use bundled schema if not specified)
            schema_path = parsed_args.schema or str(bundled_schema_path())
            
            if parsed_args.debug:
                print(f"[DEBUG] Using schema path: {schema_path}", file=sys.stderr)
                print("[DEBUG] Loading all available collectors...", file=sys.stderr)
            
            # Load all available collectors
            all_collectors = load_collectors()
            
            if parsed_args.debug:
                print(f"[DEBUG] Found {len(all_collectors)} total collectors", file=sys.stderr)
                print(f"[DEBUG] Requested collectors: {parsed_args.collectors}", file=sys.stderr)
            
            # Filter to only the requested collectors
            collectors = []
            for name in parsed_args.collectors:
                if name not in all_collectors:
                    msg = f"Warning: Unknown collector '{name}', skipping"
                    print(msg, file=sys.stderr)
                    if parsed_args.debug:
                        print(f"[DEBUG] Available collectors: {list(all_collectors.keys())}", file=sys.stderr)
                    continue
                collectors.append(all_collectors[name])
            
            if not collectors:
                error_msg = "Error: No valid collectors specified"
                print(error_msg, file=sys.stderr)
                if parsed_args.debug:
                    print("[DEBUG] No valid collectors found after filtering", file=sys.stderr)
                return 1
            
            if parsed_args.debug:
                print(f"[DEBUG] Running {len(collectors)} collectors: {[c.NAME for c in collectors]}", file=sys.stderr)
                print(f"[DEBUG] Validation is {'enabled' if parsed_args.validate else 'disabled'}", file=sys.stderr)
            
            # Run the collectors
            result = collect_all(
                [c.NAME for c in collectors],
                schema_path=schema_path,
                validate=getattr(parsed_args, 'validate', True),  # Use getattr for backward compatibility
                debug=parsed_args.debug
            )
            
            # Output the result
            output = json.dumps(result, indent=2)
            
            if parsed_args.output:
                if parsed_args.debug:
                    print(f"[DEBUG] Writing results to {parsed_args.output}", file=sys.stderr)
                try:
                    parsed_args.output.write_text(output)
                    print(f"Results written to {parsed_args.output}")
                    if parsed_args.debug:
                        print(f"[DEBUG] Successfully wrote {len(output)} bytes to {parsed_args.output}", file=sys.stderr)
                except Exception as e:
                    error_msg = f"Error writing to {parsed_args.output}: {str(e)}"
                    print(error_msg, file=sys.stderr)
                    if parsed_args.debug:
                        import traceback
                        traceback.print_exc(file=sys.stderr)
                    return 1
            else:
                if parsed_args.debug:
                    print("[DEBUG] Outputting results to stdout", file=sys.stderr)
                print(output)
            
            if parsed_args.debug:
                duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                print(f"[DEBUG] Collection completed in {duration:.2f} seconds", file=sys.stderr)
                
            return 0
                
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            print(error_msg, file=sys.stderr)
            if parsed_args.debug:  # Show traceback in debug mode
                import traceback
                print("\n[DEBUG] Exception details:", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                print(f"\n[DEBUG] Current working directory: {os.getcwd()}", file=sys.stderr)
                print(f"[DEBUG] Python path: {sys.path}", file=sys.stderr)
            return 1
    
    return 0