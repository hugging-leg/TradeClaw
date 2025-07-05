#!/usr/bin/env python3
"""
Test runner script for the Trading Agent system.
"""

import subprocess
import sys
import os
from pathlib import Path


def run_tests():
    """Run all tests with appropriate configuration."""
    # Change to the project directory
    project_dir = Path(__file__).parent
    os.chdir(project_dir)
    
    # Basic test command
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/",
        "-v",
        "--tb=short",
        "--strict-markers",
        "--strict-config"
    ]
    
    # Check if coverage is requested
    if "--coverage" in sys.argv:
        cmd.extend([
            "--cov=src",
            "--cov-report=html",
            "--cov-report=term-missing",
            "--cov-fail-under=80"
        ])
    
    # Check if only unit tests are requested
    if "--unit" in sys.argv:
        cmd.extend(["-m", "unit"])
    
    # Check if integration tests are requested
    if "--integration" in sys.argv:
        cmd.extend(["-m", "integration"])
    
    # Check if slow tests should be skipped
    if "--fast" in sys.argv:
        cmd.extend(["-m", "not slow"])
    
    # Add any additional pytest arguments
    additional_args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    cmd.extend(additional_args)
    
    print(f"Running: {' '.join(cmd)}")
    print("-" * 50)
    
    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\nTests interrupted by user")
        return 1
    except Exception as e:
        print(f"Error running tests: {e}")
        return 1


def main():
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] in ["--help", "-h"]:
        print("""
Trading Agent Test Runner

Usage:
    python run_tests.py [options] [test_files...]

Options:
    --coverage          Run tests with coverage reporting
    --unit              Run only unit tests
    --integration       Run only integration tests
    --fast              Skip slow tests
    --help, -h          Show this help message

Examples:
    python run_tests.py                    # Run all tests
    python run_tests.py --coverage         # Run with coverage
    python run_tests.py --unit             # Run only unit tests
    python run_tests.py --fast             # Skip slow tests
    python run_tests.py tests/test_config.py  # Run specific test file
        """)
        return 0
    
    return run_tests()


if __name__ == "__main__":
    sys.exit(main()) 