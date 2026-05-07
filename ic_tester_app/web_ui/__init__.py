# ic_tester_app/web_ui/__init__.py
# Last edited: 2026-04-09
# Purpose: Web UI package initialization for Bootstrap-based interface
# Dependencies: flask, flask-socketio

"""
Bootstrap Web UI for IC Tester.

This package provides a modern web-based interface using Flask and Bootstrap 5,
replacing the legacy tkinter GUI. It uses WebSocket for real-time communication
with the Arduino hardware.
"""

from .app import create_app, run_web_ui

__all__ = ['create_app', 'run_web_ui']
