import sys
import os

def main():
    # Add the parent directory to the Python path if running directly
    if __package__ is None:
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    
    try:
        from dwellir_harvester.cli import main as cli_main, build_parser
    except ImportError as e:
        print(f"Error importing cli module: {e}", file=sys.stderr)
        return 1
    
    # Show help if no arguments are provided
    if len(sys.argv) == 1:
        parser = build_parser()
        parser.print_help()
        return 0
    
    return cli_main()

if __name__ == "__main__":
    sys.exit(main())