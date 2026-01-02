# Adding Custom MAVLink Messages

This guide explains how to add custom MAVLink messages to the navlink dialect and integrate them across the ArduPilot ecosystem.

## Overview

Adding a custom MAVLink message involves updating 4 repositories:

| Step | Repository | Branch | Purpose |
|------|------------|--------|---------|
| 1 | `mavlink` | Plane-4.5/navlink | Define message in navlink.xml |
| 2 | `ardupilot` | Plane-4.5 | Update submodule, rebuild pymavlink & SITL |
| 3 | `c_library_v2` | Plane-4.5/navlink | Copy navlink.xml, regenerate C headers |
| 4 | `mavlink-router` | Plane-4.5/navlink | Update submodule, rebuild router |

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
  - 25002: CHECK_IN
  - 25003: CHECK_OUT
  - 25004: SWARM_HEARTBEAT
  - 25104-25109: Task messages (AVAILABLE_TASK_*, TASK_ASSIGN_*, TASK_CONFIRM_*)
  - 25200: SLOT_HEARTBEAT
  - 25201: SLOT_CLAIM
  - 25202: VOTE_PHASE
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
git push origin Plane-4.5/navlink
```

## Step 2: Update ArduPilot

### 2.1 Update mavlink Submodule

```bash
cd ardupilot/modules/mavlink
git fetch origin
git checkout Plane-4.5/navlink
git pull origin Plane-4.5/navlink
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
git push origin Plane-4.5
```

## Step 3: Update c_library_v2

### 3.1 Copy navlink.xml

```bash
cp mavlink/message_definitions/v1.0/navlink.xml \
   mavlink-router/modules/mavlink_c_library_v2/message_definitions/navlink.xml
```

### 3.2 Regenerate C Headers

```bash
cd mavlink-router/modules/mavlink_c_library_v2

# Regenerate ALL headers from ardupilotmega.xml
~/.local/bin/mavgen.py --lang=C --wire-protocol=2.0 \
    -o . \
    message_definitions/ardupilotmega.xml
```

**CRITICAL:** You must regenerate from `ardupilotmega.xml` (which includes navlink.xml). This updates the `MAVLINK_MESSAGE_CRCS` table in `ardupilotmega/ardupilotmega.h`. If you only update `navlink/*.h` files, the CRC lookup table will be stale and mavlink-router will drop messages due to CRC mismatch.

### 3.3 Verify CRCs Match

```bash
cd mavlink
python3 check_navlink_crcs.py
```

Expected output: `PASSED: All CRCs match!`

### 3.4 Commit and Push

```bash
cd mavlink-router/modules/mavlink_c_library_v2
git add -A
git commit -m "Regenerate C headers with YOUR_MESSAGE_NAME"
git push origin Plane-4.5/navlink
```

## Step 4: Update mavlink-router

### 4.1 Update c_library_v2 Submodule

```bash
cd mavlink-router/modules/mavlink_c_library_v2
git fetch origin
git checkout Plane-4.5
git pull origin Plane-4.5
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
git push origin Plane-4.5/navlink
```

## Step 5: Test the New Message

### 5.1 Start SITL Swarm

For WSL/local testing:
```bash
~/ardupilot/Tools/autotest/run_swarm.sh wsl -n 2
```

For Windows GCS testing:
```bash
~/ardupilot/Tools/autotest/run_swarm.sh sim -n 2 -d 50
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
| `wsl` | WSL local testing | `127.0.0.1:14500,14550,...` |
| `jsbsim` | JSBSim with Windows GCS | `$WIN_IP:14500,14550,...` |
| `jsbsim_only` | JSBSim local only | `0.0.0.0:15000` |

### Common Flags
- `-n N` : Number of SITL instances (default 2)
- `-d M` : Spacing between vehicles in meters (default 2)

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

If navlink messages are not being routed (standard MAVLink messages work but custom ones don't), the most likely cause is a **CRC mismatch** between pymavlink and mavlink-router's C headers.

**Diagnose with CRC check script:**

```bash
cd mavlink
python3 check_navlink_crcs.py -v
```

If you see output like:
```
pymavlink vs router: 1 error(s)
  - CHECK_IN (ID 25002): CRC mismatch: pymavlink=29 vs router=131
```

This means mavlink-router has stale headers. The `MAVLINK_MESSAGE_CRCS` table in `ardupilotmega.h` was not regenerated after navlink.xml was updated.

**Fix:**

```bash
# 1. Copy updated navlink.xml
cp mavlink/message_definitions/v1.0/navlink.xml \
   mavlink-router/modules/mavlink_c_library_v2/message_definitions/

# 2. Regenerate ALL C headers (not just navlink/)
cd mavlink-router/modules/mavlink_c_library_v2
~/.local/bin/mavgen.py --lang=C --wire-protocol=2.0 \
    -o . message_definitions/ardupilotmega.xml

# 3. Rebuild mavlink-router
cd mavlink-router
ninja -C build

# 4. Verify fix
cd mavlink
python3 check_navlink_crcs.py
```

### SITL Bind Errors

```bash
# Kill existing processes
pkill arduplane
pkill mavlink-routerd

# Restart swarm
~/ardupilot/Tools/autotest/run_swarm.sh wsl -n 2
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

| Repository | File | Purpose |
|------------|------|---------|
| `mavlink` | `message_definitions/v1.0/navlink.xml` | Message definitions (source of truth) |
| `mavlink` | `check_navlink_crcs.py` | CRC consistency check script |
| `mavlink` | `test_navlink_msg.py` | Message routing test script |
| `c_library_v2` | `message_definitions/navlink.xml` | Copy for C header generation |
| `c_library_v2` | `ardupilotmega/ardupilotmega.h` | Contains `MAVLINK_MESSAGE_CRCS` table |
