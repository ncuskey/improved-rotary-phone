#!/usr/bin/env python3
"""
Comprehensive test runner for ISBN Lot Optimizer.

This script provides various testing modes:
- Fast: Only unit tests
- Full: All tests including integration and slow tests
- Coverage: Run with code coverage reporting
- Specific: Run specific test file or test

Usage:
    python run_tests.py                    # Run fast tests (unit only)
    python run_tests.py --full             # Run all tests
    python run_tests.py --coverage         # Run with coverage
    python run_tests.py --file test_metadata.py  # Run specific file
    python run_tests.py --verbose          # Verbose output
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run_command(cmd: list[str], description: str) -> int:
    """Run a command and return exit code."""
    print(f"\n{'=' * 70}")
    print(f"{description}")
    print(f"{'=' * 70}")
    print(f"Running: {' '.join(cmd)}\n")

    result = subprocess.run(cmd)
    return result.returncode


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(
        description="Comprehensive test runner for ISBN Lot Optimizer"
    )

    parser.add_argument(
        "--fast",
        action="store_true",
        default=True,
        help="Run only fast unit tests (default)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run all tests including integration and slow tests",
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Run tests with code coverage reporting",
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Run specific test file (e.g., test_metadata.py)",
    )
    parser.add_argument(
        "--test",
        type=str,
        help="Run specific test (e.g., TestMetadata::test_function)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--markers",
        action="store_true",
        help="List available test markers",
    )
    parser.add_argument(
        "--failfast",
        "-x",
        action="store_true",
        help="Stop on first failure",
    )

    args = parser.parse_args()

    # Change to project root
    project_root = Path(__file__).parent
    import os
    os.chdir(project_root)

    # List markers if requested
    if args.markers:
        cmd = ["pytest", "--markers"]
        return run_command(cmd, "Available Test Markers")

    # Build pytest command
    cmd = ["pytest"]

    # Add verbosity
    if args.verbose:
        cmd.append("-vv")

    # Add failfast
    if args.failfast:
        cmd.append("-x")

    # Determine test selection
    if args.file:
        cmd.append(f"tests/{args.file}")
        description = f"Running tests from {args.file}"
    elif args.test:
        cmd.append(f"-k {args.test}")
        description = f"Running test: {args.test}"
    elif args.full:
        # Run all tests
        description = "Running ALL tests (unit + integration + slow)"
    else:
        # Fast mode: only unit tests
        cmd.extend(["-m", "unit"])
        description = "Running FAST tests (unit tests only)"

    # Add coverage if requested
    if args.coverage:
        cmd.extend([
            "--cov=shared",
            "--cov=isbn_lot_optimizer",
            "--cov=isbn_web",
            "--cov-report=html",
            "--cov-report=term-missing",
        ])
        description += " with code coverage"

    # Run tests
    exit_code = run_command(cmd, description)

    # Print summary
    print(f"\n{'=' * 70}")
    if exit_code == 0:
        print("✅ All tests passed!")
    else:
        print(f"❌ Tests failed with exit code: {exit_code}")
    print(f"{'=' * 70}\n")

    if args.coverage and exit_code == 0:
        print("📊 Coverage report generated at: htmlcov/index.html")
        print("   Open in browser: file://" + str(project_root / "htmlcov" / "index.html"))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
