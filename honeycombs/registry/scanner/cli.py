#!/usr/bin/env python3
"""
Command-line interface for the scanner.
Full functionality from original honeycomb_scanner.py
"""
import argparse
from .core import HoneycombScanner

def main():
    parser = argparse.ArgumentParser(
        description='Honeycomb Scanner v2.0 — Unified System Health Scanner for Mandala Symbiosis'
    )
    parser.add_argument(
        'scan',
        nargs='?',
        default='scan',
        help='Run scan (default)'
    )
    parser.add_argument(
        '--full-check',
        action='store_true',
        help='Run all health checks'
    )
    parser.add_argument(
        '--validate-tasks',
        action='store_true',
        help='Run task validation only'
    )
    parser.add_argument(
        '--ahimsa',
        action='store_true',
        help='Run Ahimsa filter only'
    )
    parser.add_argument(
        '--deadlines',
        action='store_true',
        help='Run deadline monitoring only'
    )
    parser.add_argument(
        '--integrity',
        action='store_true',
        help='Run integrity check only'
    )
    parser.add_argument(
        '--base-path',
        default='.',
        help='Base path to repository (default: .)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force full rescan'
    )
    parser.add_argument(
        '--no-cache',
        action='store_true',
        help='Ignore scan_state.json entirely'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
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
