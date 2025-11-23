import argparse
import json
import sys
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
    # Schema validation is now handled by the schema itself
    
    return parser

def main(args: Optional[List[str]] = None) -> int:
    """Main entry point for the CLI.
    
    Args:
        args: Command line arguments (defaults to sys.argv[1:])
        
    Returns:
        int: Exit code (0 for success, non-zero for error)
    """
    # Parse command line arguments
    parser = build_parser()
    parsed_args = parser.parse_args(args)
    
    if parsed_args.cmd == "collect":
        # Get available collectors
        available_collectors = load_collectors()
        
        # Check if all requested collectors exist
        invalid = [name for name in parsed_args.collectors if name not in available_collectors]
        if invalid:
            print(f"Error: Unknown collectors: {', '.join(invalid)}", file=sys.stderr)
            print(f"Available collectors: {', '.join(sorted(available_collectors.keys()))}", file=sys.stderr)
            return 1
        
        result = {}

        try:
            # Run the collectors
            result = collect_all(
                collector_names=parsed_args.collectors,
                schema_path=str(parsed_args.schema) if parsed_args.schema else str(bundled_schema_path())
            )
            
            # Convert to JSON
            output = json.dumps(result, indent=2)
            
            # Write to file or stdout
            if parsed_args.output:
                parsed_args.output.write_text(output)
                print(f"Results written to {parsed_args.output}", file=sys.stderr)
            else:
                print(output)
                
            return 0
            
        except Exception as e:
            print(f"Error in cli.py parsing result from collect_all(): {e}", file=sys.stderr)
            if hasattr(e, '__traceback__'):
                import traceback
                traceback.print_exc(file=sys.stderr)
            return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())