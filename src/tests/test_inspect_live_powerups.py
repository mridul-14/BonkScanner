"""Tests for live power-up and Za Warudo tracking in inspect_live.py."""

from __future__ import annotations

import math
import struct
import sys
from pathlib import Path
import unittest

# Ensure tools/inspect_live is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INSPECT_LIVE_DIR = PROJECT_ROOT / "tools" / "inspect_live"
if str(INSPECT_LIVE_DIR) not in sys.path:
    sys.path.insert(0, str(INSPECT_LIVE_DIR))
DEPS_DIR = INSPECT_LIVE_DIR / "dependencies"
if str(DEPS_DIR) not in sys.path:
    sys.path.insert(0, str(DEPS_DIR))

import inspect_live as il


class MockProcessMemory:
    """Mock memory backend for testing read_active_powerups."""

    def __init__(self, memory_map: dict[int, bytes | int | float]) -> None:
        self.raw_data: dict[int, bytes] = {}
        for addr, val in memory_map.items():
            if isinstance(val, bytes):
                self.raw_data[addr] = val
            elif isinstance(val, int):
                # Default to 8-byte pointer unless negative
                if val < 0:
                    self.raw_data[addr] = struct.pack("<i", val)
                else:
                    self.raw_data[addr] = struct.pack("<Q", val)
            elif isinstance(val, float):
                self.raw_data[addr] = struct.pack("<f", val)

    def read_ptr(self, address: int) -> int:
        data = self.raw_data.get(address)
        if data is None:
            return 0
        return struct.unpack("<Q", data[:8])[0]

    def read_i32(self, address: int) -> int:
        data = self.raw_data.get(address)
        if data is None:
            return 0
        return struct.unpack("<i", data[:4])[0]

    def read_float(self, address: int) -> float:
        data = self.raw_data.get(address)
        if data is None:
            return 0.0
        return struct.unpack("<f", data[:4])[0]


class TestInspectLivePowerups(unittest.TestCase):
    def test_format_clock_time_standard(self) -> None:
        self.assertEqual(il.format_clock_time(0.0), "00:00")
        self.assertEqual(il.format_clock_time(45.0), "00:45")
        self.assertEqual(il.format_clock_time(60.0), "01:00")
        self.assertEqual(il.format_clock_time(480.0), "08:00")
        self.assertEqual(il.format_clock_time(600.0), "10:00")

    def test_format_clock_time_overtime(self) -> None:
        self.assertEqual(il.format_clock_time(0.0, is_overtime=True), "+00:00")
        self.assertEqual(il.format_clock_time(75.0, is_overtime=True), "+01:15")
        self.assertEqual(il.format_clock_time(125.4, is_overtime=True), "+02:05")

    def test_format_powerups_display_empty(self) -> None:
        self.assertEqual(il.format_powerups_display({"effects": []}), "")
        self.assertEqual(il.format_powerups_display({}), "")

    def test_format_powerups_display_single_and_multiple(self) -> None:
        data = {
            "stage_clock": "05:20",
            "effects": [
                {
                    "effect_id": 4,
                    "name": "Clock / Za Warudo",
                    "remaining_seconds": 8.4,
                    "end_clock": "05:12",
                },
                {
                    "effect_id": 1,
                    "name": "Rage",
                    "remaining_seconds": 14.1,
                    "end_clock": "05:06",
                },
            ],
        }
        # Plain text
        plain = il.format_powerups_display(data, ansi=False)
        self.assertIn("Clock / Za Warudo: 8.4s (Ends at 05:12)", plain)
        self.assertIn("Rage: 14.1s (Ends at 05:06)", plain)
        self.assertIn("[Stage Clock: 05:20]", plain)

        # ANSI text
        ansi = il.format_powerups_display(data, ansi=True)
        self.assertIn("Clock / Za Warudo", ansi)
        self.assertIn("8.4s", ansi)
        self.assertIn("Ends at 05:12", ansi)

    def test_read_active_powerups_countdown(self) -> None:
        module_base = 0x180000000

        # Pointers
        my_time_type_info = module_base + il.MY_TIME_TYPE_INFO_OFFSET
        my_time_static = 0x200000000
        map_ctrl_type_info = module_base + il.MAP_CONTROLLER_TYPE_INFO_OFFSET
        map_ctrl_static = 0x210000000
        player_stats_type_info = module_base + il.PLAYER_STATS_TYPE_INFO_OFFSET
        player_stats_static = 0x220000000
        root = 0x230000000
        owner_stats = 0x240000000
        player_inv = 0x250000000
        status_effects = 0x260000000
        status_dict = 0x270000000
        status_entries = 0x280000000

        effect_clock_ptr = 0x290000000
        effect_rage_ptr = 0x2A0000000

        # Status effect entry 0 (Clock / Za Warudo)
        entry0 = status_entries + il.DICT_ENTRY_START_OFFSET
        # Status effect entry 1 (Rage)
        entry1 = entry0 + il.DICT_ENTRY_SIZE
        # Status effect entry 2 (Dead / Empty slot)
        entry2 = entry1 + il.DICT_ENTRY_SIZE

        mem_map: dict[int, bytes | int | float] = {
            # MyTime: session time = 1000.0, stage timer = 120.0
            my_time_type_info: my_time_static,
            my_time_static + il.CLASS_STATIC_FIELDS_OFFSET: my_time_static,
            my_time_static + il.MY_TIME_TIME_OFFSET: 1000.0,
            my_time_static + il.STAGE_TIMER_OFFSET: 120.0,

            # MapController: stage index = 0 (Forest, 600s total)
            map_ctrl_type_info: map_ctrl_static,
            map_ctrl_static + il.CLASS_STATIC_FIELDS_OFFSET: map_ctrl_static,
            map_ctrl_static + il.MAP_CONTROLLER_STAGE_INDEX_OFFSET: struct.pack("<i", 0),
            map_ctrl_static + il.MAP_CONTROLLER_CURRENT_STAGE_OFFSET: 0,

            # PlayerStats hierarchy
            player_stats_type_info: player_stats_static,
            player_stats_static + il.CLASS_STATIC_FIELDS_OFFSET: player_stats_static,
            player_stats_static + il.PLAYER_STATS_ROOT_OFFSET: root,
            root + il.OWNER_STATS_OFFSET: owner_stats,
            owner_stats + il.PLAYER_INVENTORY_OFFSET: player_inv,
            player_inv + il.PLAYER_STATUS_EFFECTS_OFFSET: status_effects,
            status_effects + il.PLAYER_STATUS_EFFECTS_DICT_OFFSET: status_dict,

            # Dictionary headers
            status_dict + il.DICT_ENTRIES_OFFSET: status_entries,
            status_dict + il.DICT_COUNT_OFFSET: struct.pack("<i", 2),
            status_entries + il.ARRAY_LENGTH_OFFSET: struct.pack("<i", 3),

            # Entry 0: Clock / Za Warudo (effect 4)
            entry0 + il.DICT_ENTRY_HASH_CODE_OFFSET: struct.pack("<i", 4),
            entry0 + il.DICT_ENTRY_KEY_OFFSET: struct.pack("<i", 4),
            entry0 + il.DICT_ENTRY_VALUE_OFFSET: effect_clock_ptr,
            effect_clock_ptr + il.STATUS_EFFECT_EXPIRATION_OFFSET: 1015.0,  # 15s remaining
            effect_clock_ptr + il.STATUS_EFFECT_ADDED_OFFSET: 1000.0,

            # Entry 1: Rage (effect 1)
            entry1 + il.DICT_ENTRY_HASH_CODE_OFFSET: struct.pack("<i", 1),
            entry1 + il.DICT_ENTRY_KEY_OFFSET: struct.pack("<i", 1),
            entry1 + il.DICT_ENTRY_VALUE_OFFSET: effect_rage_ptr,
            effect_rage_ptr + il.STATUS_EFFECT_EXPIRATION_OFFSET: 1025.0,  # 25s remaining
            effect_rage_ptr + il.STATUS_EFFECT_ADDED_OFFSET: 1000.0,

            # Entry 2: Free / Deleted slot (hash_code = -1)
            entry2 + il.DICT_ENTRY_HASH_CODE_OFFSET: struct.pack("<i", -1),
        }

        mock_mem = MockProcessMemory(mem_map)
        res = il.read_active_powerups(mock_mem, module_base)

        self.assertTrue(res["available"])
        self.assertFalse(res["is_overtime"])
        # Stage clock: 600 - 120 = 480s = 08:00
        self.assertEqual(res["stage_clock"], "08:00")
        self.assertEqual(len(res["effects"]), 2)

        # Sorted ascending by remaining time: Clock first (15s), then Rage (25s)
        clock_eff = res["effects"][0]
        self.assertEqual(clock_eff["effect_id"], 4)
        self.assertEqual(clock_eff["name"], "Clock / Za Warudo")
        self.assertAlmostEqual(clock_eff["remaining_seconds"], 15.0, places=1)
        # End clock: 480 - 15 = 465s = 07:45
        self.assertEqual(clock_eff["end_clock"], "07:45")

        rage_eff = res["effects"][1]
        self.assertEqual(rage_eff["effect_id"], 1)
        self.assertEqual(rage_eff["name"], "Rage")
        self.assertAlmostEqual(rage_eff["remaining_seconds"], 25.0, places=1)
        # End clock: 480 - 25 = 455s = 07:35
        self.assertEqual(rage_eff["end_clock"], "07:35")

    def test_read_active_powerups_overtime(self) -> None:
        module_base = 0x180000000

        my_time_type_info = module_base + il.MY_TIME_TYPE_INFO_OFFSET
        my_time_static = 0x200000000
        map_ctrl_type_info = module_base + il.MAP_CONTROLLER_TYPE_INFO_OFFSET
        map_ctrl_static = 0x210000000
        player_stats_type_info = module_base + il.PLAYER_STATS_TYPE_INFO_OFFSET
        player_stats_static = 0x220000000
        root = 0x230000000
        owner_stats = 0x240000000
        player_inv = 0x250000000
        status_effects = 0x260000000
        status_dict = 0x270000000
        status_entries = 0x280000000
        effect_ptr = 0x290000000
        entry0 = status_entries + il.DICT_ENTRY_START_OFFSET

        # Overtime: stage_timer = 650.0 on 600.0s stage (+00:50)
        mem_map: dict[int, bytes | int | float] = {
            my_time_type_info: my_time_static,
            my_time_static + il.CLASS_STATIC_FIELDS_OFFSET: my_time_static,
            my_time_static + il.MY_TIME_TIME_OFFSET: 1000.0,
            my_time_static + il.STAGE_TIMER_OFFSET: 650.0,

            map_ctrl_type_info: map_ctrl_static,
            map_ctrl_static + il.CLASS_STATIC_FIELDS_OFFSET: map_ctrl_static,
            map_ctrl_static + il.MAP_CONTROLLER_STAGE_INDEX_OFFSET: struct.pack("<i", 0),
            map_ctrl_static + il.MAP_CONTROLLER_CURRENT_STAGE_OFFSET: 0,

            player_stats_type_info: player_stats_static,
            player_stats_static + il.CLASS_STATIC_FIELDS_OFFSET: player_stats_static,
            player_stats_static + il.PLAYER_STATS_ROOT_OFFSET: root,
            root + il.OWNER_STATS_OFFSET: owner_stats,
            owner_stats + il.PLAYER_INVENTORY_OFFSET: player_inv,
            player_inv + il.PLAYER_STATUS_EFFECTS_OFFSET: status_effects,
            status_effects + il.PLAYER_STATUS_EFFECTS_DICT_OFFSET: status_dict,

            status_dict + il.DICT_ENTRIES_OFFSET: status_entries,
            status_dict + il.DICT_COUNT_OFFSET: struct.pack("<i", 1),
            status_entries + il.ARRAY_LENGTH_OFFSET: struct.pack("<i", 1),

            entry0 + il.DICT_ENTRY_HASH_CODE_OFFSET: struct.pack("<i", 4),
            entry0 + il.DICT_ENTRY_KEY_OFFSET: struct.pack("<i", 4),
            entry0 + il.DICT_ENTRY_VALUE_OFFSET: effect_ptr,
            effect_ptr + il.STATUS_EFFECT_EXPIRATION_OFFSET: 1015.0,  # 15s remaining
            effect_ptr + il.STATUS_EFFECT_ADDED_OFFSET: 1000.0,
        }

        mock_mem = MockProcessMemory(mem_map)
        res = il.read_active_powerups(mock_mem, module_base)

        self.assertTrue(res["available"])
        self.assertTrue(res["is_overtime"])
        # Stage clock: overtime 50s -> +00:50
        self.assertEqual(res["stage_clock"], "+00:50")
        self.assertEqual(len(res["effects"]), 1)
        # End clock: 50 + 15 = 65s -> +01:05
        self.assertEqual(res["effects"][0]["end_clock"], "+01:05")

    def test_read_active_powerups_expired_and_uninitialized(self) -> None:
        module_base = 0x180000000

        # Uninitialized memory -> available=False, no effects
        mock_mem_empty = MockProcessMemory({})
        res_empty = il.read_active_powerups(mock_mem_empty, module_base)
        self.assertFalse(res_empty["available"])
        self.assertEqual(res_empty["effects"], [])

        # Memory with expired effect: expiration_time <= my_time_seconds
        my_time_type_info = module_base + il.MY_TIME_TYPE_INFO_OFFSET
        my_time_static = 0x200000000
        map_ctrl_type_info = module_base + il.MAP_CONTROLLER_TYPE_INFO_OFFSET
        map_ctrl_static = 0x210000000
        player_stats_type_info = module_base + il.PLAYER_STATS_TYPE_INFO_OFFSET
        player_stats_static = 0x220000000
        root = 0x230000000
        owner_stats = 0x240000000
        player_inv = 0x250000000
        status_effects = 0x260000000
        status_dict = 0x270000000
        status_entries = 0x280000000
        effect_ptr = 0x290000000
        entry0 = status_entries + il.DICT_ENTRY_START_OFFSET

        mem_map: dict[int, bytes | int | float] = {
            my_time_type_info: my_time_static,
            my_time_static + il.CLASS_STATIC_FIELDS_OFFSET: my_time_static,
            my_time_static + il.MY_TIME_TIME_OFFSET: 1000.0,
            my_time_static + il.STAGE_TIMER_OFFSET: 100.0,

            map_ctrl_type_info: map_ctrl_static,
            map_ctrl_static + il.CLASS_STATIC_FIELDS_OFFSET: map_ctrl_static,

            player_stats_type_info: player_stats_static,
            player_stats_static + il.CLASS_STATIC_FIELDS_OFFSET: player_stats_static,
            player_stats_static + il.PLAYER_STATS_ROOT_OFFSET: root,
            root + il.OWNER_STATS_OFFSET: owner_stats,
            owner_stats + il.PLAYER_INVENTORY_OFFSET: player_inv,
            player_inv + il.PLAYER_STATUS_EFFECTS_OFFSET: status_effects,
            status_effects + il.PLAYER_STATUS_EFFECTS_DICT_OFFSET: status_dict,

            status_dict + il.DICT_ENTRIES_OFFSET: status_entries,
            status_dict + il.DICT_COUNT_OFFSET: struct.pack("<i", 1),
            status_entries + il.ARRAY_LENGTH_OFFSET: struct.pack("<i", 1),

            entry0 + il.DICT_ENTRY_HASH_CODE_OFFSET: struct.pack("<i", 4),
            entry0 + il.DICT_ENTRY_KEY_OFFSET: struct.pack("<i", 4),
            entry0 + il.DICT_ENTRY_VALUE_OFFSET: effect_ptr,
            # Expired: expiration_time == my_time (1000.0 <= 1000.0)
            effect_ptr + il.STATUS_EFFECT_EXPIRATION_OFFSET: 1000.0,
            effect_ptr + il.STATUS_EFFECT_ADDED_OFFSET: 985.0,
        }

        mock_mem = MockProcessMemory(mem_map)
        res = il.read_active_powerups(mock_mem, module_base)
        self.assertTrue(res["available"])
        self.assertEqual(res["effects"], [])

    def test_read_active_powerups_ignores_invulnerability(self) -> None:
        """Invulnerability (effect_id 5 from XP/level interaction or i-frames) must be ignored."""
        module_base = 0x180000000

        my_time_type_info = module_base + il.MY_TIME_TYPE_INFO_OFFSET
        my_time_static = 0x200000000
        map_ctrl_type_info = module_base + il.MAP_CONTROLLER_TYPE_INFO_OFFSET
        map_ctrl_static = 0x210000000
        player_stats_type_info = module_base + il.PLAYER_STATS_TYPE_INFO_OFFSET
        player_stats_static = 0x220000000
        root = 0x230000000
        owner_stats = 0x240000000
        player_inv = 0x250000000
        status_effects = 0x260000000
        status_dict = 0x270000000
        status_entries = 0x280000000
        effect_ptr = 0x290000000
        entry0 = status_entries + il.DICT_ENTRY_START_OFFSET

        mem_map: dict[int, bytes | int | float] = {
            my_time_type_info: my_time_static,
            my_time_static + il.CLASS_STATIC_FIELDS_OFFSET: my_time_static,
            my_time_static + il.MY_TIME_TIME_OFFSET: 1000.0,
            my_time_static + il.STAGE_TIMER_OFFSET: 100.0,

            map_ctrl_type_info: map_ctrl_static,
            map_ctrl_static + il.CLASS_STATIC_FIELDS_OFFSET: map_ctrl_static,

            player_stats_type_info: player_stats_static,
            player_stats_static + il.CLASS_STATIC_FIELDS_OFFSET: player_stats_static,
            player_stats_static + il.PLAYER_STATS_ROOT_OFFSET: root,
            root + il.OWNER_STATS_OFFSET: owner_stats,
            owner_stats + il.PLAYER_INVENTORY_OFFSET: player_inv,
            player_inv + il.PLAYER_STATUS_EFFECTS_OFFSET: status_effects,
            status_effects + il.PLAYER_STATUS_EFFECTS_DICT_OFFSET: status_dict,

            status_dict + il.DICT_ENTRIES_OFFSET: status_entries,
            status_dict + il.DICT_COUNT_OFFSET: struct.pack("<i", 1),
            status_entries + il.ARRAY_LENGTH_OFFSET: struct.pack("<i", 1),

            # Effect ID 5: Invulnerability
            entry0 + il.DICT_ENTRY_HASH_CODE_OFFSET: struct.pack("<i", 5),
            entry0 + il.DICT_ENTRY_KEY_OFFSET: struct.pack("<i", 5),
            entry0 + il.DICT_ENTRY_VALUE_OFFSET: effect_ptr,
            effect_ptr + il.STATUS_EFFECT_EXPIRATION_OFFSET: 1010.0,
            effect_ptr + il.STATUS_EFFECT_ADDED_OFFSET: 1000.0,
        }

        mock_mem = MockProcessMemory(mem_map)
        res = il.read_active_powerups(mock_mem, module_base)
        self.assertTrue(res["available"])
        # Invulnerability must NOT be in active effects
        self.assertEqual(res["effects"], [])
        self.assertNotIn(5, il.POWERUP_EFFECT_NAMES)

    def test_read_active_powerups_za_warudo_held(self) -> None:
        module_base = 0x180000000

        my_time_type_info = module_base + il.MY_TIME_TYPE_INFO_OFFSET
        my_time_static = 0x200000000
        player_stats_type_info = module_base + il.PLAYER_STATS_TYPE_INFO_OFFSET
        player_stats_static = 0x220000000
        root = 0x230000000
        owner_stats = 0x240000000
        player_inv = 0x250000000
        item_inv = 0x260000000
        items_dict = 0x270000000
        i_entries = 0x280000000
        item_obj = 0x290000000
        i_entry0 = i_entries + il.DICT_ENTRY_START_OFFSET

        mem_map: dict[int, bytes | int | float] = {
            my_time_type_info: my_time_static,
            my_time_static + il.CLASS_STATIC_FIELDS_OFFSET: my_time_static,
            my_time_static + il.MY_TIME_TIME_OFFSET: 1000.0,
            my_time_static + il.STAGE_TIMER_OFFSET: 100.0,

            player_stats_type_info: player_stats_static,
            player_stats_static + il.CLASS_STATIC_FIELDS_OFFSET: player_stats_static,
            player_stats_static + il.PLAYER_STATS_ROOT_OFFSET: root,
            root + il.OWNER_STATS_OFFSET: owner_stats,
            owner_stats + il.PLAYER_INVENTORY_OFFSET: player_inv,

            # Item inventory with Za Warudo (ID 25)
            player_inv + 0x20: item_inv,
            item_inv + 0x10: items_dict,
            items_dict + il.DICT_ENTRIES_OFFSET: i_entries,
            i_entries + il.ARRAY_LENGTH_OFFSET: struct.pack("<i", 1),
            i_entry0 + il.DICT_ENTRY_HASH_CODE_OFFSET: struct.pack("<i", 25),
            i_entry0 + il.DICT_ENTRY_KEY_OFFSET: struct.pack("<i", 25),
            i_entry0 + il.DICT_ENTRY_VALUE_OFFSET: item_obj,
            item_obj + 0x18: struct.pack("<i", 2),  # x2 held
        }

        mock_mem = MockProcessMemory(mem_map)
        res = il.read_active_powerups(mock_mem, module_base)
        self.assertTrue(res["available"])
        self.assertEqual(res["za_warudo_held"], 2)

    def test_format_single_powerup_line_active(self) -> None:
        """Active line shows name, end clock, and in-game clock in single line."""
        line = il.format_single_powerup_line(
            name="Clock / Za Warudo",
            end_clock="02:45",
            stage_clock="02:15",
            is_ended=False,
            use_rich=False,
        )
        self.assertEqual(line, "⚡ [POWER-UP] Clock / Za Warudo: Active until 02:45 (Clock: 02:15)")

        rich_line = il.format_single_powerup_line(
            name="Clock / Za Warudo",
            end_clock="02:45",
            stage_clock="02:15",
            is_ended=False,
            use_rich=True,
        )
        self.assertIn("Active until", rich_line)
        self.assertIn("02:45", rich_line)
        self.assertIn("02:15", rich_line)

    def test_format_single_powerup_line_ended(self) -> None:
        """Ended line is struck-through and dimmed."""
        line_plain = il.format_single_powerup_line(
            name="Clock / Za Warudo",
            end_clock="02:45",
            stage_clock="02:15",
            is_ended=True,
            use_rich=False,
        )
        self.assertTrue(line_plain.startswith("\033[2;9m"))
        self.assertTrue(line_plain.endswith("\033[0m"))

        line_rich = il.format_single_powerup_line(
            name="Clock / Za Warudo",
            end_clock="02:45",
            stage_clock="02:15",
            is_ended=True,
            use_rich=True,
        )
        self.assertTrue(line_rich.startswith("[dim strike]"))
        self.assertTrue(line_rich.endswith("[/]"))

    def test_powerup_display_tracker_lifecycle(self) -> None:
        """Tracker records single line on activation and strikes/dims on expiry."""
        printed_lines: list[str] = []

        class MockConsole:
            def print(self, msg: str) -> None:
                printed_lines.append(msg)

        tracker = il.PowerupDisplayTracker(console_obj=MockConsole())

        # 1. Activate Za Warudo
        pu_data_1 = {
            "stage_clock": "02:15",
            "effects": [
                {
                    "effect_id": 4,
                    "name": "Clock / Za Warudo",
                    "end_clock": "02:45",
                    "remaining_seconds": 30.0,
                }
            ],
        }
        tracker.update(pu_data_1)
        self.assertEqual(len(tracker.displayed_lines), 1)
        self.assertEqual(tracker.displayed_lines[0]["status"], "active")
        self.assertEqual(len(printed_lines), 1)
        self.assertIn("Active until", printed_lines[0])

        # 2. Add second power-up (Rage) while Za Warudo still active
        pu_data_2 = {
            "stage_clock": "02:20",
            "effects": [
                {
                    "effect_id": 4,
                    "name": "Clock / Za Warudo",
                    "end_clock": "02:45",
                    "remaining_seconds": 25.0,
                },
                {
                    "effect_id": 1,
                    "name": "Rage",
                    "end_clock": "02:35",
                    "remaining_seconds": 15.0,
                },
            ],
        }
        tracker.update(pu_data_2)
        self.assertEqual(len(tracker.displayed_lines), 2)
        self.assertEqual(tracker.displayed_lines[1]["status"], "active")
        self.assertEqual(len(printed_lines), 2)

        # 3. Rage expires first
        pu_data_3 = {
            "stage_clock": "02:35",
            "effects": [
                {
                    "effect_id": 4,
                    "name": "Clock / Za Warudo",
                    "end_clock": "02:45",
                    "remaining_seconds": 10.0,
                }
            ],
        }
        tracker.update(pu_data_3)
        self.assertEqual(tracker.displayed_lines[1]["status"], "ended")
        self.assertEqual(tracker.displayed_lines[0]["status"], "active")

        # 4. Za Warudo expires
        pu_data_4 = {
            "stage_clock": "02:45",
            "effects": [],
        }
        tracker.update(pu_data_4)
        self.assertEqual(tracker.displayed_lines[0]["status"], "ended")

    def test_same_type_multiple_pickups_print_new_line_and_expire_independently(self) -> None:
        """When player picks another power-up of the same type, a new line is printed and each line expires at its own end time."""
        printed_lines: list[str] = []

        class MockConsole:
            def print(self, msg: str) -> None:
                printed_lines.append(msg)

        tracker = il.PowerupDisplayTracker(console_obj=MockConsole())

        # 1. First pickup of Clock / Za Warudo (duration 30s, active until 02:30)
        pu_1 = {
            "my_time": 100.0,
            "stage_clock": "03:00",
            "effects": [
                {
                    "effect_id": 4,
                    "name": "Clock / Za Warudo",
                    "end_clock": "02:30",
                    "remaining_seconds": 30.0,
                    "expiration_time": 130.0,
                    "added_time": 100.0,
                }
            ],
        }
        tracker.update(pu_1)
        self.assertEqual(len(tracker.displayed_lines), 1)
        self.assertEqual(tracker.displayed_lines[0]["status"], "active")
        self.assertEqual(len(printed_lines), 1)
        self.assertIn("Active until", printed_lines[0])
        self.assertIn("02:30", printed_lines[0])
        self.assertIn("03:00", printed_lines[0])

        # 2. 15s later, player picks up ANOTHER Clock (duration extended to 160.0, ends at 02:00)
        pu_2 = {
            "my_time": 115.0,
            "stage_clock": "02:45",
            "effects": [
                {
                    "effect_id": 4,
                    "name": "Clock / Za Warudo",
                    "end_clock": "02:00",
                    "remaining_seconds": 45.0,
                    "expiration_time": 160.0,
                    "added_time": 115.0,
                }
            ],
        }
        tracker.update(pu_2)
        # Feed MUST update with a new line for the second pickup!
        self.assertEqual(len(tracker.displayed_lines), 2)
        # Both lines must remain active (previous line visible until it expires)
        self.assertEqual(tracker.displayed_lines[0]["status"], "active")
        self.assertEqual(tracker.displayed_lines[1]["status"], "active")
        self.assertEqual(len(printed_lines), 2)
        self.assertIn("Active until", printed_lines[1])
        self.assertIn("02:00", printed_lines[1])
        self.assertIn("02:45", printed_lines[1])

        # 3. Normal countdown tick at my_time = 120.0 (no new pickup, remaining decreases)
        pu_3 = {
            "my_time": 120.0,
            "stage_clock": "02:40",
            "effects": [
                {
                    "effect_id": 4,
                    "name": "Clock / Za Warudo",
                    "end_clock": "02:00",
                    "remaining_seconds": 40.0,
                    "expiration_time": 160.0,
                    "added_time": 115.0,
                }
            ],
        }
        tracker.update(pu_3)
        # No extra lines printed during normal ticking
        self.assertEqual(len(tracker.displayed_lines), 2)
        self.assertEqual(tracker.displayed_lines[0]["status"], "active")
        self.assertEqual(tracker.displayed_lines[1]["status"], "active")
        self.assertEqual(len(printed_lines), 2)

        # 4. Stage reaches my_time = 130.0 (First power-up's 02:30 mark expires!)
        pu_4 = {
            "my_time": 130.0,
            "stage_clock": "02:30",
            "effects": [
                {
                    "effect_id": 4,
                    "name": "Clock / Za Warudo",
                    "end_clock": "02:00",
                    "remaining_seconds": 30.0,
                    "expiration_time": 160.0,
                    "added_time": 115.0,
                }
            ],
        }
        tracker.update(pu_4)
        # First line MUST now be ended (struck through & dimmed), second line STILL active!
        self.assertEqual(tracker.displayed_lines[0]["status"], "ended")
        self.assertEqual(tracker.displayed_lines[1]["status"], "active")

        # 5. Stage reaches my_time = 160.0 (Second power-up's 02:00 mark expires!)
        pu_5 = {
            "my_time": 160.0,
            "stage_clock": "02:00",
            "effects": [],
        }
        tracker.update(pu_5)
        # Second line MUST now also be ended!
        self.assertEqual(tracker.displayed_lines[0]["status"], "ended")
        self.assertEqual(tracker.displayed_lines[1]["status"], "ended")

    def test_same_type_multiple_pickups_early_wipe_ends_all(self) -> None:
        """If an effect completely disappears before individual expiration times, all active lines are ended."""
        class MockConsole:
            def print(self, msg: str) -> None:
                pass

        tracker = il.PowerupDisplayTracker(console_obj=MockConsole())
        pu_1 = {
            "my_time": 100.0,
            "stage_clock": "03:00",
            "effects": [{"effect_id": 2, "name": "Speed", "end_clock": "02:30", "remaining_seconds": 30.0, "expiration_time": 130.0}],
        }
        tracker.update(pu_1)
        pu_2 = {
            "my_time": 110.0,
            "stage_clock": "02:50",
            "effects": [{"effect_id": 2, "name": "Speed", "end_clock": "02:00", "remaining_seconds": 50.0, "expiration_time": 160.0}],
        }
        tracker.update(pu_2)
        self.assertEqual(len(tracker.displayed_lines), 2)
        self.assertEqual(tracker.displayed_lines[0]["status"], "active")
        self.assertEqual(tracker.displayed_lines[1]["status"], "active")

        # Early wipe at my_time = 115.0 (player died or stage reset)
        pu_wipe = {"my_time": 115.0, "stage_clock": "02:45", "effects": []}
        tracker.update(pu_wipe)
        self.assertEqual(tracker.displayed_lines[0]["status"], "ended")
        self.assertEqual(tracker.displayed_lines[1]["status"], "ended")

    def test_console_cleared_reprints_only_active_lines(self) -> None:
        """When console is cleared, active lines are reprinted and ended lines are discarded."""
        reprinted: list[str] = []

        class MockConsole:
            def print(self, msg: str) -> None:
                reprinted.append(msg)

        tracker = il.PowerupDisplayTracker(console_obj=MockConsole())
        pu_1 = {
            "my_time": 100.0,
            "stage_clock": "03:00",
            "effects": [{"effect_id": 4, "name": "Clock / Za Warudo", "end_clock": "02:30", "remaining_seconds": 30.0, "expiration_time": 130.0}],
        }
        tracker.update(pu_1)
        pu_2 = {
            "my_time": 115.0,
            "stage_clock": "02:45",
            "effects": [{"effect_id": 4, "name": "Clock / Za Warudo", "end_clock": "02:00", "remaining_seconds": 45.0, "expiration_time": 160.0}],
        }
        tracker.update(pu_2)

        # Expire line 0
        pu_3 = {
            "my_time": 130.0,
            "stage_clock": "02:30",
            "effects": [{"effect_id": 4, "name": "Clock / Za Warudo", "end_clock": "02:00", "remaining_seconds": 30.0, "expiration_time": 160.0}],
        }
        tracker.update(pu_3)
        self.assertEqual(tracker.displayed_lines[0]["status"], "ended")
        self.assertEqual(tracker.displayed_lines[1]["status"], "active")

        # Console clear
        reprinted.clear()
        tracker.on_console_cleared()
        # Only the active second pickup should be retained and reprinted
        self.assertEqual(len(tracker.displayed_lines), 1)
        self.assertEqual(tracker.displayed_lines[0]["status"], "active")
        self.assertIn("Active until 02:00", tracker.displayed_lines[0]["line_plain"])
        self.assertEqual(len(reprinted), 1)

    def test_format_powerups_display_with_za_warudo_held(self) -> None:
        """format_powerups_display formats held Za Warudo even without active timed effects."""
        data = {"za_warudo_held": 1, "stage_clock": "08:15", "effects": []}
        plain = il.format_powerups_display(data, ansi=False)
        self.assertIn("Za Warudo (Held x1): Active Protection", plain)
        self.assertIn("[Stage Clock: 08:15]", plain)

        ansi = il.format_powerups_display(data, ansi=True)
        self.assertIn("Za Warudo (Held x1)", ansi)
        self.assertIn("Active Protection", ansi)

    def test_powerup_display_tracker_held_za_warudo_lifecycle(self) -> None:
        """Tracker displays held Za Warudo, updates on count changes, and strikes out when consumed."""
        printed_lines: list[str] = []

        class MockConsole:
            def print(self, msg: str) -> None:
                printed_lines.append(msg)

        tracker = il.PowerupDisplayTracker(console_obj=MockConsole())

        # 1. Player holds 1 Za Warudo item
        pu_1 = {"my_time": 50.0, "stage_clock": "08:00", "za_warudo_held": 1, "effects": []}
        tracker.update(pu_1)
        self.assertEqual(len(tracker.displayed_lines), 1)
        self.assertEqual(tracker.displayed_lines[0]["status"], "active")
        self.assertEqual(tracker.displayed_lines[0]["effect_id"], -25)
        self.assertIn("Za Warudo", printed_lines[0])
        self.assertIn("Active Protection", printed_lines[0])

        # 2. Player buys a second Za Warudo (count increases to 2)
        pu_2 = {"my_time": 70.0, "stage_clock": "07:40", "za_warudo_held": 2, "effects": []}
        tracker.update(pu_2)
        self.assertEqual(len(tracker.displayed_lines), 1)
        self.assertEqual(tracker.displayed_lines[0]["status"], "active")
        self.assertIn("Added +1, total x2", printed_lines[1])

        # 3. Console clear re-prints active held item
        printed_lines.clear()
        tracker.on_console_cleared()
        self.assertEqual(len(tracker.displayed_lines), 1)
        self.assertEqual(tracker.displayed_lines[0]["status"], "active")
        self.assertEqual(len(printed_lines), 1)

        # 4. Lethal damage taken: all Za Warudo items consumed / broken (count -> 0)
        pu_3 = {"my_time": 100.0, "stage_clock": "07:10", "za_warudo_held": 0, "effects": []}
        tracker.update(pu_3)
        self.assertEqual(tracker.displayed_lines[0]["status"], "ended")

    def test_render_active_powerups_block(self) -> None:
        """render_active_powerups_block prints tables with powerup names, remaining time, and end clocks."""
        pu_data = {
            "stage_clock": "06:30",
            "za_warudo_held": 1,
            "effects": [
                {
                    "name": "Shield",
                    "remaining_seconds": 10.0,
                    "end_clock": "06:20",
                }
            ],
        }
        import io
        from unittest.mock import patch

        # Plain text
        buf = io.StringIO()
        with patch.object(il, "console", None):
            with patch("sys.stdout", buf):
                il.render_active_powerups_block(pu_data, use_rich=False)
        output = buf.getvalue()
        self.assertIn("ACTIVE POWER-UPS & BUFFS", output)
        self.assertIn("Za Warudo (Held Item x1)", output)
        self.assertIn("Shield", output)
        self.assertIn("Ends at 06:20", output)


if __name__ == "__main__":
    unittest.main()
