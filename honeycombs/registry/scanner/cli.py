#!/usr/bin/env python3
"""
Command-line interface for the scanner.
"""
import argparse
from .core import HoneycombScanner

def main():
    parser = argparse.ArgumentParser(description='Honeycomb Scanner')
    parser.add_argument('scan', nargs='?', default='scan')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--full-check', action='store_true')
    parser.add_argument('--validate-tasks', action='store_true')
    parser.add_argument('--ahimsa', action='store_true')
    parser.add_argument('--deadlines', action='store_true')
    parser.add_argument('--integrity', action='store_true')
    parser.add_argument('--no-cache', action='store_true')
    parser.add_argument('--base-path', default='.')
    args = parser.parse_args()
    scanner = HoneycombScanner(
        base_path=args.base_path,
        full_check=args.full_check,
        validate_tasks=args.validate_tasks,
        ahimsa=args.ahimsa,
        deadlines=args.deadlines,
        integrity=args.integrity,
        no_cache=args.no_cache,
        verbose=args.verbose
    )
    scanner.scan_all_honeycombs()

if __name__ == "__main__":
    main()
