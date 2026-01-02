#!/usr/bin/env python3
"""
Check navlink message CRCs match across all components.

This script verifies that CRCs for navlink messages are consistent between:
- pymavlink (Python dialect)
- ArduPilot C headers (build/sitl/libraries/GCS_MAVLink/include/mavlink/v2.0/)
- mavlink-router C headers (mavlink-router/modules/mavlink_c_library_v2/)

Usage:
    python3 check_navlink_crcs.py [--ardupilot PATH] [--router PATH]

Example:
    python3 check_navlink_crcs.py
    python3 check_navlink_crcs.py --ardupilot ~/ardupilot --router ~/mavlink-router
"""

import argparse
import os
import re
import sys
from pathlib import Path

# Navlink message IDs
NAVLINK_MESSAGES = {
    'CHECK_IN': 25002,
    'CHECK_OUT': 25003,
    'SWARM_HEARTBEAT': 25004,
    'AVAILABLE_TASK_REQUEST': 25104,
    'AVAILABLE_TASK_RESPONSE': 25105,
    'TASK_ASSIGN_REQUEST': 25106,
    'TASK_ASSIGN_RESPONSE': 25107,
    'TASK_CONFIRM_REQUEST': 25108,
    'TASK_CONFIRM_RESPONSE': 25109,
    'SLOT_HEARTBEAT': 25200,
    'SLOT_CLAIM': 25201,
    'VOTE_PHASE': 25202,
    'SEARCH_STATUS': 25300,
}


def get_pymavlink_crcs():
    """Get CRCs from pymavlink dialect."""
    try:
        from pymavlink.dialects.v20 import ardupilotmega as mav
    except ImportError:
        print("Error: pymavlink not installed or ardupilotmega dialect not available")
        return None

    crcs = {}
    for name, msg_id in NAVLINK_MESSAGES.items():
        class_name = f"MAVLink_{name.lower()}_message"
        if hasattr(mav, class_name):
            msg_class = getattr(mav, class_name)
            # Get actual message length from format string or calculate from field sizes
            msg_len = 0
            if hasattr(msg_class, 'native_format'):
                # Calculate from struct format
                import struct
                try:
                    msg_len = struct.calcsize('<' + msg_class.native_format.replace('Z', 's'))
                except:
                    pass
            if msg_len == 0:
                # Fallback: use fieldtypes to calculate
                type_sizes = {'uint8_t': 1, 'int8_t': 1, 'uint16_t': 2, 'int16_t': 2,
                              'uint32_t': 4, 'int32_t': 4, 'uint64_t': 8, 'int64_t': 8,
                              'float': 4, 'double': 8, 'char': 1}
                for ft in msg_class.fieldtypes:
                    if '[' in ft:
                        base, count = ft.rstrip(']').split('[')
                        msg_len += type_sizes.get(base, 4) * int(count)
                    else:
                        msg_len += type_sizes.get(ft, 4)
            crcs[msg_id] = {
                'name': name,
                'crc': msg_class.crc_extra,
                'len': msg_len,
            }
        else:
            print(f"Warning: {name} not found in pymavlink")
    return crcs


def parse_c_header_crcs(header_path):
    """Parse MAVLINK_MESSAGE_CRCS from a C header file."""
    if not os.path.exists(header_path):
        return None

    with open(header_path, 'r') as f:
        content = f.read()

    # Find MAVLINK_MESSAGE_CRCS definition - it's all on one line with double braces
    match = re.search(r'#define MAVLINK_MESSAGE_CRCS\s*\{\{', content)
    if not match:
        return None

    # Parse each entry: {msg_id, crc, min_len, max_len, flags, target_sys_ofs, target_comp_ofs}
    crcs = {}
    for entry in re.findall(r'\{(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*\d+,\s*\d+,\s*\d+\}', content):
        msg_id = int(entry[0])
        crc = int(entry[1])
        min_len = int(entry[2])
        max_len = int(entry[3])
        if msg_id in NAVLINK_MESSAGES.values():
            name = [k for k, v in NAVLINK_MESSAGES.items() if v == msg_id][0]
            crcs[msg_id] = {
                'name': name,
                'crc': crc,
                'len': max_len,
            }
    return crcs


def compare_crcs(source1_name, source1_crcs, source2_name, source2_crcs):
    """Compare CRCs between two sources. Returns tuple of (errors, warnings)."""
    errors = []
    warnings = []

    if source1_crcs is None or source2_crcs is None:
        return errors, warnings

    all_ids = set(source1_crcs.keys()) | set(source2_crcs.keys())

    for msg_id in sorted(all_ids):
        if msg_id not in source1_crcs:
            errors.append({
                'msg_id': msg_id,
                'name': source2_crcs[msg_id]['name'],
                'issue': f'Missing in {source1_name}',
            })
        elif msg_id not in source2_crcs:
            errors.append({
                'msg_id': msg_id,
                'name': source1_crcs[msg_id]['name'],
                'issue': f'Missing in {source2_name}',
            })
        else:
            s1 = source1_crcs[msg_id]
            s2 = source2_crcs[msg_id]
            if s1['crc'] != s2['crc']:
                errors.append({
                    'msg_id': msg_id,
                    'name': s1['name'],
                    'issue': f"CRC mismatch: {source1_name}={s1['crc']} vs {source2_name}={s2['crc']}",
                })
            # Length differences are expected for messages with arrays (max vs base size)
            # Only warn, don't treat as error

    return errors, warnings


def main():
    parser = argparse.ArgumentParser(
        description="Check navlink message CRCs match across components",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--ardupilot",
        default=os.path.expanduser("~/ardupilot"),
        help="Path to ardupilot directory (default: ~/ardupilot)"
    )
    parser.add_argument(
        "--router",
        default=os.path.expanduser("~/mavlink-router"),
        help="Path to mavlink-router directory (default: ~/mavlink-router)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show all CRC values"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("NAVLINK CRC CONSISTENCY CHECK")
    print("=" * 60)

    # Get CRCs from all sources
    sources = {}

    # 1. pymavlink
    print("\n[1] Checking pymavlink...")
    sources['pymavlink'] = get_pymavlink_crcs()
    if sources['pymavlink']:
        print(f"    Found {len(sources['pymavlink'])} navlink messages")
    else:
        print("    ERROR: Could not read pymavlink CRCs")

    # 2. ArduPilot C headers
    ardupilot_header = os.path.join(
        args.ardupilot,
        "build/sitl/libraries/GCS_MAVLink/include/mavlink/v2.0/ardupilotmega/ardupilotmega.h"
    )
    print(f"\n[2] Checking ArduPilot headers...")
    print(f"    Path: {ardupilot_header}")
    sources['ardupilot'] = parse_c_header_crcs(ardupilot_header)
    if sources['ardupilot']:
        print(f"    Found {len(sources['ardupilot'])} navlink messages")
    else:
        print("    WARNING: Could not read ArduPilot headers (run ./waf plane first)")

    # 3. mavlink-router C headers
    router_header = os.path.join(
        args.router,
        "modules/mavlink_c_library_v2/ardupilotmega/ardupilotmega.h"
    )
    print(f"\n[3] Checking mavlink-router headers...")
    print(f"    Path: {router_header}")
    sources['router'] = parse_c_header_crcs(router_header)
    if sources['router']:
        print(f"    Found {len(sources['router'])} navlink messages")
    else:
        print("    WARNING: Could not read mavlink-router headers")

    # Show verbose output
    if args.verbose and sources['pymavlink']:
        print("\n" + "-" * 60)
        print("CRC VALUES (from pymavlink)")
        print("-" * 60)
        print(f"{'Message':<30} {'ID':>6} {'CRC':>5} {'Len':>5}")
        print("-" * 60)
        for msg_id in sorted(sources['pymavlink'].keys()):
            info = sources['pymavlink'][msg_id]
            print(f"{info['name']:<30} {msg_id:>6} {info['crc']:>5} {info['len']:>5}")

    # Compare all pairs
    print("\n" + "=" * 60)
    print("COMPARISON RESULTS")
    print("=" * 60)

    all_errors = []
    pairs = [
        ('pymavlink', 'ardupilot'),
        ('pymavlink', 'router'),
        ('ardupilot', 'router'),
    ]

    for name1, name2 in pairs:
        if sources.get(name1) and sources.get(name2):
            errors, warnings = compare_crcs(name1, sources[name1], name2, sources[name2])
            if errors:
                print(f"\n{name1} vs {name2}: {len(errors)} error(s)")
                for e in errors:
                    print(f"  - {e['name']} (ID {e['msg_id']}): {e['issue']}")
                all_errors.extend(errors)
            else:
                print(f"\n{name1} vs {name2}: OK")

    # Summary
    print("\n" + "=" * 60)
    if all_errors:
        print(f"FAILED: {len(all_errors)} CRC error(s) found!")
        print("\nTo fix CRC mismatches:")
        print("1. Regenerate C headers:")
        print("   cd mavlink-router/modules/mavlink_c_library_v2")
        print("   mavgen.py --lang=C --wire-protocol=2.0 -o . message_definitions/ardupilotmega.xml")
        print("2. Rebuild mavlink-router:")
        print("   cd mavlink-router && ninja -C build")
        print("=" * 60)
        return 1
    else:
        print("PASSED: All CRCs match!")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())
