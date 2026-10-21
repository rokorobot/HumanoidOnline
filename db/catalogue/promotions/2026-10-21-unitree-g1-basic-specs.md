# Catalogue promotion: 2026-10-21-unitree-g1-basic-specs

**Robot:** unitree-g1  
**Classification:** ROUTINE  
**Digest:** `b45cafcfbccb19c707f13c7182e3c4519e29ce8cb5d695f66c4ba6804b3a57e5`  
**Base commit:** `efd81436af751a6d1a59193bc33956a66c06b557`

## New manufacturer facts

- **joint_breakdown** (G1): 6 per leg, 5 per arm, 1 waist — 23 body joints
  - will show as: Robot detail spec table: 'Joint breakdown: 6 per leg, 5 per arm, 1 waist — 23 body joints', with source
- **swappable_battery** (G1): True
  - will show as: Robot detail spec table: 'Swappable battery: Yes', with source
- **connectivity** (G1): Wi-Fi 6, Bluetooth 5.2
  - will show as: Robot detail spec table: 'Connectivity: Wi-Fi 6, Bluetooth 5.2', with source
- **audio** (G1): 4-microphone array + 5 W speaker
  - will show as: Robot detail spec table: 'Audio: 4-microphone array + 5 W speaker', with source
- **ota_updates** (G1): True
  - will show as: Robot detail spec table: 'OTA updates: Yes', with source

## Evidence

- joint_breakdown: https://www.unitree.com/g1 (observed 2026-10-18; claim `ef475514-f437-4a3b-baea-be7e8ed3b996`; page hash `e1a93cd0bd13`)
  - interpretation: Combined from three rows of the page's G1 column: Single Leg Degrees of Freedom '6' (claim ef475514), Single Arm Degrees of Freedom '5' (claim f7d5f1d2), Waist Degrees of Freedom '1' (claim ff4692a0); sums to the catalogue's 23 DoF. Single Hand Degrees of Freedom is '/' and is not included.
- swappable_battery: https://www.unitree.com/g1 (observed 2026-10-18; claim `e33ad443-a121-4081-bbbc-f0e9545e8602`; page hash `e1a93cd0bd13`)
  - interpretation: Row 'Smart Battery (Quick Release)' states '9000mAh' for the G1 column: the battery is quick-release. Only the quick-release fact is recorded; the 9000 mAh capacity is not added because battery_pack already holds a value (a change, not an addition).
- connectivity: https://www.unitree.com/g1 (observed 2026-10-18; claim `e08e492c-6f8c-46d7-aa0a-01066f206d43`; page hash `e1a93cd0bd13`)
  - interpretation: The page's row label is 'WiFi 6 、Bluetooth 5.2' and the G1 cell is 'YES'; the value is the confirmed row label.
- audio: https://www.unitree.com/g1 (observed 2026-10-18; claim `e3ce8fc0-80f7-4911-8d3d-17ee6928f04b`; page hash `e1a93cd0bd13`)
  - interpretation: Two rows of the G1 column, each 'YES': '4 Microphone Array' (claim e3ce8fc0) and '5W Speaker' (claim cf5c96ad); the value is the confirmed row labels.
- ota_updates: https://www.unitree.com/g1 (observed 2026-10-18; claim `6c1d6536-5dc7-47ce-a72f-d894560c9d83`; page hash `e1a93cd0bd13`)
  - interpretation: Row 'Upgraded Intelligent OTA' is 'YES' for the G1 column.

## Impact

5 specification additions; no changes to price, availability, publication, images or unrelated robots.


## Decision

APPROVE (merge) / REJECT / DEFER (close PR with label)
