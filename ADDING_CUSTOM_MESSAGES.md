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

### 4.2 Rebuild and install mavlink-router

```bash
cd mavlink-router
meson setup build --wipe
ninja -C build
sudo ninja -C build install
```

**NOTE:** Always use `meson setup build --wipe` when message definitions change. A plain `ninja -C build` may only do an incremental rebuild that misses header changes.

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
ROUTER_BIN=~/mavlink-router/build/src/mavlink-routerd ~/ardupilot/Tools/autotest/run_swarm.sh wsl -n 2
```

For Windows GCS testing:
```bash
ROUTER_BIN=~/mavlink-router/build/src/mavlink-routerd ~/ardupilot/Tools/autotest/run_swarm.sh sim -n 2 -d 50
```

### 5.2 Run Test Script

```bash
cd mavlink

# List available messages
python3 test_navlink_msg.py --list

# Test your new message
python3 test_navlink_msg.py YOUR_MESSAGE_NAME field1=value1 field2=value2

# Example: Test CHECK_IN (broadcast, no target_system)
python3 test_navlink_msg.py CHECK_IN boot_id=123 msg_seq=1 time_ms=1000 ttl_ms=5000

# Example: Test CHECK_OUT
python3 test_navlink_msg.py CHECK_OUT boot_id=123 msg_seq=1 time_ms=1000 ttl_ms=5000 lat=40.31 lng=44.45 alt=1500

# Example: Test message with array fields (comma-separated values)
python3 test_navlink_msg.py AVAILABLE_TASK_REQUEST boot_id=123 msg_seq=1 time_ms=1000 ttl_ms=5000 \
    count=2 task_id=1,2 task_type=1,2 class_id=0,3 lat=40.31,40.32 lng=44.45,44.46 alt=1500,1600

# Example: Test TASK_CONFIRM_REQUEST (broadcast, has class_id)
python3 test_navlink_msg.py TASK_CONFIRM_REQUEST boot_id=123 msg_seq=1 time_ms=1000 ttl_ms=5000 \
    task_id=42 task_type=2 class_id=3 lat=40.31 lng=44.45 alt=1500
```

### 5.3 Targeted vs Broadcast Messages

Messages with a `target_system` field (marked with `MAV_MSG_ENTRY_FLAG_HAVE_TARGET_SYSTEM` in the CRC table) are delivered only to the matching sysid by the router. The test script listens on sysids 251/252, so **targeted messages with `target_system=1` will not be received by the test listener** — this is correct router behavior, not a failure.

Broadcast messages (no `target_system` flag) are forwarded to all endpoints and will show `TEST PASSED`.

| Message | Has target_system | Test behavior |
|---------|-------------------|---------------|
| CHECK_IN, CHECK_OUT, SWARM_HEARTBEAT | No | Broadcast, test passes |
| AVAILABLE_TASK_REQUEST | No | Broadcast, test passes |
| TASK_CONFIRM_REQUEST | No | Broadcast, test passes |
| AVAILABLE_TASK_RESPONSE | Yes | Targeted, test won't receive unless target_system matches |
| TASK_ASSIGN_REQUEST | Yes | Targeted, test won't receive unless target_system matches |
| TASK_ASSIGN_RESPONSE | Yes | Targeted, test won't receive unless target_system matches |
| TASK_CONFIRM_RESPONSE | Yes | Targeted, test won't receive unless target_system matches |

### 5.4 Expected Output

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

If navlink messages are not being routed (standard MAVLink messages work but custom ones don't), the most likely cause is a **CRC mismatch** between pymavlink and mavlink-router.

There are two common causes:

**Diagnose with CRC check script:**

```bash
cd mavlink
python3 check_navlink_crcs.py -v
```

If you see CRC mismatches, regenerate and rebuild:

```bash
# 1. Copy updated navlink.xml
cp mavlink/message_definitions/v1.0/navlink.xml \
   mavlink-router/modules/mavlink_c_library_v2/message_definitions/

# 2. Regenerate ALL C headers (not just navlink/)
cd mavlink-router/modules/mavlink_c_library_v2
~/.local/bin/mavgen.py --lang=C --wire-protocol=2.0 \
    -o . message_definitions/ardupilotmega.xml

# 3. Full rebuild and install mavlink-router
cd mavlink-router
meson setup build --wipe
ninja -C build
sudo ninja -C build install

# 4. Verify fix
cd mavlink
python3 check_navlink_crcs.py
```

**Symptom: CRCs pass but messages still not routed.** This means `mavlink-routerd` was not reinstalled after rebuild. Unmodified messages (e.g., CHECK_IN) route fine, but modified/new messages are silently dropped because the installed binary has stale CRCs. Re-run `sudo ninja -C build install` and restart the swarm.

**Check for duplicate mavlink-routerd binaries.** There should be only one `mavlink-routerd` on the system. Multiple copies (e.g., one in `/usr/bin/` and another in `/usr/local/bin/`) can cause confusion — the wrong one may be picked up from `$PATH`.

```bash
# Find all copies
which -a mavlink-routerd

# Should return only one path. If you see two (e.g., /usr/bin/ and /bin/),
# check if /bin is a symlink to /usr/bin — that's normal:
ls -la /bin
# lrwxrwxrwx 1 root root 7 ... /bin -> usr/bin
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
