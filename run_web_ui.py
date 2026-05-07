#!/usr/bin/env python3
"""
IC Tester Web UI Entry Point
Last edited: 2026-04-09
Purpose: Launch the Bootstrap-based web UI for the IC Tester
Dependencies: flask, flask-socketio, ic_tester_app

This script launches the modern web-based interface for the IC Tester.
It uses Flask with SocketIO for real-time communication between the
browser and the Arduino hardware.

Usage:
    python run_web_ui.py              # Run on default port 5000
    python run_web_ui.py --port 8080  # Run on custom port
    python run_web_ui.py --host 0.0.0.0 --port 5000  # Accessible from network
"""

import sys
import argparse
from pathlib import Path

# Add ic_tester_app to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from ic_tester_app.web_ui import run_web_ui
except ImportError as e:
    print(f"Error importing web_ui module: {e}")
    print("\nPlease ensure all dependencies are installed:")
    print("  pip install -r requirements.txt")
    sys.exit(1)


def main():
    """Parse arguments and start the web UI server."""
    parser = argparse.ArgumentParser(
        description='IC Tester Web UI - Bootstrap-based web interface',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Default: localhost:5050
  %(prog)s --port 8080              # Use port 8080
  %(prog)s --host 0.0.0.0           # Allow external connections
  %(prog)s --debug                  # Enable debug mode
        """
    )
    
    parser.add_argument(
        '--host', 
        default='127.0.0.1',
        help='Host to bind to (default: 127.0.0.1)'
    )
    parser.add_argument(
        '--port', 
        type=int, 
        default=5050,
        help='Port to listen on (default: 5050)'
    )
    parser.add_argument(
        '--debug', 
        action='store_true',
        help='Enable Flask debug mode (auto-reload on code changes)'
    )
    
    args = parser.parse_args()
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                   IC Tester Web UI                             ║
║                                                                ║
║  Open your browser and navigate to:                            ║
║  http://{args.host}:{args.port:<5}                              ║
║                                                                ║
║  Press Ctrl+C to stop the server                               ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    try:
        run_web_ui(host=args.host, port=args.port, debug=args.debug)
    except KeyboardInterrupt:
        print("\n\nShutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"\nError starting server: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
