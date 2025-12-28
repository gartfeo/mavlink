#!/usr/bin/env python3
"""
Test script for custom navlink MAVLink messages.

Sends a specified navlink message between SITL vehicles via mavlink-router
and verifies it is received correctly.

Usage:
    # Start SITL swarm first (use wsl profile for local testing):
    ROUTER_BIN=/path/to/mavlink-routerd ~/ardupilot/Tools/autotest/run_swarm.sh wsl 2

    # Test CHECK_IN message:
    python3 test_navlink_msg.py CHECK_IN boot_id=123 msg_seq=1 time_ms=1000 ttl_ms=5000

    # Test CHECK_OUT message:
    python3 test_navlink_msg.py CHECK_OUT boot_id=123 msg_seq=1 time_ms=1000 ttl_ms=5000 lat=40.31 lng=44.45 alt=1500

    # Test with custom ports:
    python3 test_navlink_msg.py CHECK_IN boot_id=1 --port1 14560 --port2 14570

    # List available navlink messages:
    python3 test_navlink_msg.py --list

Available messages (from navlink.xml):
    CHECK_IN              - boot_id, msg_seq, time_ms, ttl_ms
    CHECK_OUT             - boot_id, msg_seq, time_ms, ttl_ms, lat, lng, alt
    SWARM_HEARTBEAT       - boot_id, msg_seq, time_ms, ttl_ms, state
    AVAILABLE_TASK_REQUEST - boot_id, msg_seq, time_ms, ttl_ms, count, task_id[], task_type[], lat[], lng[], alt[]
    AVAILABLE_TASK_RESPONSE - boot_id, msg_seq, time_ms, ttl_ms, target_system, count, task_id[], time[]
    TASK_ASSIGN_REQUEST   - boot_id, msg_seq, time_ms, ttl_ms, target_system, task_id, task_type, lat, lng, alt
    TASK_ASSIGN_RESPONSE  - boot_id, msg_seq, time_ms, ttl_ms, target_system, task_id, accepted
    TASK_CONFIRM_REQUEST  - boot_id, msg_seq, time_ms, ttl_ms, task_id, task_type, lat, lng, alt
    TASK_CONFIRM_RESPONSE - boot_id, msg_seq, time_ms, ttl_ms, target_system, task_id, confirmed
    SLOT_HEARTBEAT        - boot_id, msg_seq, time_ms, ttl_ms, slot_id, state
    SLOT_CLAIM            - boot_id, msg_seq, time_ms, ttl_ms, slot_id, priority
    VOTE_PHASE            - boot_id, msg_seq, time_ms, ttl_ms, phase, round_id, proposal_id, vote
    SEARCH_STATUS         - boot_id, msg_seq, time_ms, ttl_ms, area_id, status, coverage_pct, detections
"""

import argparse
import sys
import time
import threading
from typing import Dict, List, Callable, Any

from pymavlink import mavutil

# Try to import navlink dialect
try:
    from pymavlink.dialects.v20 import navlink as mavlink
except ImportError:
    try:
        from pymavlink.dialects.v20 import ardupilotmega as mavlink
    except ImportError:
        print("Error: pymavlink dialect not available.")
        print("Make sure pymavlink is installed with navlink support.")
        sys.exit(1)


# Navlink message IDs (from navlink.xml)
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


class SimpleVehicle:
    """Simplified vehicle connection for testing."""

    def __init__(self, device: str, source_system: int = 255):
        self.source_system = source_system
        self.device = device
        self._conn = None
        self._stop_evt = threading.Event()
        self._reader_th = None
        self._callbacks: Dict[str, List[Callable]] = {}
        self._lock = threading.RLock()

    def connect(self, wait_heartbeat: bool = True, timeout: float = 10.0) -> bool:
        print(f"[SYS {self.source_system}] Connecting to {self.device}...")
        self._conn = mavutil.mavlink_connection(
            self.device,
            source_system=self.source_system,
            source_component=1,
            autoreconnect=True,
        )
        # Replace mav with navlink dialect
        self._conn.mav = mavlink.MAVLink(self._conn, srcSystem=self.source_system, srcComponent=1)

        if wait_heartbeat:
            print(f"[SYS {self.source_system}] Waiting for heartbeat...")
            msg = self._conn.wait_heartbeat(timeout=timeout)
            if msg:
                print(f"[SYS {self.source_system}] Got heartbeat from sysid {self._conn.target_system}")
            else:
                print(f"[SYS {self.source_system}] No heartbeat received!")
                return False

        self._reader_th = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_th.start()
        return True

    def _reader_loop(self):
        while not self._stop_evt.is_set():
            try:
                msg = self._conn.recv_match(blocking=True, timeout=0.5)
                if not msg:
                    continue

                mtype = msg.get_type()
                for cb in self._callbacks.get(mtype, []) + self._callbacks.get("*", []):
                    try:
                        cb(msg)
                    except Exception as e:
                        print(f"Callback error: {e}")
            except Exception as e:
                if not self._stop_evt.is_set():
                    print(f"Reader error: {e}")

    def on_message(self, msg_type: str, callback: Callable):
        if msg_type not in self._callbacks:
            self._callbacks[msg_type] = []
        self._callbacks[msg_type].append(callback)

    def send_message(self, msg):
        with self._lock:
            self._conn.mav.send(msg)

    def wait_heartbeat_from(self, target_sysid: int, timeout: float = 30.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = self._conn.recv_match(type='HEARTBEAT', blocking=True, timeout=1.0)
            if msg and msg.get_srcSystem() == target_sysid:
                print(f"[SYS {self.source_system}] Heartbeat from system {target_sysid}")
                return True
        return False

    def close(self):
        self._stop_evt.set()
        if self._reader_th:
            self._reader_th.join(timeout=2.0)
        if self._conn:
            self._conn.close()
        print(f"[SYS {self.source_system}] Closed")


def parse_params(params: List[str]) -> Dict[str, Any]:
    """Parse key=value parameters from command line."""
    result = {}
    for param in params:
        if '=' not in param:
            continue
        key, value = param.split('=', 1)
        # Try to convert to appropriate type
        try:
            if '.' in value:
                result[key] = float(value)
            elif value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
                result[key] = int(value)
            elif value.lower() in ('true', 'false'):
                result[key] = value.lower() == 'true'
            else:
                result[key] = value
        except ValueError:
            result[key] = value
    return result


def create_message(msg_name: str, params: Dict[str, Any]):
    """Create a MAVLink message by name with given parameters."""
    msg_name_upper = msg_name.upper()

    # Get the message class
    class_name = f"MAVLink_{msg_name.lower()}_message"
    if not hasattr(mavlink, class_name):
        raise ValueError(f"Unknown message: {msg_name}. Use --list to see available messages.")

    msg_class = getattr(mavlink, class_name)

    # Create message with parameters
    try:
        return msg_class(**params)
    except TypeError as e:
        # Get expected parameters from class
        import inspect
        sig = inspect.signature(msg_class.__init__)
        expected = [p for p in sig.parameters.keys() if p != 'self']
        raise ValueError(f"Invalid parameters for {msg_name}. Expected: {expected}. Error: {e}")


def list_messages():
    """List available navlink messages."""
    print("\nAvailable navlink messages:")
    print("-" * 60)

    for msg_name, msg_id in sorted(NAVLINK_MESSAGES.items(), key=lambda x: x[1]):
        class_name = f"MAVLink_{msg_name.lower()}_message"
        if hasattr(mavlink, class_name):
            msg_class = getattr(mavlink, class_name)
            import inspect
            sig = inspect.signature(msg_class.__init__)
            params = [p for p in sig.parameters.keys() if p != 'self']
            print(f"  {msg_name} (ID: {msg_id})")
            print(f"    Parameters: {', '.join(params)}")
        else:
            print(f"  {msg_name} (ID: {msg_id}) - NOT AVAILABLE IN DIALECT")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Test navlink MAVLink messages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("message", nargs="?", help="Message name (e.g., CHECK_IN)")
    parser.add_argument("params", nargs="*", help="Message parameters as key=value pairs")
    parser.add_argument("--port1", type=int, default=14560, help="UDP port for vehicle 1 (default: 14560)")
    parser.add_argument("--port2", type=int, default=14570, help="UDP port for vehicle 2 (default: 14570)")
    parser.add_argument("--timeout", type=int, default=5, help="Wait timeout in seconds (default: 5)")
    parser.add_argument("--list", action="store_true", help="List available navlink messages")

    args = parser.parse_args()

    if args.list:
        list_messages()
        return 0

    if not args.message:
        parser.print_help()
        return 1

    # Parse parameters
    params = parse_params(args.params)

    # Create the message
    try:
        msg = create_message(args.message, params)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    print("=" * 60)
    print(f"NAVLINK MESSAGE TEST: {args.message}")
    print("=" * 60)
    print(f"Parameters: {params}")
    print(f"Message: {msg.to_dict()}")
    print()

    received = []
    target_msg_type = args.message.upper()

    def create_handler(vehicle_id: int):
        def handler(msg):
            msg_type = msg.get_type()
            if msg_type == target_msg_type:
                print(f"[VEHICLE {vehicle_id}] <- [SYS {msg.get_srcSystem()}] {msg_type}: {msg.to_dict()}")
                received.append({
                    'receiver': vehicle_id,
                    'sender': msg.get_srcSystem(),
                    'type': msg_type,
                    'data': msg.to_dict()
                })
        return handler

    # Connect to vehicles
    vehicle1 = SimpleVehicle(f"udpin:0.0.0.0:{args.port1}", source_system=251)
    vehicle2 = SimpleVehicle(f"udpin:0.0.0.0:{args.port2}", source_system=252)

    try:
        if not vehicle1.connect(wait_heartbeat=True, timeout=10):
            print("Failed to connect to vehicle 1")
            return 1
        if not vehicle2.connect(wait_heartbeat=True, timeout=10):
            print("Failed to connect to vehicle 2")
            return 1

        # Register handlers
        vehicle1.on_message("*", create_handler(1))
        vehicle2.on_message("*", create_handler(2))

        # Wait for cross-heartbeats
        vehicle2.wait_heartbeat_from(1, 10.0)
        vehicle1.wait_heartbeat_from(2, 10.0)

        print("-" * 40)
        print(f"Sending {args.message} from Vehicle 2...")
        print("-" * 40)

        vehicle2.send_message(msg)

        print(f"\nWaiting {args.timeout} seconds for message routing...")
        time.sleep(args.timeout)

        # Summary
        print("\n" + "=" * 60)
        print("TEST RESULTS")
        print("=" * 60)

        if received:
            for r in received:
                print(f"  Vehicle {r['receiver']} <- SYS {r['sender']}: {r['type']}")
            print(f"\nTotal messages received: {len(received)}")
            print("\n*** TEST PASSED ***")
            return 0
        else:
            print("  No messages received!")
            print("\n*** TEST FAILED ***")
            return 1

    except KeyboardInterrupt:
        print("\nInterrupted")
        return 1
    finally:
        vehicle1.close()
        vehicle2.close()


if __name__ == "__main__":
    sys.exit(main())
