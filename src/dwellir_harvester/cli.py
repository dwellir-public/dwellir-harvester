import argparse
import json
import logging
import os
import sys
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any

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

# Add the parent directory to the Python path if running directly
if __name__ == "__main__" and __package__ is None:
    import os
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from dwellir_harvester.core import collect_all, bundled_schema_path, load_collectors, run_collector
else:
    from .core import collect_all, bundled_schema_path, load_collectors, run_collector

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
    # Allow a single string of arguments (e.g., when VS Code passes one promptString)
    if args is None and len(sys.argv) == 2 and isinstance(sys.argv[1], str):
        args = shlex.split(sys.argv[1])
    elif isinstance(args, list) and len(args) == 1 and isinstance(args[0], str):
        args = shlex.split(args[0])

    parser = build_parser()
    parsed_args = parser.parse_args(args)

    # Configure logging
    log = setup_logging(debug=parsed_args.debug)
    log.debug("CLI main() started")
    if parsed_args.cmd == "collect":
        start_time = datetime.now(timezone.utc)
        
        log.debug(f"Starting collection process at {start_time.isoformat()}")
        log.debug(f"Python version: {sys.version}")
        log.debug(f"Command line arguments: {sys.argv}")
        log.debug(f"Parsed arguments: {vars(parsed_args)}")
        
        try:
            # Get the schema path (use bundled schema if not specified)
            schema_path = parsed_args.schema or str(bundled_schema_path())
            
            log.debug(f"Using schema path: {schema_path}")
            log.debug("Loading all available collectors...")
            
            # Load all available collectors
            all_collectors = load_collectors()
            
            log.debug(f"Found {len(all_collectors)} total collectors")
            log.debug(f"Requested collectors: {parsed_args.collectors}")
            
            # Filter to only the requested collectors
            collectors = []
            for name in parsed_args.collectors:
                if name not in all_collectors:
                    log.warning(f"Unknown collector '{name}', skipping")
                    log.debug(f"Available collectors: {list(all_collectors.keys())}")
                    continue
                collectors.append(all_collectors[name])
            
            if not collectors:
                log.error("No valid collectors specified")
                log.debug("No valid collectors found after filtering")
                return 1
            
            log.debug(f"Running {len(collectors)} collectors: {[c.NAME for c in collectors]}")
            log.debug(f"Validation is {'enabled' if parsed_args.validate else 'disabled'}")
            
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
                log.debug(f"Writing results to {parsed_args.output}")
                try:
                    parsed_args.output.write_text(output)
                    log.info(f"Results written to {parsed_args.output}")
                    log.debug(f"Successfully wrote {len(output)} bytes to {parsed_args.output}")
                except Exception as e:
                    log.error(f"Error writing to {parsed_args.output}: {str(e)}", exc_info=parsed_args.debug)
                    return 1
            else:
                log.debug("Outputting results to stdout")
                print(output)
            
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            log.debug(f"Collection completed in {duration:.2f} seconds")
                
            return 0
                
        except Exception as e:
            log.error(f"Error: {str(e)}", exc_info=parsed_args.debug)
            if parsed_args.debug:
                log.debug(f"Current working directory: {os.getcwd()}")
                log.debug(f"Python path: {sys.path}")
            return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
