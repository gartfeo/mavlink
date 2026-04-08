# Adding Custom MAVLink Messages

This guide explains how to add custom MAVLink messages to the navlink dialect and integrate them across the ArduPilot ecosystem.

## Overview

Adding a custom MAVLink message involves updating 4 repositories:

| Step | Repository | Branch | Purpose |
|------|------------|--------|---------|
| 1 | `mavlink` | navlink-4.6 | Define message in navlink.xml |
| 2 | `ardupilot` | ArduPilot-4.6 | Update submodule, rebuild pymavlink & SITL |
| 3 | `c_library_v2` | ArduPilot-4.6 | Copy navlink.xml for C library |
| 4 | `mavlink-router` | navlink-4.6 | Update submodule, rebuild router |

## Prerequisites

- All repositories cloned locally
- ArduPilot build environment set up
- Python 3 with pip

## Step 1: Define Message in mavlink Repository

### 1.1 Edit navlink.xml

Location: `mavlink/message_definitions/v1.0/navlink.xml`

```xml
<?xml version="1.0"?>
<mavlink>
  <messages>
    <!-- Add your new message here -->
    <message id="25XXX" name="YOUR_MESSAGE_NAME">
      <description>Description of your message.</description>
      <field type="uint8_t" name="field1">Description of field1.</field>
      <field type="float" name="field2">Description of field2.</field>
      <!-- Add more fields as needed -->
    </message>
  </messages>
</mavlink>
```

### Message ID Rules
- Use IDs in range 25001-25999 for navlink messages
- Check existing IDs to avoid conflicts:
  - 25001: NAVLINK_TEST
  - 25002: CHECK_IN
  - 25003: CHECK_OUT
  - 25004: SWARM_HEARTBEAT
  - 25104-25109: Task messages
  - 25200-25202: Slot/voting messages (SLOT_HEARTBEAT, SLOT_CLAIM, VOTE_PHASE)
  - 25300: SEARCH_STATUS

### Supported Field Types
- `uint8_t`, `int8_t`
- `uint16_t`, `int16_t`
- `uint32_t`, `int32_t`
- `uint64_t`, `int64_t`
- `float`, `double`
- Arrays: `uint8_t[N]`, `float[N]`, etc.

### 1.2 Commit and Push

```bash
cd mavlink
git add message_definitions/v1.0/navlink.xml
git commit -m "Add YOUR_MESSAGE_NAME message"
git push origin navlink-4.6
```

## Step 2: Update ArduPilot

### 2.1 Update mavlink Submodule

```bash
cd ardupilot/modules/mavlink
git fetch origin
git checkout navlink-4.6
git pull origin navlink-4.6
```

### 2.2 Reinstall pymavlink

```bash
# Uninstall existing pymavlink
pip uninstall pymavlink -y

# Install from source with updated dialect
cd ardupilot/modules/mavlink/pymavlink
python3 setup.py install --user
```

### 2.3 Verify Installation

```bash
python3 -c "
from pymavlink.dialects.v20 import ardupilotmega as mav
print('YOUR_MESSAGE_NAME ID:', mav.MAVLINK_MSG_ID_YOUR_MESSAGE_NAME)
"
```

### 2.4 Rebuild ArduPilot SITL

```bash
cd ardupilot
./waf configure --board sitl
./waf plane
```

### 2.5 Commit Submodule Update

```bash
cd ardupilot
git add modules/mavlink
git commit -m "Update mavlink submodule with YOUR_MESSAGE_NAME"
git push origin ArduPilot-4.6
```

## Step 3: Update c_library_v2

### 3.1 Copy navlink.xml

```bash
cp mavlink/message_definitions/v1.0/navlink.xml \
   c_library_v2/message_definitions/navlink.xml
```

### 3.2 Regenerate C Headers

```bash
# Find mavgen.py location: which mavgen.py or ~/.local/bin/mavgen.py
mavgen.py --lang=C --wire-protocol=2.0 \
    -o c_library_v2 \
    c_library_v2/message_definitions/ardupilotmega.xml
```

**Important:** Generate from `ardupilotmega.xml` (which includes navlink.xml) to ensure consistent headers across all dialects.

### 3.3 Commit and Push

```bash
cd c_library_v2
git add message_definitions/navlink.xml navlink/
git commit -m "Add YOUR_MESSAGE_NAME message"
git push origin ArduPilot-4.6
```

## Step 4: Update mavlink-router

### 4.1 Update c_library_v2 Submodule

```bash
cd mavlink-router/modules/mavlink_c_library_v2
git fetch origin
git checkout ArduPilot-4.6
git pull origin ArduPilot-4.6
```

### 4.2 Rebuild mavlink-router

```bash
cd mavlink-router
ninja -C build
```

Or for fresh build:
```bash
meson setup build --wipe
ninja -C build
```

### 4.3 Commit Submodule Update

```bash
cd mavlink-router
git add modules/mavlink_c_library_v2
git commit -m "Update mavlink submodule with YOUR_MESSAGE_NAME"
git push origin navlink-4.6
```

## Step 5: Test the New Message

### 5.1 Start SITL Swarm

For WSL/local testing:
```bash
ROUTER_BIN=/path/to/mavlink-router/build/src/mavlink-routerd \
    ~/ardupilot/Tools/autotest/run_swarm.sh wsl 2
```

For Windows GCS testing:
```bash
~/ardupilot/Tools/autotest/run_swarm.sh sim 2
```

### 5.2 Run Test Script

```bash
cd mavlink

# List available messages
python3 test_navlink_msg.py --list

# Test your new message
python3 test_navlink_msg.py YOUR_MESSAGE_NAME field1=value1 field2=value2

# Example: Test CHECK_IN
python3 test_navlink_msg.py CHECK_IN boot_id=123 msg_seq=1 time_ms=1000 ttl_ms=5000

# Example: Test CHECK_OUT
python3 test_navlink_msg.py CHECK_OUT boot_id=123 msg_seq=1 time_ms=1000 ttl_ms=5000 lat=40.31 lng=44.45 alt=1500
```

### 5.3 Expected Output

```
============================================================
NAVLINK MESSAGE TEST: YOUR_MESSAGE_NAME
============================================================
Parameters: {'field1': value1, 'field2': value2}
...
*** TEST PASSED ***
```

## SITL Profiles Reference

| Profile | Description | Router Endpoints |
|---------|-------------|------------------|
| `sim` | Windows GCS testing | `$WIN_IP:14500,14550,...` |
| `sim_only` | Local only | `0.0.0.0:15000` |
| `wsl` | WSL local testing | `0.0.0.0:14500,14550,...` |

## Troubleshooting

### Message Not Found in Dialect

```bash
# Verify navlink.xml includes your message
grep YOUR_MESSAGE_NAME mavlink/message_definitions/v1.0/navlink.xml

# Reinstall pymavlink
pip uninstall pymavlink -y
cd ardupilot/modules/mavlink/pymavlink
python3 setup.py install --user
```

### CRC Mismatch / Messages Not Routed

If some messages work but others don't, the C headers may be inconsistent.
Navlink message headers should only exist in `c_library_v2/navlink/`. If
duplicates exist in `c_library_v2/ardupilotmega/`, the old CRCs take
precedence and the router silently drops messages with mismatched CRCs.

```bash
# Check for conflicting header files (navlink msgs should NOT be in ardupilotmega/)
ls c_library_v2/ardupilotmega/mavlink_msg_check_in.h 2>/dev/null && echo "DUPLICATES FOUND"
ls c_library_v2/ardupilotmega/mavlink_msg_task_assign_request.h 2>/dev/null && echo "DUPLICATES FOUND"

# Remove only the navlink duplicates from ardupilotmega/ (do NOT rm mavlink_msg_*.h)
cd c_library_v2/ardupilotmega
rm -f mavlink_msg_check_in.h mavlink_msg_check_out.h mavlink_msg_swarm_heartbeat.h \
     mavlink_msg_available_task_request.h mavlink_msg_available_task_response.h \
     mavlink_msg_task_assign_request.h mavlink_msg_task_assign_response.h \
     mavlink_msg_task_confirm_request.h mavlink_msg_task_confirm_response.h \
     mavlink_msg_slot_heartbeat.h mavlink_msg_slot_claim.h \
     mavlink_msg_vote_phase.h mavlink_msg_search_status.h
cd ../..

# Regenerate
python3 ~/.local/bin/mavgen.py --lang=C --wire-protocol=2.0 \
    -o c_library_v2 \
    c_library_v2/message_definitions/ardupilotmega.xml

# Verify CRCs match between pymavlink and c_library_v2
python3 -c "
from pymavlink.dialects.v20 import ardupilotmega as mav
for msg_id, cls in sorted(mav.mavlink_map.items()):
    if 25000 <= msg_id <= 26000:
        print(f'{cls.__name__} (ID:{msg_id}): crc_extra={cls.crc_extra}')
"

# Rebuild mavlink-router
ninja -C mavlink-router/build
```

### SITL Bind Errors

```bash
# Kill existing processes
pkill arduplane
pkill mavlink-routerd

# Restart swarm
~/ardupilot/Tools/autotest/run_swarm.sh wsl 2
```

### No Heartbeat Received

- Verify SITL is running: `pgrep -a arduplane`
- Verify mavlink-router is running: `pgrep -a mavlink-routerd`
- Check correct ports in test script

## Quick Reference

### Add New Simple Message

```xml
<message id="25010" name="MY_STATUS">
  <description>Custom status message.</description>
  <field type="uint8_t" name="status">Status code.</field>
  <field type="uint32_t" name="timestamp">Timestamp in ms.</field>
</message>
```

### Test Command

```bash
python3 test_navlink_msg.py MY_STATUS status=1 timestamp=12345
```

## File Locations

| Repository | navlink.xml Location |
|------------|----------------------|
| `mavlink` | `message_definitions/v1.0/navlink.xml` |
| `c_library_v2` | `message_definitions/navlink.xml` |
