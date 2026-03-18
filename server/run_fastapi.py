#!/usr/bin/env python3
"""
PyInstaller entry point for the FastAPI server.

This file is used by PyInstaller to create a standalone executable.
"""
import multiprocessing

if __name__ == "__main__":
    # Required for PyInstaller + multiprocessing on macOS
    multiprocessing.freeze_support()
    
    from fastapi_app.main import run_server
    run_server()
