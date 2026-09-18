"""Dedicated inspect tool for Shady Guy and Moai items with Auto-Reroll."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import glob
import json
import math
import os
import struct
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TOOL_DIR = Path(__file__).resolve().parent
DEPS_DIR = TOOL_DIR / "dependencies"
ARTIFACTS_DIR = TOOL_DIR / "artifacts"
if str(DEPS_DIR) not in sys.path:
    sys.path.insert(0, str(DEPS_DIR))

from core.item_metadata import (
    ITEM_DISPLAY_NAME_BY_RAW_VALUE,
    ITEM_ENUM_NAMES_BY_ID,
    ITEMS,
    normalize_item_name_for_rarity,
)
from infra.memory.game_data_client import GameDataClient
from infra.memory.map_marker_client import MapMarkerMemoryClient
from infra.memory.reader import ProcessMemory

try:
    import keyboard
except ImportError:
    keyboard = None

try:
    import win32gui
    import win32process
except ImportError:
    win32gui = None
    win32process = None

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    console = Console()
except ImportError:
    Console = None
    Panel = None
    Table = None
    console = None

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import numpy as np
except ImportError:
    np = None

PROCESS_NAME = "Megabonk.exe"
MODULE_NAME = "GameAssembly.dll"

MY_PLAYER_TYPE_INFO_OFFSET = 0x2F620F8
CLASS_STATIC_FIELDS_OFFSET = 0xB8
MY_PLAYER_INSTANCE_OFFSET = 0x08

MAP_CONTROLLER_TYPE_INFO_OFFSET = 0x2F58E08
MAP_CONTROLLER_STAGE_INDEX_OFFSET = 0x08
SHADY_GUY_TYPE_INFO_OFFSET = 0x2FB5928

ITEM_DATA_ENUM_OFFSET = 0x54

SHADY_RARITY_OFFSET = 0x90
SHADY_ITEMS_LIST_OFFSET = 0x98
SHADY_SECONDARY_LIST_OFFSET = 0xA0
SHADY_PRICES_ARRAY_OFFSET = 0xA8
SHADY_DONE_OFFSET = 0xB0
NATIVE_COMP_OFFSET = 0x10

MICROWAVE_TYPE_INFO_OFFSET = 0x2FB57D8
MICROWAVE_RARITY_OFFSET = 0x80
MICROWAVE_USES_LEFT_OFFSET = 0x84

MOAI_TYPE_INFO_OFFSET = 0x2FB5D18
BOSS_CURSE_TYPE_INFO_OFFSET = 0x2FB5B20

PLAYER_STATS_TYPE_INFO_OFFSET = 0x02F6A4B8
PLAYER_STATS_ROOT_OFFSET = 0x0
OWNER_STATS_OFFSET = 0x40
PLAYER_INVENTORY_OFFSET = 0x28
CHARACTER_DATA_OFFSET = 0x18
CHARACTER_DATA_CHARACTER_ID_OFFSET = 0x50

MY_TIME_TYPE_INFO_OFFSET = 0x02F62398
MY_TIME_TIME_OFFSET = 0x04
STAGE_TIMER_OFFSET = 0x1C

MAP_CONTROLLER_CURRENT_STAGE_OFFSET = 0x18
STAGE_DATA_TIMELINE_OFFSET = 0xD0
STAGE_TIMELINE_STAGE_TIME_OFFSET = 0x10

PLAYER_STATUS_EFFECTS_OFFSET = 0x38
PLAYER_STATUS_EFFECTS_DICT_OFFSET = 0x10
DICT_ENTRIES_OFFSET = 0x18
DICT_COUNT_OFFSET = 0x20
DICT_ENTRY_START_OFFSET = 0x20
DICT_ENTRY_SIZE = 0x18
DICT_ENTRY_HASH_CODE_OFFSET = 0x0
DICT_ENTRY_KEY_OFFSET = 0x8
DICT_ENTRY_VALUE_OFFSET = 0x10

STATUS_EFFECT_EXPIRATION_OFFSET = 0x20
STATUS_EFFECT_ADDED_OFFSET = 0x24
ARRAY_LENGTH_OFFSET = 0x18

DEFAULT_STAGE_DURATIONS: dict[int, float] = {
    0: 600.0,
    1: 540.0,
    2: 480.0,
}

POWERUP_EFFECT_NAMES: dict[int, str] = {
    0: "Haste",
    1: "Rage",
    2: "Shield",
    3: "Stonks",
    4: "Clock / Za Warudo",
}


CHARACTER_NAMES = {
    0: "Fox",
    1: "Calcium",
    2: "Sir Oofie",
    3: "Cl4nk",
    4: "Megachad",
    5: "Ogre",
    6: "Robinette",
    7: "Athena",
    8: "Birdo",
    9: "Bush",
    10: "Bandit",
    11: "Monke",
    12: "Noelle",
    13: "Tony McZoom",
    14: "Amog",
    15: "Spaceman",
    16: "Ninja",
    17: "Vlad",
    18: "Dice",
    19: "Sir Chadwell",
    20: "Roberto",
}

MICROWAVE_COLORS = {
    0: ("White", "white", "bright_white"),
    1: ("Blue", "blue", "bold cyan"),
    2: ("Purple", "purple", "bold magenta"),
    3: ("Gold", "gold", "bold yellow"),
}

# ==============================================================================
# Stage 1 Seed Filter Thresholds (Editable)
# ==============================================================================
THRESHOLD_SHADY_PLUS_MOAI = 0
THRESHOLD_MICROWAVES = 2
THRESHOLD_BOSS_CURSES = 1
THRESHOLD_MAGNET_CURSES = 2
REQUIRE_BOTH_MICROWAVES_WHITE = False  # Set to False so microwaves of any color/tier satisfy threshold and are reported

# ==============================================================================
# Target Shady Guy Items (Tracked for Pricing, Sector & Inventory Display)
# ==============================================================================
TARGET_SHADY_ITEMS = {
    41: "Anvil",
    22: "Dragonfire",
    15: "Spicy Meatball",
    47: "Soul Harvester",
    57: "Kevin",
    45: "Electric Plug",
    32: "Echo Shard",
}

# ==============================================================================
# Required Shady Guy Items Filter (Editable)
# ==============================================================================
# Configure items that MUST appear among Shady Guy offerings for a seed to match on Stage 1.
# - REQUIRED_ALL_ITEM_IDS (AND / Must-Have): ALL items in this list MUST appear on the map.
# - REQUIRED_ANY_ITEM_IDS (OR / Any-Of):    At least ONE item in this list MUST appear on the map.
#
# Examples:
# - REQUIRED_ALL_ITEM_IDS = [41, 57], REQUIRED_ANY_ITEM_IDS = [47, 22]
#   -> Map must have BOTH Anvil (41) AND Kevin (57) AND at least ONE of [Soul Harvester (47), Dragonfire (22)].
# - If both lists are empty, no specific items are required (shrine & curse thresholds only).
#
# ------------------------------------------------------------------------------
# COMPLETE ITEM ID REFERENCE TABLE (IDs 0 - 87)
# Sorted by Rarity (Legendary > Rare > Uncommon > Common), then Name
# ------------------------------------------------------------------------------
#  ID | Item Name                 | In-Game UI Name           | Rarity
# ----+---------------------------+---------------------------+-----------
#  41 | Anvil                     | Anvil                     | LEGENDARY
#  62 | Bloody Cleaver            | Bloody Cleaver            | LEGENDARY
#   3 | Bonker                    | Big Bonk                  | LEGENDARY
#  16 | Chonkplate                | Chonkplate                | LEGENDARY
#  22 | Dragonfire                | Dragonfire                | LEGENDARY
#  44 | Energy Core               | Energy Core               | LEGENDARY
#  12 | Giant Fork                | Giant Fork                | LEGENDARY
#  76 | Glove Power               | Power Gloves              | LEGENDARY
#  79 | Golden Ring               | Golden Ring               | LEGENDARY
#  54 | Holy Book                 | Holy Book                 | LEGENDARY
#  18 | Ice Cube                  | Ice Cube                  | LEGENDARY
#  49 | Joes Dagger               | Joe's Dagger              | LEGENDARY
#  17 | Lightning Orb             | Lightning Orb             | LEGENDARY
#  26 | Overpowered Lamp          | Overpowered Lamp          | LEGENDARY
#  84 | Pot                       | Pot (stainless steel)     | LEGENDARY
#  83 | Snek                      | Snek                      | LEGENDARY
#  47 | Soul Harvester            | Soul Harvester            | LEGENDARY
#  51 | Speed Boi                 | Speed Boi                 | LEGENDARY
#  15 | Spicy Meatball            | Spicy Meatball            | LEGENDARY
#  33 | Sucky Magnet              | Sucky Magnet              | LEGENDARY
#  87 | Wizards Hat               | Wizard's Hat              | LEGENDARY
#  25 | Za Warudo                 | Za Warudo                 | LEGENDARY
#  21 | Beefy Ring                | Beefy Ring                | RARE
#  46 | Bob Dead                  | Bob (Dead)                | RARE
#  85 | Bobs Lantern              | Bob's Light               | RARE
#  64 | Credit Card Green         | Credit Card (Green)       | RARE
#  20 | Demonic Soul              | Demonic Soul              | RARE
#  39 | Eagle Claw                | Eagle Claw                | RARE
#  60 | Gamer Goggles             | Gamer Goggles             | RARE
#  52 | Gasmask                   | Gas Mask                  | RARE
#  74 | Glove Blood               | Slurp Gloves              | RARE
#  75 | Glove Curse               | Cursed Grabbies           | RARE
#  11 | Grandmas Secret Tonic     | Grandma's Secret Tonic    | RARE
#  57 | Kevin                     | Kevin                     | RARE
#  48 | Mirror                    | Mirror                    | RARE
#  80 | Quins Mask                | Quin's Mask               | RARE
#  37 | Rollerblades              | Turbo Skates              | RARE
#  40 | Scarf                     | Scarf                     | RARE
#  31 | Shattered Wisdom          | Shattered Knowledge       | RARE
#  29 | Slutty Cannon             | Slutty Cannon             | RARE
#   2 | Spiky Shield              | Spiky Shield              | RARE
#  53 | Toxic Barrel              | Toxic Barrel              | RARE
#  34 | Backpack                  | Backpack                  | UNCOMMON
#  78 | Beacon                    | Beacon                    | UNCOMMON
#   1 | Beer                      | Beer                      | UNCOMMON
#  55 | Brass Knuckles            | Brass Knuckles            | UNCOMMON
#  36 | Campfire                  | Campfire                  | UNCOMMON
#   5 | Cowards Cloak             | Coward's cloak            | UNCOMMON
#  63 | Credit Card Red           | Credit Card (Red)         | UNCOMMON
#  10 | Demon Blade               | Demonic Blade             | UNCOMMON
#  19 | Demonic Blood             | Demonic Blood             | UNCOMMON
#  32 | Echo Shard                | Echo Shard                | UNCOMMON
#  45 | Electric Plug             | Electric Plug             | UNCOMMON
#  27 | Feathers                  | Feathers                  | UNCOMMON
#  72 | Glove Lightning           | Thunder Mitts             | UNCOMMON
#  73 | Glove Poison              | Moldy Gloves              | UNCOMMON
#  24 | Golden Shield             | Golden Shield             | UNCOMMON
#  14 | Golden Sneakers           | Golden Sneakers           | UNCOMMON
#  56 | Idle Juice                | Idle Juice                | UNCOMMON
#  66 | Leeching Crystal          | Leeching Crystal          | UNCOMMON
#   8 | Phantom Shroud            | Phantom Shroud            | UNCOMMON
#  86 | Pumpkin                   | Pumpkin                   | UNCOMMON
#  61 | Unstable Transfusion      | Unstable Transfusion      | UNCOMMON
#   7 | Battery                   | Battery                   | COMMON
#  58 | Borgar                    | Borgar                    | COMMON
#  65 | Boss Buster               | Boss Buster               | COMMON
#  68 | Cactus                    | Cactus                    | COMMON
#  35 | Clover                    | Clover                    | COMMON
#  43 | Cursed Doll               | Cursed Doll               | COMMON
#   9 | Forbidden Juice           | Forbidden Juice           | COMMON
#  28 | Ghost                     | Ghost                     | COMMON
#  23 | Golden Glove              | Golden Glove              | COMMON
#   6 | Gym Sauce                 | Gym Sauce                 | COMMON
#  70 | Ice Crystal               | Ice Crystal               | COMMON
#   0 | Key                       | Key                       | COMMON
#  59 | Medkit                    | Medkit                    | COMMON
#  13 | Moldy Cheese              | Moldy Cheese              | COMMON
#  42 | Oats                      | Oats                      | COMMON
#  82 | Old Mask                  | Old Mask                  | COMMON
#  38 | Skuleg                    | Skuleg                    | COMMON
#   4 | Slippery Ring             | Slippery Ring             | COMMON
#  67 | Tactical Glasses          | Tactical Glasses          | COMMON
#  71 | Time Bracelet             | Time Bracelet             | COMMON
#  30 | Turbo Socks               | Turbo Socks               | COMMON
#  77 | Wrench                    | Wrench                    | COMMON
#  69 | Cage Key                  | Golden key                | -
#  81 | Crypt Key                 | Crypt key                 | -
#  50 | Weeb Headset              | Weeb Headset              | -
# ------------------------------------------------------------------------------
REQUIRED_ALL_ITEM_IDS: list[int] = [41]  # Must-have items: ALL must be present on map (AND)
REQUIRED_ANY_ITEM_IDS: list[int] = [47] #22, 49, 15, 76, 17      # Any-of items: At least ONE must be present on map (OR)


# ==============================================================================
# Secondary Highlighted Shady Guy Items (Editable)
# ==============================================================================
# Items to be highlighted in a distinct color in Shady Guy inventory and distance tables:
HIGHLIGHTED_SHADY_ITEMS = {
    49: "Joe's Dagger",
    54: "Holy Book",
    17: "Lightning Orb",
    16: "Chonkplate",
    56: "Idle Juice",
    71: "Time Bracelet",
    43: "Cursed Doll",
    27: "Feathers",
    0: "Key",
    21: "Beefy Ring",
}
HIGHLIGHTED_ITEM_MARKER = "+"                  # Visual marker for secondary highlighted items
TARGET_ITEM_COLOR = "bold bright_red"          # Target items color (bright red)
REGULAR_ITEM_COLOR = "bold bright_white"       # Regular filler items (Common/Rare/Epic) (bright white)

# ==============================================================================
# Tier & Rarity Color Palette Configuration
# ==============================================================================
# User-specified 4-tier palette:
# 1. Common: Light Green
# 2. Rare: Cyan
# 3. Epic: Magenta
# 4. Legendary: Yellow
# Target items: Bright Red (*)
# Highlighted items: Tier-colored (+)
# Any other Legendary items: Yellow (bold yellow)
# Regular filler items (Common/Rare/Epic): Bright White
TIER_COLORS = {
    "COMMON": "bold light_green",
    "RARE": "bold cyan",
    "EPIC": "bold magenta",
    "LEGENDARY": "bold yellow",
    # Legacy alias
    "UNCOMMON": "bold cyan",
}

# Megabonk internal disassembly keys -> canonical 4-tier game rarities
INTERNAL_TO_GAME_RARITY = {
    "COMMON": "COMMON",
    "UNCOMMON": "RARE",
    "RARE": "EPIC",
    "LEGENDARY": "LEGENDARY",
}

ITEM_RARITY_BY_ID: dict[int, str] = {
    item.item_id: INTERNAL_TO_GAME_RARITY.get(item.rarity, item.rarity)
    for item in ITEMS
    if item.rarity
}

ITEM_RARITY_BY_NAME: dict[str, str] = {}
for _item in ITEMS:
    if not _item.rarity:
        continue
    _game_rarity = INTERNAL_TO_GAME_RARITY.get(_item.rarity, _item.rarity)
    for _name in (_item.ui_name, _item.scanner_name, _item.enum_name):
        if _name:
            ITEM_RARITY_BY_NAME[_name] = _game_rarity
            ITEM_RARITY_BY_NAME[_name.lower()] = _game_rarity


# ==============================================================================
# Seed Offerings Data Tracker (Records seed -> [items] into JSON)
# ==============================================================================
TRACK_SEED_OFFERINGS = True        # If True, saves seed -> [shady items] in JSON file
SEED_TRACKER_FILE = ARTIFACTS_DIR / "shady_seed_data.json"

# ==============================================================================
# Auto-Restart / Reroll Settings (Editable)
# ==============================================================================
AUTO_RESTART_ON_FAIL = True        # Automatically restart Stage 1 if criteria not met
PAUSE_GAME_ON_MATCH = True         # Automatically pause Megabonk (Escape) when criteria are met
FAST_EVALUATION = True             # Skip 0.8s Shady heap scan if shrine counts fail and tracking is off
READ_SETTINGS_FROM_GAME = True     # Automatically read Quick Reset key & hold duration from Megabonk
MANUAL_RESET_HOTKEY = None         # Set to string (e.g. 'p' or 'r') to override game settings, or None
MANUAL_HOLD_DURATION = None        # Set to float (e.g. 0.3) to override game settings, or None
REQUIRE_GAME_WINDOW_FOCUS = True   # Pause auto-restart if Megabonk is not focused
HOTKEY_TOGGLE_AUTORESTART = "f6"   # Global hotkey to toggle auto-restart ON/OFF
MAX_REROLLS = 0                    # Maximum rerolls (0 = unlimited until match)
# ==============================================================================
# Console Display Settings (Editable)
# ==============================================================================
CLEAR_CONSOLE_ON_OUTPUT = True      # Always clear old console output before displaying a new scan/evaluation report
# ==============================================================================

_RARITIES = ["COMMON", "RARE", "EPIC", "LEGENDARY"]


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("PartitionId", wintypes.WORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000


def clear_console(force: bool = False) -> None:
    """Clear the terminal screen and scrollback buffer for fresh output."""
    try:
        # Avoid clearing if stdout is redirected to a file or pipe, unless forced
        if not force and hasattr(sys.stdout, "isatty") and not sys.stdout.isatty():
            if not (console and getattr(console, "is_terminal", False)):
                return
    except Exception:
        pass

    try:
        if os.name == "nt":
            os.system("cls")
        else:
            os.system("clear")
    except Exception:
        pass

    if console:
        try:
            console.clear()
        except Exception:
            pass

    try:
        sys.stdout.write("\033[2J\033[3J\033[H")
        sys.stdout.flush()
    except Exception:
        pass


def clear_live_line() -> None:
    """Clear the active status line on stdout without leaving artifacts."""
    try:
        sys.stdout.write("\r\033[K" + (" " * 80) + "\r")
        sys.stdout.flush()
    except Exception:
        pass


def format_clock_time(seconds: float, is_overtime: bool = False) -> str:
    """Format seconds into MM:SS (or +MM:SS for overtime)."""
    total_seconds = max(0, int(round(seconds)))
    prefix = "+" if is_overtime else ""
    return f"{prefix}{total_seconds // 60:02d}:{total_seconds % 60:02d}"


def read_active_powerups(memory: ProcessMemory, module_base: int) -> dict:
    """Read active power-ups and Za Warudo / status effects from game memory.

    Returns:
        dict with keys:
            available (bool): True if memory read succeeded.
            my_time (float | None): Current game session clock (MyTime.time).
            stage_timer (float | None): Seconds elapsed on current stage.
            stage_time (float): Stage duration limit in seconds.
            is_overtime (bool): True if stage timer has passed stage_time.
            stage_clock (str): In-game countdown clock (e.g. '06:45' or '+01:15').
            za_warudo_held (int): Number of Za Warudo items held in inventory.
            effects (list[dict]): Active status effects sorted by remaining time:
                effect_id (int)
                name (str): e.g. 'Clock / Za Warudo', 'Rage', 'Shield', 'Stonks', etc.
                remaining_seconds (float): Seconds remaining until expiration.
                duration_seconds (float): Total granted duration of this buff instance.
                end_clock (str): Exact in-game stage countdown clock mark when buff expires.
                added_time (float): Session timestamp when buff was added.
                expiration_time (float): Session timestamp when buff expires.
    """
    res = {
        "available": False,
        "my_time": None,
        "stage_timer": None,
        "stage_time": 600.0,
        "is_overtime": False,
        "stage_clock": "--:--",
        "za_warudo_held": 0,
        "effects": [],
    }

    # 1. Read stage time from MapController
    stage_idx = 0
    stage_time = 600.0
    try:
        mc_type = memory.read_ptr(module_base + MAP_CONTROLLER_TYPE_INFO_OFFSET)
        if mc_type and is_valid_class_ptr(mc_type):
            mc_static = memory.read_ptr(mc_type + CLASS_STATIC_FIELDS_OFFSET)
            if mc_static and mc_static > 0x10000:
                s_idx = memory.read_i32(mc_static + MAP_CONTROLLER_STAGE_INDEX_OFFSET)
                if 0 <= s_idx <= 10:
                    stage_idx = s_idx
                current_stage = memory.read_ptr(mc_static + MAP_CONTROLLER_CURRENT_STAGE_OFFSET)
                if current_stage and current_stage > 0x10000:
                    timeline = memory.read_ptr(current_stage + STAGE_DATA_TIMELINE_OFFSET)
                    if timeline and timeline > 0x10000:
                        st = memory.read_float(timeline + STAGE_TIMELINE_STAGE_TIME_OFFSET)
                        if st and math.isfinite(st) and 0 < st <= 1800:
                            stage_time = st
    except Exception:
        pass
    if stage_time == 600.0 and stage_idx in DEFAULT_STAGE_DURATIONS:
        stage_time = DEFAULT_STAGE_DURATIONS[stage_idx]
    res["stage_time"] = stage_time

    # 2. Read MyTime static fields
    my_time_seconds = None
    stage_timer_seconds = None
    try:
        my_time_type = memory.read_ptr(module_base + MY_TIME_TYPE_INFO_OFFSET)
        if my_time_type and is_valid_class_ptr(my_time_type):
            my_time_static = memory.read_ptr(my_time_type + CLASS_STATIC_FIELDS_OFFSET)
            if my_time_static and my_time_static > 0x10000:
                my_time_seconds = memory.read_float(my_time_static + MY_TIME_TIME_OFFSET)
                stage_timer_seconds = memory.read_float(my_time_static + STAGE_TIMER_OFFSET)
    except Exception:
        pass

    if my_time_seconds is None or stage_timer_seconds is None or not math.isfinite(my_time_seconds):
        return res

    res["my_time"] = my_time_seconds
    res["stage_timer"] = stage_timer_seconds
    is_overtime = stage_timer_seconds > stage_time
    res["is_overtime"] = is_overtime

    if not is_overtime:
        stage_clock_remaining = max(0.0, stage_time - stage_timer_seconds)
        stage_clock_str = format_clock_time(stage_clock_remaining, is_overtime=False)
    else:
        stage_clock_overtime = stage_timer_seconds - stage_time
        stage_clock_str = format_clock_time(stage_clock_overtime, is_overtime=True)
    res["stage_clock"] = stage_clock_str
    res["available"] = True

    # 3. Read PlayerStatusEffects
    try:
        stats_type = memory.read_ptr(module_base + PLAYER_STATS_TYPE_INFO_OFFSET)
        if not stats_type or not is_valid_class_ptr(stats_type):
            return res
        stats_static = memory.read_ptr(stats_type + CLASS_STATIC_FIELDS_OFFSET)
        if not stats_static or stats_static < 0x10000:
            return res
        root = memory.read_ptr(stats_static + PLAYER_STATS_ROOT_OFFSET)
        if not root or root < 0x10000:
            return res
        owner_stats = memory.read_ptr(root + OWNER_STATS_OFFSET)
        if not owner_stats or owner_stats < 0x10000:
            return res
        player_inventory = memory.read_ptr(owner_stats + PLAYER_INVENTORY_OFFSET)
        if not player_inventory or player_inventory < 0x10000:
            return res

        # Check if Za Warudo item (Item 25) is held in inventory
        try:
            item_dicts = []
            # Route 1: inventory_container (0xA0) -> passive_item_dict (0x50)
            try:
                inv_container = memory.read_ptr(owner_stats + 0xA0)
                if inv_container and inv_container > 0x10000:
                    p_dict = memory.read_ptr(inv_container + 0x50)
                    if p_dict and p_dict > 0x10000:
                        item_dicts.append(p_dict)
            except Exception:
                pass
            # Route 2: player_inventory (0x28) -> item_inventory (0x20) -> items_dict (0x10)
            try:
                item_inv = memory.read_ptr(player_inventory + 0x20)
                if item_inv and item_inv > 0x10000:
                    p_dict = memory.read_ptr(item_inv + 0x10)
                    if p_dict and p_dict > 0x10000:
                        item_dicts.append(p_dict)
            except Exception:
                pass

            for items_dict in dict.fromkeys(item_dicts):
                i_entries = memory.read_ptr(items_dict + DICT_ENTRIES_OFFSET)
                i_cap = memory.read_i32(i_entries + ARRAY_LENGTH_OFFSET) if i_entries else 0
                if 0 < i_cap <= 256 and hasattr(memory, "read_bytes"):
                    tot_len = i_cap * DICT_ENTRY_SIZE
                    i_buf = memory.read_bytes(i_entries + DICT_ENTRY_START_OFFSET, tot_len)
                    if i_buf and len(i_buf) >= tot_len:
                        for i in range(i_cap):
                            off = i * DICT_ENTRY_SIZE
                            h_code, _, iid, item_obj = struct.unpack_from("<iii4xQ", i_buf, off)
                            if h_code >= 0 and iid == 25:
                                cnt = memory.read_i32(item_obj + 0x18) if item_obj else 1
                                res["za_warudo_held"] = max(1, cnt)
                                break
                elif 0 < i_cap <= 256:
                    for i in range(i_cap):
                        entry_addr = i_entries + DICT_ENTRY_START_OFFSET + (i * DICT_ENTRY_SIZE)
                        if memory.read_i32(entry_addr + DICT_ENTRY_HASH_CODE_OFFSET) < 0:
                            continue
                        iid = memory.read_i32(entry_addr + DICT_ENTRY_KEY_OFFSET)
                        if iid == 25:  # Za Warudo
                            item_obj = memory.read_ptr(entry_addr + DICT_ENTRY_VALUE_OFFSET)
                            cnt = memory.read_i32(item_obj + 0x18) if item_obj else 1
                            res["za_warudo_held"] = max(1, cnt)
                            break
                if res["za_warudo_held"] > 0:
                    break
        except Exception:
            pass

        status_effects = memory.read_ptr(player_inventory + PLAYER_STATUS_EFFECTS_OFFSET)
        if not status_effects or status_effects < 0x10000:
            return res
        dictionary_address = memory.read_ptr(status_effects + PLAYER_STATUS_EFFECTS_DICT_OFFSET)
        if not dictionary_address or dictionary_address < 0x10000:
            return res
        entries = memory.read_ptr(dictionary_address + DICT_ENTRIES_OFFSET)
        if not entries or entries < 0x10000:
            return res
        count = memory.read_i32(dictionary_address + DICT_COUNT_OFFSET)
        if count <= 0 or count > 128:
            return res
        capacity = memory.read_i32(entries + ARRAY_LENGTH_OFFSET)
        if capacity <= 0 or capacity > 128:
            return res

        active_effects = []
        tot_bytes = capacity * DICT_ENTRY_SIZE
        dict_buf = memory.read_bytes(entries + DICT_ENTRY_START_OFFSET, tot_bytes) if hasattr(memory, "read_bytes") else None

        if dict_buf and len(dict_buf) >= tot_bytes:
            for index in range(capacity):
                off = index * DICT_ENTRY_SIZE
                hash_code, _, effect_id, effect_ptr = struct.unpack_from("<iii4xQ", dict_buf, off)
                if hash_code < 0 or effect_id not in POWERUP_EFFECT_NAMES or effect_ptr < 0x10000:
                    continue
                try:
                    eff_buf = memory.read_bytes(effect_ptr + STATUS_EFFECT_EXPIRATION_OFFSET, 8) if hasattr(memory, "read_bytes") else None
                    if eff_buf and len(eff_buf) >= 8:
                        expiration_time, added_time = struct.unpack("<ff", eff_buf)
                    else:
                        expiration_time = memory.read_float(effect_ptr + STATUS_EFFECT_EXPIRATION_OFFSET)
                        added_time = memory.read_float(effect_ptr + STATUS_EFFECT_ADDED_OFFSET)
                    remaining = expiration_time - my_time_seconds
                    if remaining <= 0 or not math.isfinite(remaining):
                        continue

                    if not is_overtime:
                        end_clock_seconds = max(0.0, stage_clock_remaining - remaining)
                        end_clock_str = format_clock_time(end_clock_seconds, is_overtime=False)
                    else:
                        end_clock_seconds = stage_clock_overtime + remaining
                        end_clock_str = format_clock_time(end_clock_seconds, is_overtime=True)

                    duration = (
                        expiration_time - added_time
                        if (math.isfinite(added_time) and added_time <= expiration_time)
                        else remaining
                    )

                    active_effects.append({
                        "effect_id": effect_id,
                        "name": POWERUP_EFFECT_NAMES[effect_id],
                        "remaining_seconds": round(remaining, 1),
                        "duration_seconds": round(duration, 1),
                        "end_clock": end_clock_str,
                        "added_time": added_time,
                        "expiration_time": expiration_time,
                    })
                except Exception:
                    continue
        else:
            for index in range(capacity):
                entry = entries + DICT_ENTRY_START_OFFSET + (index * DICT_ENTRY_SIZE)
                try:
                    hash_code = memory.read_i32(entry + DICT_ENTRY_HASH_CODE_OFFSET)
                    if hash_code < 0:
                        continue
                    effect_id = memory.read_i32(entry + DICT_ENTRY_KEY_OFFSET)
                    if effect_id not in POWERUP_EFFECT_NAMES:
                        continue
                    effect_ptr = memory.read_ptr(entry + DICT_ENTRY_VALUE_OFFSET)
                    if not effect_ptr or effect_ptr < 0x10000:
                        continue
                    expiration_time = memory.read_float(effect_ptr + STATUS_EFFECT_EXPIRATION_OFFSET)
                    added_time = memory.read_float(effect_ptr + STATUS_EFFECT_ADDED_OFFSET)
                    remaining = expiration_time - my_time_seconds
                    if remaining <= 0 or not math.isfinite(remaining):
                        continue

                    if not is_overtime:
                        end_clock_seconds = max(0.0, stage_clock_remaining - remaining)
                        end_clock_str = format_clock_time(end_clock_seconds, is_overtime=False)
                    else:
                        end_clock_seconds = stage_clock_overtime + remaining
                        end_clock_str = format_clock_time(end_clock_seconds, is_overtime=True)

                    duration = (
                        expiration_time - added_time
                        if (math.isfinite(added_time) and added_time <= expiration_time)
                        else remaining
                    )

                    active_effects.append({
                        "effect_id": effect_id,
                        "name": POWERUP_EFFECT_NAMES[effect_id],
                        "remaining_seconds": round(remaining, 1),
                        "duration_seconds": round(duration, 1),
                        "end_clock": end_clock_str,
                        "added_time": added_time,
                        "expiration_time": expiration_time,
                    })
                except Exception:
                    continue

        active_effects.sort(key=lambda e: e["remaining_seconds"])
        res["effects"] = active_effects
    except Exception:
        pass

    return res




def render_active_powerups_block(powerup_data: dict | None, use_rich: bool = True) -> None:
    """Render Active Power-ups and Za Warudo table/section in stage report."""
    if not powerup_data:
        return
    effects = powerup_data.get("effects", [])
    za_held = powerup_data.get("za_warudo_held", 0)
    if not effects and za_held <= 0:
        return

    stage_clock = powerup_data.get("stage_clock", "--:--")

    if use_rich and console is not None:
        pu_table = Table(
            title=f"⚡ ACTIVE POWER-UPS & BUFFS (Stage Clock: {stage_clock})",
            header_style="bold bright_white",
        )
        pu_table.add_column("Power-Up / Buff", style="bold")
        pu_table.add_column("Status / Time Left", justify="right")
        pu_table.add_column("Expires At (Stage Clock)", justify="center", style="bold bright_yellow")
        pu_table.add_column("Stage Clock", justify="center", style="dim")

        if za_held > 0:
            pu_table.add_row(
                "[bold bright_yellow]Za Warudo (Held Item)[/]",
                f"[bold green]Active Protection (x{za_held})[/]",
                "[dim]On Lethal Damage[/]",
                stage_clock,
            )

        for eff in effects:
            name = eff.get("name", "Unknown")
            rem = eff.get("remaining_seconds", 0.0)
            end_clock = eff.get("end_clock", "--:--")
            if "Za Warudo" in name or "Clock" in name:
                name_styled = f"[bold bright_yellow]{name}[/]"
            elif "Rage" in name:
                name_styled = f"[bold bright_red]{name}[/]"
            elif "Shield" in name:
                name_styled = f"[bold bright_cyan]{name}[/]"
            elif "Stonks" in name:
                name_styled = f"[bold bright_green]{name}[/]"
            else:
                name_styled = f"[bold bright_magenta]{name}[/]"

            pu_table.add_row(
                name_styled,
                f"[bold white]{rem:.1f}s remaining[/]",
                f"[bold bright_yellow]{end_clock}[/]",
                stage_clock,
            )

        console.print(pu_table)
    else:
        print("-" * 80, flush=True)
        print(f"⚡ ACTIVE POWER-UPS & BUFFS (Stage Clock: {stage_clock}):", flush=True)
        if za_held > 0:
            print(f"  * Za Warudo (Held Item x{za_held}): Active Protection (Triggers on lethal damage)", flush=True)
        for eff in effects:
            name = eff.get("name", "Unknown")
            rem = eff.get("remaining_seconds", 0.0)
            end_clock = eff.get("end_clock", "--:--")
            print(f"  * {name}: {rem:.1f}s remaining -> Ends at {end_clock} (Stage Clock: {stage_clock})", flush=True)


def format_single_powerup_line(
    name: str,
    end_clock: str,
    stage_clock: str,
    is_ended: bool = False,
    use_rich: bool = True,
) -> str:
    """Format a single power-up line: bright/colored when active, struck-through and dimmed when ended."""
    plain = f"⚡ [POWER-UP] {name}: Active until {end_clock} (Clock: {stage_clock})"
    if is_ended:
        if use_rich:
            return f"[dim strike]⚡ [POWER-UP] {name}: Active until {end_clock} (Clock: {stage_clock})[/]"
        return f"\033[2;9m{plain}\033[0m"

    if use_rich:
        if "Za Warudo" in name or "Clock" in name:
            name_tag = f"[bold bright_yellow]{name}[/]"
        elif "Rage" in name:
            name_tag = f"[bold bright_red]{name}[/]"
        elif "Shield" in name:
            name_tag = f"[bold bright_cyan]{name}[/]"
        elif "Stonks" in name:
            name_tag = f"[bold bright_green]{name}[/]"
        else:
            name_tag = f"[bold bright_magenta]{name}[/]"
        return f"⚡ [bold yellow][POWER-UP][/] {name_tag}: Active until [bold bright_yellow]{end_clock}[/] [dim](Clock: {stage_clock})[/]"

    return plain


class PowerupDisplayTracker:
    """Tracks active power-ups, printing a single line when activated and striking/dimming it when ended."""

    def __init__(self, console_obj: Any = None) -> None:
        self.console = console_obj
        self.active_powerup_ids: set[int] = set()
        self.last_seen_effects: dict[int, dict] = {}
        self.last_seen_za_warudo_held: int = 0
        self.displayed_lines: list[dict] = []
        self.intervening_prints: bool = False

    def reset(self) -> None:
        """Reset tracking state for a new run or stage."""
        self.active_powerup_ids.clear()
        self.last_seen_effects.clear()
        self.last_seen_za_warudo_held = 0
        self.displayed_lines.clear()
        self.intervening_prints = False

    def on_console_cleared(self) -> None:
        """Called when clear_console() is invoked."""
        active_entries = [entry for entry in self.displayed_lines if entry["status"] == "active"]
        self.displayed_lines.clear()
        self.intervening_prints = False
        if active_entries:
            for entry in active_entries:
                self._print_line(entry["line_rich"], entry["line_plain"])
                self.displayed_lines.append(entry)

    def on_other_print(self) -> None:
        """Called if an unrelated message is printed without a console clear."""
        self.intervening_prints = True

    def _print_line(self, rich_str: str, plain_str: str) -> None:
        c = self.console or console
        if c is not None:
            c.print(rich_str)
        else:
            print(plain_str, flush=True)

    def _strike_out_line(self, match_idx: int) -> None:
        entry = self.displayed_lines[match_idx]
        entry["status"] = "ended"

        ended_rich = entry["line_ended_rich"]
        ended_ansi = entry["line_ended_plain"]

        is_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
        if is_tty and not self.intervening_prints:
            dist = len(self.displayed_lines) - match_idx
            try:
                sys.stdout.write(f"\033[{dist}A\r\033[K{ended_ansi}\033[{dist}B\r")
                sys.stdout.flush()
            except Exception:
                self._print_line(ended_rich, ended_ansi)
        else:
            self._print_line(ended_rich, ended_ansi)

    def update(self, pu_data: dict) -> None:
        """Process power-up state updates from memory."""
        current_effects = pu_data.get("effects", [])
        current_effect_ids = {e["effect_id"] for e in current_effects}
        current_my_time = pu_data.get("my_time")
        stage_clock = pu_data.get("stage_clock", "--:--")
        current_za_held = pu_data.get("za_warudo_held", 0)

        # Track Za Warudo held item status
        if current_za_held > 0 and self.last_seen_za_warudo_held == 0:
            line_rich = (
                f"⚡ [bold yellow][HELD ITEM][/] [bold bright_yellow]Za Warudo[/] (x{current_za_held}): "
                f"[green]Active Protection (Freezes time on lethal damage)[/] [dim](Clock: {stage_clock})[/]"
            )
            line_plain = f"⚡ [HELD ITEM] Za Warudo (x{current_za_held}): Active Protection (Freezes time on lethal damage) (Clock: {stage_clock})"
            line_ended_rich = (
                f"[dim strike]⚡ [HELD ITEM] Za Warudo: Consumed / Broken (Clock: {stage_clock})[/]"
            )
            line_ended_plain = (
                f"\033[2;9m⚡ [HELD ITEM] Za Warudo: Consumed / Broken (Clock: {stage_clock})\033[0m"
            )

            self._print_line(line_rich, line_plain)

            self.displayed_lines.append({
                "effect_id": -25,
                "name": "Za Warudo (Held)",
                "end_clock": "--:--",
                "stage_clock": stage_clock,
                "expiration_time": None,
                "line_rich": line_rich,
                "line_plain": line_plain,
                "line_ended_rich": line_ended_rich,
                "line_ended_plain": line_ended_plain,
                "status": "active",
            })
        elif current_za_held > 0 and current_za_held != self.last_seen_za_warudo_held:
            diff = current_za_held - self.last_seen_za_warudo_held
            if diff > 0:
                msg_rich = f"[green]Active Protection (Added +{diff}, total x{current_za_held})[/]"
                msg_plain = f"Active Protection (Added +{diff}, total x{current_za_held})"
            else:
                msg_rich = f"[yellow]Active Protection ({abs(diff)} consumed, x{current_za_held} remaining)[/]"
                msg_plain = f"Active Protection ({abs(diff)} consumed, x{current_za_held} remaining)"
            line_rich = (
                f"⚡ [bold yellow][HELD ITEM][/] [bold bright_yellow]Za Warudo[/] (x{current_za_held}): "
                f"{msg_rich} [dim](Clock: {stage_clock})[/]"
            )
            line_plain = f"⚡ [HELD ITEM] Za Warudo (x{current_za_held}): {msg_plain} (Clock: {stage_clock})"
            self._print_line(line_rich, line_plain)
        elif current_za_held == 0 and self.last_seen_za_warudo_held > 0:
            for idx, entry in enumerate(self.displayed_lines):
                if entry.get("effect_id") == -25 and entry.get("status") == "active":
                    self._strike_out_line(idx)

        self.last_seen_za_warudo_held = current_za_held

        # 1. Detect newly activated power-ups and renewed power-ups of the same type
        new_or_renewed_buffs = []
        for eff in current_effects:
            eid = eff["effect_id"]
            exp_time = eff.get("expiration_time")
            added_time = eff.get("added_time")
            rem_sec = eff.get("remaining_seconds", 0.0)
            end_clock = eff.get("end_clock", "--:--")

            if eid not in self.last_seen_effects:
                new_or_renewed_buffs.append(eff)
                self.last_seen_effects[eid] = {
                    "expiration_time": exp_time,
                    "added_time": added_time,
                    "end_clock": end_clock,
                    "remaining_seconds": rem_sec,
                }
            else:
                last = self.last_seen_effects[eid]
                is_renewed = False
                if exp_time is not None and last.get("expiration_time") is not None:
                    if exp_time > last["expiration_time"] + 0.1:
                        is_renewed = True
                if not is_renewed and added_time is not None and last.get("added_time") is not None:
                    if added_time > last["added_time"] + 0.1:
                        is_renewed = True
                if not is_renewed and rem_sec > last.get("remaining_seconds", 0.0) + 1.0:
                    is_renewed = True
                if not is_renewed and end_clock != last.get("end_clock") and rem_sec >= last.get("remaining_seconds", 0.0):
                    is_renewed = True

                if is_renewed:
                    new_or_renewed_buffs.append(eff)
                    self.last_seen_effects[eid] = {
                        "expiration_time": exp_time,
                        "added_time": added_time,
                        "end_clock": end_clock,
                        "remaining_seconds": rem_sec,
                    }
                else:
                    self.last_seen_effects[eid]["remaining_seconds"] = rem_sec
                    if exp_time is not None:
                        self.last_seen_effects[eid]["expiration_time"] = exp_time
                    if added_time is not None:
                        self.last_seen_effects[eid]["added_time"] = added_time
                    self.last_seen_effects[eid]["end_clock"] = end_clock

        # Print feed line for each new or renewed power-up
        for nb in new_or_renewed_buffs:
            eid = nb["effect_id"]
            name = nb.get("name") or POWERUP_EFFECT_NAMES.get(eid, f"Effect {eid}")
            end_clock = nb.get("end_clock", "--:--")
            exp_time = nb.get("expiration_time")
            if exp_time is None and current_my_time is not None:
                exp_time = current_my_time + nb.get("remaining_seconds", 0.0)

            line_rich = format_single_powerup_line(name, end_clock, stage_clock, is_ended=False, use_rich=True)
            line_plain = format_single_powerup_line(name, end_clock, stage_clock, is_ended=False, use_rich=False)
            line_ended_rich = format_single_powerup_line(name, end_clock, stage_clock, is_ended=True, use_rich=True)
            line_ended_plain = format_single_powerup_line(name, end_clock, stage_clock, is_ended=True, use_rich=False)

            self._print_line(line_rich, line_plain)

            self.displayed_lines.append({
                "effect_id": eid,
                "name": name,
                "end_clock": end_clock,
                "stage_clock": stage_clock,
                "expiration_time": exp_time,
                "line_rich": line_rich,
                "line_plain": line_plain,
                "line_ended_rich": line_ended_rich,
                "line_ended_plain": line_ended_plain,
                "status": "active",
            })

        # 2. Check for expired power-up entries in displayed_lines
        # A line expires if:
        #  a) Its effect_id is no longer present in current_effects (completely disappeared/wiped)
        #  b) current_time (my_time or stage_timer) has reached or passed this entry's expiration_time
        current_time = current_my_time if current_my_time is not None else pu_data.get("stage_timer")
        for idx, entry in enumerate(self.displayed_lines):
            if entry["status"] != "active":
                continue

            eid = entry["effect_id"]
            if eid == -25:
                # Za Warudo held item handled separately via za_warudo_held count
                continue

            has_expired = False

            if eid not in current_effect_ids:
                has_expired = True
            elif current_time is not None and entry.get("expiration_time") is not None:
                if current_time >= entry["expiration_time"]:
                    has_expired = True

            if has_expired:
                self._strike_out_line(idx)

        # Clean up last_seen_effects for effects that are no longer active
        for eid in list(self.last_seen_effects.keys()):
            if eid not in current_effect_ids:
                del self.last_seen_effects[eid]

        self.active_powerup_ids = current_effect_ids


def get_item_name(item_id: int) -> str:
    if item_id in ITEM_ENUM_NAMES_BY_ID:
        raw_enum = ITEM_ENUM_NAMES_BY_ID[item_id]
        return ITEM_DISPLAY_NAME_BY_RAW_VALUE.get(raw_enum, raw_enum)
    return f"UnknownItem({item_id})"


def is_target_item(item_id: int | None, item_name: str | None = None) -> bool:
    """Check if an item is one of the primary target or required items."""
    req_ids_set = set(REQUIRED_ALL_ITEM_IDS) | set(REQUIRED_ANY_ITEM_IDS)
    if item_id is not None:
        if item_id in TARGET_SHADY_ITEMS or item_id in req_ids_set:
            return True
    if item_name is not None:
        if item_name in TARGET_SHADY_ITEMS.values():
            return True
        for req_id in req_ids_set:
            if get_item_name(req_id) == item_name:
                return True
    return False


def is_highlighted_item(item_id: int | None, item_name: str | None = None) -> bool:
    """Check if an item is in the secondary highlighted list."""
    if item_id is not None and item_id in HIGHLIGHTED_SHADY_ITEMS:
        return True
    if item_name is not None and item_name in HIGHLIGHTED_SHADY_ITEMS.values():
        return True
    return False


def get_item_rarity(item_id: int | None = None, item_name: str | None = None) -> str:
    """Resolve an item's rarity string ('COMMON', 'UNCOMMON', 'RARE', 'LEGENDARY')."""
    if item_id is not None and item_id in ITEM_RARITY_BY_ID:
        return ITEM_RARITY_BY_ID[item_id]
    if item_name:
        if item_name in ITEM_RARITY_BY_NAME:
            return ITEM_RARITY_BY_NAME[item_name]
        lower = item_name.lower()
        if lower in ITEM_RARITY_BY_NAME:
            return ITEM_RARITY_BY_NAME[lower]
        try:
            norm = normalize_item_name_for_rarity(item_name)
            if norm in ITEM_RARITY_BY_NAME:
                return ITEM_RARITY_BY_NAME[norm]
        except Exception:
            pass
    return "COMMON"


def get_tier_style(rarity: str | None) -> str:
    """Return Rich style tag for an item or Shady Guy rarity tier."""
    if not rarity:
        return TIER_COLORS["COMMON"]
    return TIER_COLORS.get(str(rarity).upper(), TIER_COLORS["COMMON"])


def format_item_display(
    item_id: int | None = None,
    item_name: str | None = None,
    cost_info: str = "",
    use_rich: bool = True,
) -> str:
    """Format item name with color styling: target (bright red), highlighted (tier-colored), other legendary (yellow), rest (bright white)."""
    name = item_name or (get_item_name(item_id) if item_id is not None else "Unknown")
    is_tgt = is_target_item(item_id, name)
    is_hl = is_highlighted_item(item_id, name)

    marker = "*" if is_tgt else (HIGHLIGHTED_ITEM_MARKER if is_hl else "")

    if not use_rich:
        return f"{name}{marker}{cost_info}"

    if is_tgt:
        style = TARGET_ITEM_COLOR
    elif is_hl:
        rarity = get_item_rarity(item_id, name)
        style = get_tier_style(rarity)
    else:
        rarity = get_item_rarity(item_id, name)
        if rarity == "LEGENDARY":
            style = get_tier_style("LEGENDARY")
        else:
            style = REGULAR_ITEM_COLOR

    if cost_info:
        return f"[{style}]{name}{marker}[/][bold bright_yellow]{cost_info}[/]"
    return f"[{style}]{name}{marker}[/]"


def format_shady_rarity(rarity: str | int | None, use_rich: bool = True) -> str:
    """Format a Shady Guy rarity tier tag (e.g. COMMON, RARE, EPIC, LEGENDARY)."""
    if rarity is None or rarity == "-":
        return "-"
    if isinstance(rarity, int) and 0 <= rarity < len(_RARITIES):
        r_str = _RARITIES[rarity]
    elif str(rarity).isdigit() and 0 <= int(rarity) < len(_RARITIES):
        r_str = _RARITIES[int(rarity)]
    else:
        raw_str = str(rarity).upper()
        r_str = "RARE" if raw_str == "UNCOMMON" else raw_str
    if not use_rich:
        return r_str
    st = get_tier_style(r_str)
    return f"[{st}]{r_str}[/]"


def format_vendor_display(shady_num: int | Any, rarity: str | int | None, use_rich: bool = True) -> str:
    """Format vendor display string with tier-colored rarity tag."""
    if rarity is None or rarity == "-":
        r_str = "COMMON"
    elif isinstance(rarity, int) and 0 <= rarity < len(_RARITIES):
        r_str = _RARITIES[rarity]
    elif str(rarity).isdigit() and 0 <= int(rarity) < len(_RARITIES):
        r_str = _RARITIES[int(rarity)]
    else:
        raw_str = str(rarity).upper()
        r_str = "RARE" if raw_str == "UNCOMMON" else raw_str
    if not use_rich:
        return f"Shady #{shady_num} [{r_str}]"
    st = get_tier_style(r_str)
    return f"[pink1]Shady #{shady_num}[/] [{st}][{r_str}][/]"


def is_valid_class_ptr(val: int | None) -> bool:
    """Check if a memory value is a valid 64-bit runtime class pointer.
    
    Valid runtime class pointers in Windows 64-bit user address space are 8-byte aligned
    and reside strictly between 0x100000000 (4GB) and 0x7FFFFFFF0000 (128TB user limit).
    This safely excludes null pointers, 32-bit IL2CPP metadata tokens (<= 0xFFFFFFFF),
    and sign-extended tokens (> 0x7FFFFFFF0000).
    """
    if not val or val < 0x100000000 or val > 0x7FFFFFFF0000:
        return False
    if val % 8 != 0:
        return False
    return True


def get_character_identity(memory: ProcessMemory, module_base: int) -> tuple[int, str] | None:
    """Read current player character ID and friendly name from PlayerStats in memory."""
    try:
        type_info = memory.read_ptr(module_base + PLAYER_STATS_TYPE_INFO_OFFSET)
        if not is_valid_class_ptr(type_info):
            return None
        static_fields = memory.read_ptr(type_info + CLASS_STATIC_FIELDS_OFFSET)
        if not static_fields or static_fields < 0x10000:
            return None
        root = memory.read_ptr(static_fields + PLAYER_STATS_ROOT_OFFSET)
        if not root or root < 0x10000:
            return None
        owner_stats = memory.read_ptr(root + OWNER_STATS_OFFSET)
        if not owner_stats or owner_stats < 0x10000:
            return None
        player_inventory = memory.read_ptr(owner_stats + PLAYER_INVENTORY_OFFSET)
        if not player_inventory or player_inventory < 0x10000:
            return None
        character_data = memory.read_ptr(player_inventory + CHARACTER_DATA_OFFSET)
        if not character_data or character_data < 0x10000:
            return None
        char_id = memory.read_i32(character_data + CHARACTER_DATA_CHARACTER_ID_OFFSET)
        if 0 <= char_id <= 100:
            char_name = CHARACTER_NAMES.get(char_id, f"Character {char_id}")
            return char_id, char_name
    except Exception:
        pass
    return None



COMPASS_16 = [
    "North", "NNE", "North-East", "ENE",
    "East", "ESE", "South-East", "SSE",
    "South", "SSW", "South-West", "WSW",
    "West", "WNW", "North-West", "NNW",
]


def get_map_sector(pos: tuple[float, float] | None, world_size: float = 600.0) -> str:
    """Return human-readable map sector (e.g. 'North-East (Top-Right)') from (X, Z) coordinates."""
    if not pos:
        return "Unknown"
    x, z = pos
    threshold = max(50.0, world_size * 0.15)

    if abs(x) <= threshold and abs(z) <= threshold:
        return "Center"

    v_part = "North" if z > threshold else ("South" if z < -threshold else "")
    h_part = "East" if x > threshold else ("West" if x < -threshold else "")

    if v_part and h_part:
        compass = f"{v_part}-{h_part}"
        visual = "Top-Right" if v_part == "North" and h_part == "East" else (
            "Top-Left" if v_part == "North" else (
                "Bottom-Right" if h_part == "East" else "Bottom-Left"
            )
        )
        return f"{compass} ({visual})"
    elif v_part:
        visual = "Top-Center" if v_part == "North" else "Bottom-Center"
        return f"{v_part} ({visual})"
    elif h_part:
        visual = "Right-Center" if h_part == "East" else "Left-Center"
        return f"{h_part} ({visual})"
    return "Center"


def get_player_relative_direction(
    player_pos: tuple[float, float] | None,
    target_pos: tuple[float, float] | None,
) -> tuple[str, int, float] | None:
    """Calculate 16-point direction, bearing angle (0-359 deg), and distance from player to target."""
    if not player_pos or not target_pos:
        return None
    px, pz = player_pos
    tx, tz = target_pos
    dx = tx - px
    dz = tz - pz
    dist = round(math.hypot(dx, dz), 1)
    angle = int(round((math.degrees(math.atan2(dx, dz)) + 360) % 360)) % 360
    idx = int((angle + 11.25) / 22.5) % 16
    return COMPASS_16[idx], angle, dist


COMPASS_8 = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def get_8_direction(
    from_pos: tuple[float, float] | None,
    target_pos: tuple[float, float] | None,
) -> str:
    """Calculate 8-point cardinal direction ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')."""
    if not target_pos:
        return "Unknown"
    fx = from_pos[0] if from_pos else 0.0
    fz = from_pos[1] if from_pos else 0.0
    tx, tz = target_pos
    dx = tx - fx
    dz = tz - fz
    angle = (math.degrees(math.atan2(dx, dz)) + 360.0) % 360.0
    idx = int((angle + 22.5) / 45.0) % 8
    return COMPASS_8[idx]


def is_shady_guy_done(
    memory: ProcessMemory,
    ptr: int,
    sg_dict: dict | None = None,
    marker_client: MapMarkerMemoryClient | None = None,
) -> bool:
    """Check if a Shady Guy interactable has been used, purchased, or destroyed."""
    if not ptr or ptr < 0x10000:
        return True

    # If already confirmed done, keep it done
    if sg_dict and sg_dict.get("done", False):
        return True

    try:
        # Fast batch read if available
        if hasattr(memory, "read_bytes"):
            hdr_buf = memory.read_bytes(ptr, 0xB8)
            if hdr_buf and len(hdr_buf) >= 0xB8:
                native_comp = struct.unpack_from("<Q", hdr_buf, NATIVE_COMP_OFFSET)[0]
                if not native_comp or native_comp < 0x10000:
                    return True
                done_shady = bool(struct.unpack_from("<B", hdr_buf, SHADY_DONE_OFFSET)[0])
                if done_shady:
                    return True
                initial_items = len(sg_dict.get("items", [])) if sg_dict else 3
                items_ptr = struct.unpack_from("<Q", hdr_buf, SHADY_ITEMS_LIST_OFFSET)[0]
                if items_ptr and items_ptr > 0x10000:
                    item_count = memory.read_i32(items_ptr + 0x18)
                    if initial_items > 0 and 0 <= item_count < initial_items:
                        return True
                if sg_dict is not None:
                    sg_dict["fail_count"] = 0
                return False

        # Fallback path for mock readers without read_bytes
        native_comp = memory.read_ptr(ptr + NATIVE_COMP_OFFSET)
        if not native_comp or native_comp < 0x10000:
            return True

        done_shady = bool(memory.read_u8(ptr + SHADY_DONE_OFFSET))
        if done_shady:
            return True

        initial_items = len(sg_dict.get("items", [])) if sg_dict else 3
        items_ptr = memory.read_ptr(ptr + SHADY_ITEMS_LIST_OFFSET)
        if items_ptr and items_ptr > 0x10000:
            item_count = memory.read_i32(items_ptr + 0x18)
            if initial_items > 0 and 0 <= item_count < initial_items:
                return True

        if marker_client and hasattr(marker_client, "activity_is_active"):
            try:
                if ptr in getattr(marker_client, "_tracked_classes", {}):
                    if not marker_client.activity_is_active(ptr):
                        return True
            except Exception:
                pass

        if sg_dict is not None:
            sg_dict["fail_count"] = 0
        return False
    except Exception:
        if sg_dict is not None:
            sg_dict["fail_count"] = sg_dict.get("fail_count", 0) + 1
            if sg_dict["fail_count"] >= 2:
                return True
        return False


def get_all_shady_items_ranked(shady_guys: list[dict]) -> list[dict]:
    """Extract and rank all individual offered items from Shady Guys by distance from spawn."""
    items_ranked = []
    for rank, sg in enumerate(shady_guys, 1):
        dist = sg.get("dist")
        rel = sg.get("rel_dir")
        dist_val = dist if dist is not None else 999999.0
        sec = sg.get("map_sector") or "Unknown"
        prices = sg.get("gold_prices", [])
        mults = sg.get("multipliers", [])
        is_done = bool(sg.get("done", False))
        shady_num = sg.get("shady_num", rank)
        for it_idx, it in enumerate(sg.get("items", [])):
            item_id = it.get("item_id")
            name = it.get("item_name") or get_item_name(item_id if item_id is not None else -1)
            gold = prices[it_idx] if it_idx < len(prices) else None
            mult = mults[it_idx] if it_idx < len(mults) else None
            items_ranked.append({
                "shady_rank": rank,
                "shady_num": shady_num,
                "shady_rarity": sg.get("rarity", "COMMON"),
                "shady_done": is_done,
                "slot": it_idx + 1,
                "item_id": item_id,
                "item_name": name,
                "gold": gold,
                "multiplier": mult,
                "dist": dist,
                "dist_val": dist_val,
                "direction": rel[0] if rel else None,
                "bearing_deg": rel[1] if rel else None,
                "rel_str": f"{rel[2]}m {rel[0]}" if rel else (f"{dist}m" if dist is not None else "-"),
                "bearing_str": f"({rel[1]}°)" if (rel and rel[1] is not None) else "",
                "map_sector": sec,
            })
    items_ranked.sort(key=lambda x: (x["dist_val"], x["slot"]))
    return items_ranked


def decode_il2cpp_list_items(memory: ProcessMemory, list_ptr: int) -> list[dict]:
    """Decode a C# List<T>, supporting both reference types (ItemData) and value types (enums)."""
    items = []
    if not list_ptr or list_ptr < 0x10000:
        return items
    try:
        items_array = memory.read_ptr(list_ptr + 0x10)
        size = memory.read_i32(list_ptr + 0x18)

        if size <= 0 or size > 32 or not items_array or items_array < 0x10000:
            return items

        # Fast batch read if read_bytes is available
        if hasattr(memory, "read_bytes"):
            data_len = 0x20 + (size * 8)
            arr_buf = memory.read_bytes(items_array, data_len)
            if arr_buf and len(arr_buf) >= data_len:
                elem_ptrs = struct.unpack_from(f"<{size}Q", arr_buf, 0x20)
                elem_i32s = struct.unpack_from(f"<{size}i", arr_buf, 0x20)

                for i in range(size):
                    elem_ptr = elem_ptrs[i]
                    elem_i32 = elem_i32s[i]

                    item_info = {
                        "index": i,
                        "raw_ptr": elem_ptr,
                        "raw_i32": elem_i32,
                    }

                    if elem_ptr > 0x10000:
                        try:
                            enum_val = memory.read_i32(elem_ptr + ITEM_DATA_ENUM_OFFSET)
                            if 0 <= enum_val <= 100:
                                item_info["item_id"] = enum_val
                                item_info["item_name"] = get_item_name(enum_val)
                        except Exception:
                            pass

                    if "item_name" not in item_info and 0 <= elem_i32 <= 90 and elem_i32 in ITEM_ENUM_NAMES_BY_ID:
                        item_info["item_id"] = elem_i32
                        item_info["item_name"] = get_item_name(elem_i32)

                    items.append(item_info)
                return items

        # Fallback individual reads
        for i in range(size):
            elem_ptr = memory.read_ptr(items_array + 0x20 + (i * 8))
            elem_i32 = memory.read_i32(items_array + 0x20 + (i * 4))

            item_info = {
                "index": i,
                "raw_ptr": elem_ptr,
                "raw_i32": elem_i32,
            }

            if elem_ptr > 0x10000:
                try:
                    enum_val = memory.read_i32(elem_ptr + ITEM_DATA_ENUM_OFFSET)
                    if 0 <= enum_val <= 100:
                        item_info["item_id"] = enum_val
                        item_info["item_name"] = get_item_name(enum_val)
                except Exception:
                    pass

            if "item_name" not in item_info and 0 <= elem_i32 <= 90 and elem_i32 in ITEM_ENUM_NAMES_BY_ID:
                item_info["item_id"] = elem_i32
                item_info["item_name"] = get_item_name(elem_i32)

            items.append(item_info)
    except Exception as exc:
        items.append({"error": str(exc)})
    return items


def decode_float_array(memory: ProcessMemory, array_ptr: int) -> list[float]:
    values = []
    if not array_ptr or array_ptr < 0x10000:
        return values
    try:
        length = memory.read_i32(array_ptr + 0x18)
        if 0 < length <= 32:
            if hasattr(memory, "read_bytes"):
                req_bytes = 0x20 + length * 4
                buf = memory.read_bytes(array_ptr, req_bytes)
                if buf and len(buf) >= req_bytes:
                    raw_floats = struct.unpack_from(f"<{length}f", buf, 0x20)
                    return [round(v, 2) for v in raw_floats]
            for i in range(length):
                val = memory.read_float(array_ptr + 0x20 + (i * 4))
                values.append(round(val, 2))
    except Exception:
        pass
    return values


def decode_il2cpp_int_list(memory: ProcessMemory, list_ptr: int) -> list[int]:
    """Decode a C# List<int> (such as Shady Guy gold prices)."""
    values = []
    if not list_ptr or list_ptr < 0x10000:
        return values
    try:
        items_array = memory.read_ptr(list_ptr + 0x10)
        size = memory.read_i32(list_ptr + 0x18)
        if 0 < size <= 32 and items_array and items_array >= 0x10000:
            if hasattr(memory, "read_bytes"):
                req_bytes = 0x20 + size * 4
                buf = memory.read_bytes(items_array, req_bytes)
                if buf and len(buf) >= req_bytes:
                    return list(struct.unpack_from(f"<{size}i", buf, 0x20))
            for i in range(size):
                val = memory.read_i32(items_array + 0x20 + (i * 4))
                values.append(val)
    except Exception:
        pass
    return values







def get_stage_index(memory: ProcessMemory, module_base: int) -> int:
    try:
        type_info = memory.read_ptr(module_base + MAP_CONTROLLER_TYPE_INFO_OFFSET)
        if type_info:
            static_fields = memory.read_ptr(type_info + CLASS_STATIC_FIELDS_OFFSET)
            if static_fields:
                return memory.read_i32(static_fields + MAP_CONTROLLER_STAGE_INDEX_OFFSET)
    except Exception:
        pass
    return -1


def get_map_interactable_counts(
    memory: ProcessMemory,
    game_client: GameDataClient | None = None,
) -> dict[str, int]:
    """Read total spawned map interactable counts via GameDataClient with retry."""
    gdc = game_client or GameDataClient(memory=memory)
    for _ in range(5):
        try:
            activities = gdc.get_map_activity_values()
            if activities:
                def get_max(key: str) -> int:
                    sv = activities.get(key)
                    return sv.max if sv else 0

                return {
                    "shady": get_max("Shady Guy"),
                    "moai": get_max("Moais"),
                    "microwaves": get_max("Microwaves"),
                    "boss_curses": get_max("Boss Curses"),
                    "magnets": get_max("Magnet Shrines") or get_max("Magnet Curses"),
                }
        except Exception:
            time.sleep(0.015)

    return {
        "shady": 0,
        "moai": 0,
        "microwaves": 0,
        "boss_curses": 0,
        "magnets": 0,
    }


_TYPE_INFO_CACHE: dict[int, int] = {}


def scan_heap_interactables(
    memory: ProcessMemory,
    module_base: int,
    marker_client: MapMarkerMemoryClient | None = None,
    target_shady: int = 0,
    target_micro: int = 0,
    target_moai: int = 0,
    target_boss: int = 0,
    max_scan_attempts: int = 5,
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Scan committed GC heap memory regions for Shady Guy, Microwave, Moai, and Boss Curse instances.

    Uses NumPy AVX2 SIMD scanning if available, with automatic multi-pass retry
    and fallback for maximum speed and zero race conditions during live scene loading.
    """
    def _get_type_info(offset: int) -> int | None:
        cached = _TYPE_INFO_CACHE.get(offset)
        if cached is not None and is_valid_class_ptr(cached):
            return cached
        raw = memory.read_ptr(module_base + offset)
        if is_valid_class_ptr(raw):
            _TYPE_INFO_CACHE[offset] = raw
            return raw
        return None

    shady_class_ptr = _get_type_info(SHADY_GUY_TYPE_INFO_OFFSET)
    needle = shady_class_ptr.to_bytes(8, "little") if shady_class_ptr else None

    micro_class_ptr = _get_type_info(MICROWAVE_TYPE_INFO_OFFSET)
    micro_needle = micro_class_ptr.to_bytes(8, "little") if micro_class_ptr else None

    moai_class_ptr = _get_type_info(MOAI_TYPE_INFO_OFFSET)
    moai_needle = moai_class_ptr.to_bytes(8, "little") if moai_class_ptr else None

    boss_class_ptr = _get_type_info(BOSS_CURSE_TYPE_INFO_OFFSET)
    boss_needle = boss_class_ptr.to_bytes(8, "little") if boss_class_ptr else None

    handle = getattr(memory._pm, "process_handle", None)
    if not handle:
        return [], [], [], []

    max_buf_size = 50 * 1024 * 1024
    read_buf = (ctypes.c_char * max_buf_size)()
    bytes_read_val = ctypes.c_size_t()
    rpm = ctypes.windll.kernel32.ReadProcessMemory
    vq = ctypes.windll.kernel32.VirtualQueryEx

    mbi = MEMORY_BASIC_INFORMATION()
    max_addr = 0x7FFFFFFF0000

    shady_guys: list[dict] = []
    microwaves: list[dict] = []
    moais: list[dict] = []
    boss_curses: list[dict] = []
    seen_addresses: set[int] = set()

    # Get world size if available
    world_size = 600.0
    if marker_client:
        try:
            full_map = marker_client._resolve_full_map()
            if full_map:
                ws = memory.read_float(full_map + marker_client.FULL_MAP_WORLD_SIZE_OFFSET)
                if ws and math.isfinite(ws) and ws > 0:
                    world_size = float(ws)
        except Exception:
            pass

    for attempt in range(max_scan_attempts):
        if attempt > 0:
            time.sleep(0.06)

        # Refresh any TypeInfo pointers that were not initialized yet
        if not is_valid_class_ptr(shady_class_ptr):
            shady_class_ptr = _get_type_info(SHADY_GUY_TYPE_INFO_OFFSET)
            if shady_class_ptr:
                needle = shady_class_ptr.to_bytes(8, "little")
        if not is_valid_class_ptr(micro_class_ptr):
            micro_class_ptr = _get_type_info(MICROWAVE_TYPE_INFO_OFFSET)
            if micro_class_ptr:
                micro_needle = micro_class_ptr.to_bytes(8, "little")
        if not is_valid_class_ptr(moai_class_ptr):
            moai_class_ptr = _get_type_info(MOAI_TYPE_INFO_OFFSET)
            if moai_class_ptr:
                moai_needle = moai_class_ptr.to_bytes(8, "little")
        if not is_valid_class_ptr(boss_class_ptr):
            boss_class_ptr = _get_type_info(BOSS_CURSE_TYPE_INFO_OFFSET)
            if boss_class_ptr:
                boss_needle = boss_class_ptr.to_bytes(8, "little")

        addr = 0x10000
        while addr < max_addr:
            need_shady = (shady_class_ptr is not None) and (target_shady <= 0 or len(shady_guys) < target_shady)
            need_micro = (micro_class_ptr is not None) and (target_micro <= 0 or len(microwaves) < target_micro)
            need_moai = (moai_class_ptr is not None) and (target_moai <= 0 or len(moais) < target_moai)
            need_boss = (boss_class_ptr is not None) and (target_boss <= 0 or len(boss_curses) < target_boss)

            if not (need_shady or need_micro or need_moai or need_boss):
                break

            res = vq(
                handle,
                ctypes.c_void_p(addr),
                ctypes.byref(mbi),
                ctypes.sizeof(mbi),
            )
            if not res:
                break

            region_base = mbi.BaseAddress or addr
            size = mbi.RegionSize

            # Scan committed private PAGE_READWRITE memory regions (GC heap chunks)
            if mbi.State == MEM_COMMIT and mbi.Type == MEM_PRIVATE and mbi.Protect == 0x04:
                if size <= max_buf_size:
                    try:
                        if rpm(handle, ctypes.c_void_p(region_base), read_buf, size, ctypes.byref(bytes_read_val)):
                            n_bytes = bytes_read_val.value
                            n_words = n_bytes // 8
                            if n_words > 0:
                                if np is not None:
                                    # Ultra-fast SIMD AVX2 search with NumPy (10+ GB/s)
                                    arr = np.frombuffer(read_buf, dtype=np.uint64, count=n_words)
                                    if need_shady:
                                        s_indices = np.where(arr == shady_class_ptr)[0]
                                        for idx in s_indices:
                                            cand = region_base + int(idx) * 8
                                            if cand not in seen_addresses:
                                                try:
                                                    cand_buf = memory.read_bytes(cand, 0xC0) if hasattr(memory, "read_bytes") else None
                                                    if cand_buf and len(cand_buf) >= 0xC0:
                                                        native_comp = struct.unpack_from("<Q", cand_buf, 0x10)[0]
                                                        if not native_comp or native_comp < 0x10000:
                                                            continue
                                                        multipliers_ptr = struct.unpack_from("<Q", cand_buf, SHADY_PRICES_ARRAY_OFFSET)[0]
                                                        items_ptr = struct.unpack_from("<Q", cand_buf, SHADY_ITEMS_LIST_OFFSET)[0]
                                                        rarity = struct.unpack_from("<i", cand_buf, SHADY_RARITY_OFFSET)[0]
                                                        done_shady = struct.unpack_from("<B", cand_buf, SHADY_DONE_OFFSET)[0]
                                                        gold_prices_ptr = struct.unpack_from("<Q", cand_buf, SHADY_SECONDARY_LIST_OFFSET)[0]
                                                        is_done = bool(done_shady)
                                                    else:
                                                        native_comp = memory.read_ptr(cand + 0x10)
                                                        if not native_comp or native_comp < 0x10000:
                                                            continue
                                                        items_ptr = memory.read_ptr(cand + SHADY_ITEMS_LIST_OFFSET)
                                                        rarity = memory.read_i32(cand + SHADY_RARITY_OFFSET)
                                                        done_shady = memory.read_u8(cand + SHADY_DONE_OFFSET)
                                                        is_done = bool(done_shady)
                                                        gold_prices_ptr = memory.read_ptr(cand + SHADY_SECONDARY_LIST_OFFSET)
                                                        multipliers_ptr = memory.read_ptr(cand + SHADY_PRICES_ARRAY_OFFSET)

                                                    if items_ptr > 0x10000 and 0 <= rarity <= 4:
                                                        items = decode_il2cpp_list_items(memory, items_ptr)
                                                        if not items:
                                                            continue
                                                        seen_addresses.add(cand)
                                                        gold_prices = decode_il2cpp_int_list(memory, gold_prices_ptr)
                                                        multipliers = decode_float_array(memory, multipliers_ptr)

                                                        world_pos = None
                                                        distance = None
                                                        map_sector = None
                                                        rel_dir = None
                                                        if marker_client:
                                                            try:
                                                                s_trans = marker_client._component_transform(cand)
                                                                sx, _, sz = marker_client._transform_point(
                                                                    s_trans, (0.0, 0.0, 0.0)
                                                                )
                                                                world_pos = (round(sx, 1), round(sz, 1))
                                                                map_sector = get_map_sector(world_pos, world_size)
                                                                distance = round(math.hypot(sx, sz), 1)
                                                                rel_dir = get_player_relative_direction((0.0, 0.0), (sx, sz))
                                                            except Exception:
                                                                pass

                                                        shady_guys.append(
                                                            {
                                                                "ptr": cand,
                                                                "rarity": _RARITIES[rarity]
                                                                if 0 <= rarity < len(_RARITIES)
                                                                else f"Tier {rarity}",
                                                                "done": is_done,
                                                                "items": items,
                                                                "gold_prices": gold_prices,
                                                                "multipliers": multipliers,
                                                                "pos": world_pos,
                                                                "dist": distance,
                                                                "map_sector": map_sector,
                                                                "rel_dir": rel_dir,
                                                            }
                                                        )
                                                except Exception:
                                                    pass

                                    if need_micro:
                                        m_indices = np.where(arr == micro_class_ptr)[0]
                                        for idx in m_indices:
                                            cand = region_base + int(idx) * 8
                                            if cand not in seen_addresses:
                                                try:
                                                    cand_buf = memory.read_bytes(cand, 0x90) if hasattr(memory, "read_bytes") else None
                                                    if cand_buf and len(cand_buf) >= 0x90:
                                                        native_comp = struct.unpack_from("<Q", cand_buf, 0x10)[0]
                                                        if not native_comp or native_comp < 0x10000:
                                                            continue
                                                        rarity, uses = struct.unpack_from("<ii", cand_buf, MICROWAVE_RARITY_OFFSET)
                                                    else:
                                                        native_comp = memory.read_ptr(cand + 0x10)
                                                        if not native_comp or native_comp < 0x10000:
                                                            continue
                                                        rarity = memory.read_i32(cand + MICROWAVE_RARITY_OFFSET)
                                                        uses = memory.read_i32(cand + MICROWAVE_USES_LEFT_OFFSET)

                                                    if uses > 0 and 0 <= rarity <= 4:
                                                        seen_addresses.add(cand)
                                                        world_pos = None
                                                        distance = None
                                                        map_sector = None
                                                        rel_dir = None
                                                        if marker_client:
                                                            try:
                                                                m_trans = marker_client._component_transform(cand)
                                                                mx, _, mz = marker_client._transform_point(
                                                                    m_trans, (0.0, 0.0, 0.0)
                                                                )
                                                                world_pos = (round(mx, 1), round(mz, 1))
                                                                map_sector = get_map_sector(world_pos, world_size)
                                                                distance = round(math.hypot(mx, mz), 1)
                                                                rel_dir = get_player_relative_direction((0.0, 0.0), (mx, mz))
                                                            except Exception:
                                                                pass
                                                        c_info = MICROWAVE_COLORS.get(rarity, ("White", "white", "bright_white"))
                                                        microwaves.append(
                                                            {
                                                                "ptr": cand,
                                                                "rarity": rarity,
                                                                "color": c_info[0],
                                                                "style": c_info[2],
                                                                "uses_left": uses,
                                                                "pos": world_pos,
                                                                "dist": distance,
                                                                "map_sector": map_sector,
                                                                "rel_dir": rel_dir,
                                                            }
                                                        )
                                                except Exception:
                                                    pass

                                    if need_moai:
                                        moai_indices = np.where(arr == moai_class_ptr)[0]
                                        for idx in moai_indices:
                                            cand = region_base + int(idx) * 8
                                            if cand not in seen_addresses:
                                                try:
                                                    native_comp = memory.read_ptr(cand + 0x10)
                                                    if native_comp and native_comp > 0x10000:
                                                        world_pos = None
                                                        distance = None
                                                        rel_dir_8 = None
                                                        if marker_client:
                                                            try:
                                                                m_trans = marker_client._component_transform(cand)
                                                                mx, _, mz = marker_client._transform_point(
                                                                    m_trans, (0.0, 0.0, 0.0)
                                                                )
                                                                world_pos = (round(mx, 1), round(mz, 1))
                                                                rel_dir_8 = get_8_direction((0.0, 0.0), (mx, mz))
                                                                distance = round(math.hypot(mx, mz), 1)
                                                            except Exception:
                                                                pass
                                                        if world_pos is not None:
                                                            seen_addresses.add(cand)
                                                            moais.append(
                                                                {
                                                                    "ptr": cand,
                                                                    "pos": world_pos,
                                                                    "dist": distance,
                                                                    "dir": rel_dir_8 or "Unknown",
                                                                }
                                                            )
                                                except Exception:
                                                    pass

                                    if need_boss:
                                        boss_indices = np.where(arr == boss_class_ptr)[0]
                                        for idx in boss_indices:
                                            cand = region_base + int(idx) * 8
                                            if cand not in seen_addresses:
                                                try:
                                                    native_comp = memory.read_ptr(cand + 0x10)
                                                    if native_comp and native_comp > 0x10000:
                                                        world_pos = None
                                                        distance = None
                                                        rel_dir_8 = None
                                                        if marker_client:
                                                            try:
                                                                b_trans = marker_client._component_transform(cand)
                                                                bx, _, bz = marker_client._transform_point(
                                                                    b_trans, (0.0, 0.0, 0.0)
                                                                )
                                                                world_pos = (round(bx, 1), round(bz, 1))
                                                                rel_dir_8 = get_8_direction((0.0, 0.0), (bx, bz))
                                                                distance = round(math.hypot(bx, bz), 1)
                                                            except Exception:
                                                                pass
                                                        if world_pos is not None:
                                                            seen_addresses.add(cand)
                                                            boss_curses.append(
                                                                {
                                                                    "ptr": cand,
                                                                    "pos": world_pos,
                                                                    "dist": distance,
                                                                    "dir": rel_dir_8 or "Unknown",
                                                                }
                                                            )
                                                except Exception:
                                                    pass
                                else:
                                    # Fallback if numpy is not installed
                                    data = bytes(read_buf[:n_bytes])
                                    if need_shady and needle and needle in data:
                                        pos = 0
                                        while True:
                                            idx = data.find(needle, pos)
                                            if idx == -1: break
                                            if idx % 8 == 0:
                                                cand = region_base + idx
                                                if cand not in seen_addresses:
                                                    try:
                                                        native_comp = memory.read_ptr(cand + 0x10)
                                                        if native_comp and native_comp > 0x10000:
                                                            items_ptr = memory.read_ptr(cand + SHADY_ITEMS_LIST_OFFSET)
                                                            if items_ptr > 0x10000:
                                                                rarity = memory.read_i32(cand + SHADY_RARITY_OFFSET)
                                                                done_shady = memory.read_u8(cand + SHADY_DONE_OFFSET)
                                                                is_done = bool(done_shady)
                                                                if 0 <= rarity <= 4:
                                                                    items = decode_il2cpp_list_items(memory, items_ptr)
                                                                    if not items:
                                                                        pos = idx + 8
                                                                        continue
                                                                    seen_addresses.add(cand)
                                                                    gold_prices = decode_il2cpp_int_list(
                                                                        memory, memory.read_ptr(cand + SHADY_SECONDARY_LIST_OFFSET)
                                                                    )
                                                                    multipliers = decode_float_array(
                                                                        memory, memory.read_ptr(cand + SHADY_PRICES_ARRAY_OFFSET)
                                                                    )
                                                                    world_pos = None
                                                                    distance = None
                                                                    map_sector = None
                                                                    rel_dir = None
                                                                    if marker_client:
                                                                        try:
                                                                            s_trans = marker_client._component_transform(cand)
                                                                            sx, _, sz = marker_client._transform_point(s_trans, (0.0, 0.0, 0.0))
                                                                            world_pos = (round(sx, 1), round(sz, 1))
                                                                            map_sector = get_map_sector(world_pos, world_size)
                                                                            distance = round(math.hypot(sx, sz), 1)
                                                                            rel_dir = get_player_relative_direction((0.0, 0.0), (sx, sz))
                                                                        except Exception:
                                                                            pass
                                                                    shady_guys.append({
                                                                        "ptr": cand,
                                                                        "rarity": _RARITIES[rarity] if 0 <= rarity < len(_RARITIES) else f"Tier {rarity}",
                                                                        "done": is_done,
                                                                        "items": items,
                                                                        "gold_prices": gold_prices,
                                                                        "multipliers": multipliers,
                                                                        "pos": world_pos,
                                                                        "dist": distance,
                                                                        "map_sector": map_sector,
                                                                        "rel_dir": rel_dir,
                                                                    })
                                                    except Exception:
                                                        pass
                                            pos = idx + 8

                                    if need_micro and micro_needle and micro_needle in data:
                                        pos = 0
                                        while True:
                                            idx = data.find(micro_needle, pos)
                                            if idx == -1: break
                                            if idx % 8 == 0:
                                                cand = region_base + idx
                                                if cand not in seen_addresses:
                                                    try:
                                                        native_comp = memory.read_ptr(cand + 0x10)
                                                        if native_comp and native_comp > 0x10000:
                                                            rarity = memory.read_i32(cand + MICROWAVE_RARITY_OFFSET)
                                                            uses = memory.read_i32(cand + MICROWAVE_USES_LEFT_OFFSET)
                                                            if uses > 0 and 0 <= rarity <= 4:
                                                                seen_addresses.add(cand)
                                                                world_pos = None
                                                                distance = None
                                                                map_sector = None
                                                                rel_dir = None
                                                                if marker_client:
                                                                    try:
                                                                        m_trans = marker_client._component_transform(cand)
                                                                        mx, _, mz = marker_client._transform_point(
                                                                            m_trans, (0.0, 0.0, 0.0)
                                                                        )
                                                                        world_pos = (round(mx, 1), round(mz, 1))
                                                                        map_sector = get_map_sector(world_pos, world_size)
                                                                        distance = round(math.hypot(mx, mz), 1)
                                                                        rel_dir = get_player_relative_direction((0.0, 0.0), (mx, mz))
                                                                    except Exception:
                                                                        pass
                                                                c_info = MICROWAVE_COLORS.get(rarity, ("White", "white", "bright_white"))
                                                                microwaves.append({
                                                                    "ptr": cand,
                                                                    "rarity": rarity,
                                                                    "color": c_info[0],
                                                                    "style": c_info[2],
                                                                    "uses_left": uses,
                                                                    "pos": world_pos,
                                                                    "dist": distance,
                                                                    "map_sector": map_sector,
                                                                    "rel_dir": rel_dir,
                                                                })
                                                    except Exception:
                                                        pass
                                            pos = idx + 8

                                    if need_moai and moai_needle and moai_needle in data:
                                        pos = 0
                                        while True:
                                            idx = data.find(moai_needle, pos)
                                            if idx == -1: break
                                            if idx % 8 == 0:
                                                cand = region_base + idx
                                                if cand not in seen_addresses:
                                                    try:
                                                        native_comp = memory.read_ptr(cand + 0x10)
                                                        if native_comp and native_comp > 0x10000:
                                                            world_pos = None
                                                            distance = None
                                                            rel_dir_8 = None
                                                            if marker_client:
                                                                try:
                                                                    m_trans = marker_client._component_transform(cand)
                                                                    mx, _, mz = marker_client._transform_point(
                                                                        m_trans, (0.0, 0.0, 0.0)
                                                                    )
                                                                    world_pos = (round(mx, 1), round(mz, 1))
                                                                    rel_dir_8 = get_8_direction((0.0, 0.0), (mx, mz))
                                                                    distance = round(math.hypot(mx, mz), 1)
                                                                except Exception:
                                                                    pass
                                                            if world_pos is not None:
                                                                seen_addresses.add(cand)
                                                                moais.append(
                                                                    {
                                                                        "ptr": cand,
                                                                        "pos": world_pos,
                                                                        "dist": distance,
                                                                        "dir": rel_dir_8 or "Unknown",
                                                                    }
                                                                )
                                                    except Exception:
                                                        pass
                                            pos = idx + 8

                                    if need_boss and boss_needle and boss_needle in data:
                                        pos = 0
                                        while True:
                                            idx = data.find(boss_needle, pos)
                                            if idx == -1: break
                                            if idx % 8 == 0:
                                                cand = region_base + idx
                                                if cand not in seen_addresses:
                                                    try:
                                                        native_comp = memory.read_ptr(cand + 0x10)
                                                        if native_comp and native_comp > 0x10000:
                                                            world_pos = None
                                                            distance = None
                                                            rel_dir_8 = None
                                                            if marker_client:
                                                                try:
                                                                    b_trans = marker_client._component_transform(cand)
                                                                    bx, _, bz = marker_client._transform_point(
                                                                        b_trans, (0.0, 0.0, 0.0)
                                                                    )
                                                                    world_pos = (round(bx, 1), round(bz, 1))
                                                                    rel_dir_8 = get_8_direction((0.0, 0.0), (bx, bz))
                                                                    distance = round(math.hypot(bx, bz), 1)
                                                                except Exception:
                                                                    pass
                                                            if world_pos is not None:
                                                                seen_addresses.add(cand)
                                                                boss_curses.append(
                                                                    {
                                                                        "ptr": cand,
                                                                        "pos": world_pos,
                                                                        "dist": distance,
                                                                        "dir": rel_dir_8 or "Unknown",
                                                                    }
                                                                )
                                                    except Exception:
                                                        pass
                                            pos = idx + 8

                                # Early termination within pass if all targets found
                                all_shady_found = target_shady <= 0 or len(shady_guys) >= target_shady
                                all_micro_found = target_micro <= 0 or len(microwaves) >= target_micro
                                all_moai_found = target_moai <= 0 or len(moais) >= target_moai
                                all_boss_found = target_boss <= 0 or len(boss_curses) >= target_boss
                                if all_shady_found and all_micro_found and all_moai_found and all_boss_found:
                                    break
                    except Exception:
                        pass

            addr = region_base + size

        # Early termination across attempts if all targets found
        all_shady_found = target_shady <= 0 or len(shady_guys) >= target_shady
        all_micro_found = target_micro <= 0 or len(microwaves) >= target_micro
        all_moai_found = target_moai <= 0 or len(moais) >= target_moai
        all_boss_found = target_boss <= 0 or len(boss_curses) >= target_boss
        if all_shady_found and all_micro_found and all_moai_found and all_boss_found:
            break

    # Keep only active Moais and Boss Curses with valid world coordinates
    moais = [mo for mo in moais if mo.get("pos") is not None]
    boss_curses = [b for b in boss_curses if b.get("pos") is not None]

    # Keep only genuine Shady Guys with decoded items; drop extra ghost instances without position
    shady_guys = [sg for sg in shady_guys if sg.get("items")]
    if target_shady > 0 and len(shady_guys) > target_shady:
        with_pos = [sg for sg in shady_guys if sg.get("pos") is not None]
        if len(with_pos) >= target_shady:
            shady_guys = with_pos[:target_shady]

    # Calculate distance and direction from spawn (0.0, 0.0)
    for sg in shady_guys:
        if sg.get("pos"):
            sx, sz = sg["pos"]
            if sg.get("dist") is None:
                sg["dist"] = round(math.hypot(sx, sz), 1)
            if not sg.get("rel_dir"):
                sg["rel_dir"] = get_player_relative_direction((0.0, 0.0), (sx, sz))
    for m in microwaves:
        if m.get("pos"):
            mx, mz = m["pos"]
            if m.get("dist") is None:
                m["dist"] = round(math.hypot(mx, mz), 1)
            if not m.get("rel_dir"):
                m["rel_dir"] = get_player_relative_direction((0.0, 0.0), (mx, mz))
    for mo in moais:
        if mo.get("pos"):
            mx, mz = mo["pos"]
            if mo.get("dist") is None:
                mo["dist"] = round(math.hypot(mx, mz), 1)
            if not mo.get("dir") or mo.get("dir") == "Unknown":
                mo["dir"] = get_8_direction((0.0, 0.0), (mx, mz)) or "Unknown"
    for b in boss_curses:
        if b.get("pos"):
            bx, bz = b["pos"]
            if b.get("dist") is None:
                b["dist"] = round(math.hypot(bx, bz), 1)
            if not b.get("dir") or b.get("dir") == "Unknown":
                b["dir"] = get_8_direction((0.0, 0.0), (bx, bz)) or "Unknown"

    # Sort Shady Guys, Microwaves, Moais, and Boss Curses by proximity to player/spawn (closest first)
    shady_guys.sort(key=lambda s: s.get("dist") if s.get("dist") is not None else 999999.0)
    for idx, sg in enumerate(shady_guys, 1):
        sg["shady_num"] = idx
    microwaves.sort(key=lambda m: m.get("dist") if m.get("dist") is not None else 999999.0)
    moais.sort(key=lambda m: m.get("dist") if m.get("dist") is not None else 999999.0)
    boss_curses.sort(key=lambda b: b.get("dist") if b.get("dist") is not None else 999999.0)

    return shady_guys, microwaves, moais, boss_curses


def evaluate_target_item_matches(
    shady_guys: list[dict],
) -> list[dict]:
    """Find tracked target items in Shady Guy inventories.

    Returns list of target match info dictionaries.
    """
    target_matches = []
    for i, sg in enumerate(shady_guys):
        prices = sg.get("gold_prices", [])
        mults = sg.get("multipliers", [])
        for it in sg.get("items", []):
            item_id = it.get("item_id")
            if item_id in TARGET_SHADY_ITEMS:
                idx = it.get("index", 0)
                rel = sg.get("rel_dir")
                match_info = {
                    "shady_num": i + 1,
                    "shady": sg,
                    "slot": idx + 1,
                    "item_id": item_id,
                    "item_name": TARGET_SHADY_ITEMS[item_id],
                    "gold": prices[idx] if idx < len(prices) else None,
                    "multiplier": mults[idx] if idx < len(mults) else None,
                    "map_sector": sg.get("map_sector"),
                    "pos": sg.get("pos"),
                    "dist": sg.get("dist"),
                    "direction": rel[0] if rel else None,
                    "bearing_deg": rel[1] if rel else None,
                }
                target_matches.append(match_info)

    return target_matches


def can_satisfy_required_items_on_distinct_shadys(
    shady_guys: list[dict],
    req_all: list[int],
    req_any: list[int],
) -> tuple[bool, bool, bool]:
    """Check if all REQUIRED_ALL items and at least one REQUIRED_ANY item can be obtained on distinct Shady Guys.

    Because a Shady Guy disappears after a single item purchase, each must-have item
    in req_all and the selected any-of item in req_any must come from separate vendors.

    Returns:
        (all_passed, any_passed, satisfied)
    """
    req_all = list(req_all) if req_all else []
    req_any = list(req_any) if req_any else []

    if not req_all and not req_any:
        return True, True, True

    shady_item_sets = []
    for sg in (shady_guys or []):
        s_items = {it.get("item_id") for it in sg.get("items", []) if it.get("item_id") is not None}
        shady_item_sets.append(s_items)

    num_shadys = len(shady_item_sets)
    min_needed = len(req_all) + (1 if req_any else 0)

    def match_all_only(items: list[int], used: set[int]) -> bool:
        if not items:
            return True
        tgt, rest = items[0], items[1:]
        for idx in range(num_shadys):
            if idx not in used and tgt in shady_item_sets[idx]:
                used.add(idx)
                if match_all_only(rest, used):
                    return True
                used.remove(idx)
        return False

    can_all_only = match_all_only(req_all, set()) if req_all else True
    can_any_only = any(any(item in s for item in req_any) for s in shady_item_sets) if req_any else True

    if num_shadys < min_needed:
        return can_all_only, can_any_only, False

    if not req_all:
        return True, can_any_only, can_any_only
    if not req_any:
        return can_all_only, True, can_all_only

    def match_all_and_any(items: list[int], used: set[int]) -> bool:
        if not items:
            for idx in range(num_shadys):
                if idx not in used and any(item in shady_item_sets[idx] for item in req_any):
                    return True
            return False
        tgt, rest = items[0], items[1:]
        for idx in range(num_shadys):
            if idx not in used and tgt in shady_item_sets[idx]:
                used.add(idx)
                if match_all_and_any(rest, used):
                    return True
                used.remove(idx)
        return False

    satisfied = match_all_and_any(req_all, set())
    if satisfied:
        return True, True, True

    return can_all_only, can_any_only, False


def evaluate_stage1_criteria(
    sm_pass: bool,
    micro_pass: bool,
    boss_pass: bool,
    magnet_pass: bool,
    shady_pass: bool,
    required_all_item_ids: list[int] | None = None,
    required_any_item_ids: list[int] | None = None,
    offered_item_ids: set[int] | list[int] | None = None,
    has_white_micro: bool = True,
    is_fox: bool = False,
    shady_guys: list[dict] | None = None,
    **kwargs: Any,
) -> tuple[bool, bool, bool, bool, str]:
    """Pure logic to evaluate shrine thresholds and required items filter (AND / OR lists).

    Returns:
        (target_items_pass, thresholds_matched, target_only_matched, all_matched, match_reason)
    """
    thresholds_pass = sm_pass and micro_pass and boss_pass and magnet_pass and shady_pass

    # Resolve required item lists
    if (required_all_item_ids is not None) or (required_any_item_ids is not None):
        req_all = list(required_all_item_ids or [])
        req_any = list(required_any_item_ids or [])
    else:
        req_all = list(REQUIRED_ALL_ITEM_IDS) if REQUIRED_ALL_ITEM_IDS else []
        req_any = list(REQUIRED_ANY_ITEM_IDS) if REQUIRED_ANY_ITEM_IDS else []

    # Resolve offered items set
    if offered_item_ids is not None:
        present_set = set(offered_item_ids)
    elif shady_guys is not None or kwargs.get("shady_guys") is not None:
        sg_source = shady_guys if shady_guys is not None else kwargs.get("shady_guys")
        present_set = set()
        for sg in (sg_source or []):
            for it in sg.get("items", []):
                it_id = it.get("item_id")
                if it_id is not None:
                    present_set.add(it_id)
    else:
        present_set = set()
        if kwargs.get("has_anvil"):
            present_set.add(41)
        if kwargs.get("has_soul_harvester"):
            present_set.add(47)

    has_mandatory = bool(req_all) or bool(req_any)

    sg_list = shady_guys if shady_guys is not None else kwargs.get("shady_guys")
    if sg_list is not None and has_mandatory:
        distinct_all, distinct_any, distinct_satisfied = can_satisfy_required_items_on_distinct_shadys(
            sg_list, req_all, req_any
        )
        pool_all = all(item_id in present_set for item_id in req_all) if req_all else True
        pool_any = any(item_id in present_set for item_id in req_any) if req_any else True
        is_shady_conflict = (pool_all and pool_any) and not distinct_satisfied
        all_passed = distinct_all
        any_passed = distinct_any
        required_items_satisfied = distinct_satisfied
    else:
        all_passed = all(item_id in present_set for item_id in req_all) if req_all else True
        any_passed = any(item_id in present_set for item_id in req_any) if req_any else True
        required_items_satisfied = all_passed and any_passed
        is_shady_conflict = False

    if has_mandatory:
        if not required_items_satisfied:
            target_items_pass = False
            thresholds_matched = False
            target_only_matched = False
            all_matched = False
            if is_shady_conflict:
                match_reason = "REQUIRED_ITEMS_CONFLICT_SAME_SHADY"
            else:
                match_reason = "MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS" if thresholds_pass else "MISSING_REQUIRED_ITEMS"
        elif not thresholds_pass:
            target_items_pass = True
            thresholds_matched = False
            target_only_matched = False
            all_matched = False
            match_reason = "REQUIRED_ITEMS_FOUND_CRITERIA_FAILED"
        else:
            target_items_pass = True
            thresholds_matched = True
            target_only_matched = False
            all_matched = True
            match_reason = "PERFECT_MATCH_ALL"
    else:
        if thresholds_pass:
            target_items_pass = True
            thresholds_matched = True
            target_only_matched = False
            all_matched = True
            match_reason = "THRESHOLDS_MATCH"
        else:
            target_items_pass = False
            thresholds_matched = False
            target_only_matched = False
            all_matched = False
            match_reason = "CRITERIA_NOT_MET"

    return target_items_pass, thresholds_matched, target_only_matched, all_matched, match_reason


def scan_stage1_seed_filter(
    memory: ProcessMemory,
    module_base: int,
    marker_client: MapMarkerMemoryClient | None = None,
    game_client: GameDataClient | None = None,
    fast_eval: bool = False,
    character: tuple[int, str] | None = None,
    required_all_item_ids: list[int] | None = None,
    required_any_item_ids: list[int] | None = None,
    **kwargs: Any,
) -> dict:
    """Scan all Shady Guys in memory during Stage 1 and evaluate threshold criteria + required items."""
    t0 = time.time()
    stage_idx = get_stage_index(memory, module_base)
    if stage_idx != 0:
        return {"is_stage_1": False, "stage_index": stage_idx}

    if (required_all_item_ids is not None) or (required_any_item_ids is not None):
        req_all = list(required_all_item_ids or [])
        req_any = list(required_any_item_ids or [])
    else:
        req_all = list(REQUIRED_ALL_ITEM_IDS) if REQUIRED_ALL_ITEM_IDS else []
        req_any = list(REQUIRED_ANY_ITEM_IDS) if REQUIRED_ANY_ITEM_IDS else []

    if character is None:
        character = get_character_identity(memory, module_base)
    char_id = character[0] if character else None
    char_name = character[1] if character else "Unknown"
    is_fox = bool(char_name == "Fox" or char_id == 0)

    # 1. Read Map Activity Counts
    map_counts = get_map_interactable_counts(memory, game_client)

    # 2. Evaluate Shrine Thresholds
    sm_total = map_counts["shady"] + map_counts["moai"]
    sm_pass = sm_total >= THRESHOLD_SHADY_PLUS_MOAI
    micro_pass = map_counts["microwaves"] >= THRESHOLD_MICROWAVES
    boss_pass = map_counts["boss_curses"] >= THRESHOLD_BOSS_CURSES
    magnet_pass = map_counts["magnets"] >= THRESHOLD_MAGNET_CURSES
    counts_pass = sm_pass and micro_pass and boss_pass and magnet_pass

    mandatory_active = bool(req_all) or bool(req_any)
    min_shadys_needed = len(req_all) + (1 if req_any else 0)
    skip_heap = False
    if fast_eval:
        if not counts_pass or (mandatory_active and map_counts["shady"] < min_shadys_needed):
            skip_heap = True

    if skip_heap:
        dt = time.time() - t0
        target_items_pass = False if mandatory_active else True
        if mandatory_active:
            skip_reason = "MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS" if counts_pass else "MISSING_REQUIRED_ITEMS"
        else:
            skip_reason = "CRITERIA_NOT_MET"
        return {
            "is_stage_1": True,
            "stage_index": 0,
            "elapsed_s": round(dt, 3),
            "character": char_name,
            "character_id": char_id,
            "is_fox": is_fox,
            "required_all_item_ids": req_all,
            "required_any_item_ids": req_any,
            "required_items_satisfied": False if mandatory_active else True,
            "required_all_satisfied": False if req_all else True,
            "required_any_satisfied": False if req_any else True,
            "offered_item_counts": {},
            "map_counts": map_counts,
            "sm_total": sm_total,
            "sm_pass": sm_pass,
            "micro_pass": micro_pass,
            "boss_pass": boss_pass,
            "magnet_pass": magnet_pass,
            "target_items_found": False,
            "target_items_pass": target_items_pass,
            "target_matches": [],
            "thresholds_matched": False,
            "target_only_matched": False,
            "all_matched": False,
            "match_reason": skip_reason,
            "shady_skipped": True,
            "shady_count": map_counts["shady"],
            "shady_guys": [],
            "microwaves": [],
            "moais": [],
            "boss_curses": [],
        }

    # 3. Scan Shady Guy, Microwave, Moai, and Boss Curse instances across the heap
    target_shady = map_counts.get("shady", 0)
    target_micro = map_counts.get("microwaves", 0) if (REQUIRE_BOTH_MICROWAVES_WHITE or not fast_eval) else 0
    # In fast evaluation (auto-rerolls), Boss Curses and Moais are already verified from map_counts;
    # skipping their heap scans prevents slow multi-pass retries for missing instances.
    target_moai = 0 if fast_eval else map_counts.get("moai", 0)
    target_boss = 0 if fast_eval else map_counts.get("boss_curses", 0)

    # Shady Guy items take ~0.85s - 0.95s after map load to be rolled and populated in Unity memory.
    # 16 attempts with 60ms sleep gives a ~0.96s window. The loop breaks immediately the moment
    # all Shady Guys are populated, so it only waits as long as Unity needs to generate the items.
    max_scan_attempts = 16 if (target_shady > 0 or target_micro > 0 or target_moai > 0 or target_boss > 0) else 1

    shady_guys, microwaves, moais, boss_curses = scan_heap_interactables(
        memory,
        module_base,
        marker_client=marker_client,
        target_shady=target_shady,
        target_micro=target_micro,
        target_moai=target_moai,
        target_boss=target_boss,
        max_scan_attempts=max_scan_attempts,
    )

    dt = time.time() - t0

    # 4. Check for Target Items in Shady Guy items
    target_matches = evaluate_target_item_matches(shady_guys)

    # 5. Evaluate Thresholds & Requirements
    white_microwaves = [m for m in microwaves if m.get("color") == "White"]
    if REQUIRE_BOTH_MICROWAVES_WHITE:
        micro_pass = (
            len(microwaves) >= THRESHOLD_MICROWAVES
            and len(white_microwaves) >= THRESHOLD_MICROWAVES
            and all(m.get("color") == "White" for m in microwaves)
        )
    else:
        micro_pass = map_counts["microwaves"] >= THRESHOLD_MICROWAVES

    shady_resolved = (target_shady == 0) or (len(shady_guys) >= target_shady)
    shady_pass = (target_shady == 0) or (len(shady_guys) > 0)

    has_white_micro = len(white_microwaves) >= 1

    # Count offered items across all Shady Guys
    offered_item_counts: dict[int, int] = {}
    offered_item_ids: set[int] = set()
    for sg in shady_guys:
        for it in sg.get("items", []):
            it_id = it.get("item_id")
            if it_id is not None:
                offered_item_counts[it_id] = offered_item_counts.get(it_id, 0) + 1
                offered_item_ids.add(it_id)

    (
        target_items_pass,
        thresholds_matched,
        target_only_matched,
        all_matched,
        match_reason,
    ) = evaluate_stage1_criteria(
        sm_pass=sm_pass,
        micro_pass=micro_pass,
        boss_pass=boss_pass,
        magnet_pass=magnet_pass,
        shady_pass=shady_pass,
        required_all_item_ids=req_all,
        required_any_item_ids=req_any,
        offered_item_ids=offered_item_ids,
        has_white_micro=has_white_micro,
        is_fox=is_fox,
        shady_guys=shady_guys,
    )

    if mandatory_active:
        all_passed, any_passed, required_items_satisfied = can_satisfy_required_items_on_distinct_shadys(
            shady_guys, req_all, req_any
        )
    else:
        all_passed = True
        any_passed = True
        required_items_satisfied = True

    return {
        "is_stage_1": True,
        "stage_index": 0,
        "elapsed_s": round(dt, 3),
        "character": char_name,
        "character_id": char_id,
        "is_fox": is_fox,
        "required_all_item_ids": req_all,
        "required_any_item_ids": req_any,
        "required_items_satisfied": required_items_satisfied,
        "required_all_satisfied": all_passed,
        "required_any_satisfied": any_passed,
        "offered_item_counts": offered_item_counts,
        "map_counts": map_counts,
        "sm_total": sm_total,
        "sm_pass": sm_pass,
        "micro_pass": micro_pass,
        "boss_pass": boss_pass,
        "magnet_pass": magnet_pass,
        "target_items_found": bool(target_matches),
        "target_items_pass": target_items_pass,
        "target_matches": target_matches,
        "thresholds_matched": thresholds_matched,
        "target_only_matched": target_only_matched,
        "all_matched": all_matched,
        "match_reason": match_reason,
        "shady_skipped": False,
        "shady_resolved": shady_resolved,
        "shady_count": len(shady_guys),
        "target_shady": target_shady,
        "shady_guys": shady_guys,
        "microwaves": microwaves,
        "moais": moais,
        "boss_curses": boss_curses,
    }


def scan_stage_inspect(
    memory: ProcessMemory,
    module_base: int,
    marker_client: MapMarkerMemoryClient | None = None,
    game_client: GameDataClient | None = None,
    stage_idx: int = 1,
    character: tuple[int, str] | None = None,
) -> dict:
    """Scan and inspect all Shady Guys and Microwaves for Stage 2, Stage 3, etc."""
    t0 = time.time()
    if character is None:
        character = get_character_identity(memory, module_base)
    char_id = character[0] if character else None
    char_name = character[1] if character else "Unknown"

    map_counts = get_map_interactable_counts(memory, game_client)
    target_shady = map_counts.get("shady", 0)
    target_micro = map_counts.get("microwaves", 0)
    target_moai = map_counts.get("moai", 0)
    target_boss = map_counts.get("boss_curses", 0)

    shady_guys, microwaves, moais, boss_curses = scan_heap_interactables(
        memory,
        module_base,
        marker_client=marker_client,
        target_shady=target_shady,
        target_micro=target_micro,
        target_moai=target_moai,
        target_boss=target_boss,
        max_scan_attempts=12 if (target_shady > 0 or target_micro > 0 or target_moai > 0 or target_boss > 0) else 3,
    )

    dt = time.time() - t0
    target_matches = evaluate_target_item_matches(shady_guys)

    return {
        "stage_index": stage_idx,
        "stage_num": stage_idx + 1,
        "elapsed_s": round(dt, 3),
        "character": char_name,
        "character_id": char_id,
        "map_counts": map_counts,
        "sm_total": map_counts.get("shady", 0) + map_counts.get("moai", 0),
        "shady_count": len(shady_guys),
        "shady_guys": shady_guys,
        "microwaves": microwaves,
        "moais": moais,
        "boss_curses": boss_curses,
        "target_matches": target_matches,
    }


def _format_required_items_summary(result: dict) -> tuple[str, str, list[int], int]:
    """Return (req_label_str, found_label_str, combined_req_ids, min_shadys_needed) for display."""
    has_req_all = "required_all_item_ids" in result
    has_req_any = "required_any_item_ids" in result

    if has_req_all or has_req_any:
        req_all = list(result.get("required_all_item_ids") or [])
        req_any = list(result.get("required_any_item_ids") or [])
    else:
        req_all = list(REQUIRED_ALL_ITEM_IDS) if REQUIRED_ALL_ITEM_IDS else []
        req_any = list(REQUIRED_ANY_ITEM_IDS) if REQUIRED_ANY_ITEM_IDS else []

    min_shadys_needed = len(req_all) + (1 if req_any else 0)

    offered_cnts = result.get("offered_item_counts", {})
    all_names = [get_item_name(i) for i in req_all]
    any_names = [get_item_name(i) for i in req_any]

    parts = []
    if all_names:
        parts.append(f"{' & '.join(all_names)} (ALL)")
    if any_names:
        parts.append(f"at least 1 of [{' OR '.join(any_names)}] (ANY)")
    req_label = " and ".join(parts) if parts else "Required items"

    found_names = []
    for i in req_all:
        if offered_cnts.get(i, 0) > 0:
            found_names.append(get_item_name(i))
    for i in req_any:
        if offered_cnts.get(i, 0) > 0 and get_item_name(i) not in found_names:
            found_names.append(get_item_name(i))
    found_label = " & ".join(found_names) if found_names else "Required items"

    combined_ids = list(dict.fromkeys(req_all + req_any))
    return req_label, found_label, combined_ids, min_shadys_needed


def print_stage1_report(
    result: dict,
    reroll_num: int | None = None,
    clear_screen: bool = False,
    powerup_data: dict | None = None,
) -> None:
    if clear_screen and CLEAR_CONSOLE_ON_OUTPUT:
        clear_console()

    if powerup_data is None:
        powerup_data = result.get("powerup_data")

    if not result.get("is_stage_1"):
        stage_num = result.get("stage_index", -1) + 1
        print(f"[*] Stage {stage_num} active. (Seed filter only runs on Stage 1)", flush=True)
        return

    counts = result["map_counts"]
    sm_total = result["sm_total"]
    sm_mark = "PASS" if result["sm_pass"] else "FAIL"
    micro_mark = "PASS" if result["micro_pass"] else "FAIL"
    boss_mark = "PASS" if result["boss_pass"] else "FAIL"
    magnet_mark = "PASS" if result["magnet_pass"] else "FAIL"

    reroll_info = f" | Reroll #{reroll_num}" if reroll_num is not None else ""
    req_label, found_label, combined_ids, min_shadys_needed = _format_required_items_summary(result)

    if console and Table and Panel:
        reason = result.get("match_reason")
        if reason == "PERFECT_MATCH_ALL":
            title_color = "bold green"
            if combined_ids:
                status_text = f"[bold green]🎉 PERFECT SEED MATCH ON STAGE 1![/]\n[green]{found_label} satisfied & all other criteria met![/]"
            else:
                status_text = "[bold green]🎉 PERFECT SEED MATCH ON STAGE 1![/]\n[green]All shrine & curse thresholds satisfied![/]"
        elif reason == "THRESHOLDS_MATCH":
            title_color = "bold green"
            status_text = "[bold green]🎉 THRESHOLDS MATCH ON STAGE 1![/]\n[green]All shrine & curse thresholds satisfied![/]"
        elif reason == "REQUIRED_ITEMS_CONFLICT_SAME_SHADY":
            title_color = "bold red"
            status_text = (
                f"[bold red]Status: CRITERIA NOT MET[/]\n"
                f"[yellow]Required items found on map, but conflict on the same Shady Guy! "
                f"Must appear across at least {min_shadys_needed} different Shady Guys.[/]"
            )
        elif reason == "MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS":
            title_color = "bold red"
            status_text = f"[bold red]Status: CRITERIA NOT MET[/]\n[yellow]Threshold criteria met ({sm_total}/{THRESHOLD_SHADY_PLUS_MOAI}), but requires {req_label} on map![/]"
        elif reason == "REQUIRED_ITEMS_FOUND_CRITERIA_FAILED":
            title_color = "bold red"
            status_text = f"[bold red]Status: CRITERIA NOT MET[/]\n[yellow]{found_label} found, but other criteria failed ({sm_total}/{THRESHOLD_SHADY_PLUS_MOAI} Shady+Moai)![/]"
        elif reason == "MISSING_REQUIRED_ITEMS":
            title_color = "bold red"
            status_text = f"[bold red]Status: CRITERIA NOT MET[/]\n[yellow]Strictly requires {req_label} on map![/]"
        elif result.get("all_matched"):
            title_color = "bold green"
            status_text = "[bold green]🎉 PERFECT SEED MATCH ON STAGE 1![/]"
        else:
            title_color = "bold red"
            status_text = "[bold red]Status: CRITERIA NOT MET[/]"

        char_name = result.get("character")
        char_info = f" | Character: [bold]{char_name}[/]" if char_name and char_name != "Unknown" else ""

        title = f"STAGE 1 SEED EVALUATION (Scan took {result['elapsed_s']}s{reroll_info}{char_info})"
        panel = Panel(
            status_text,
            title=title,
            title_align="left",
            border_style=title_color,
            expand=False,
        )
        console.print(panel)

        if not result.get("all_matched"):
            # If status is criteria not met, do not populate or display any tables; re-roll immediately
            print("", flush=True)
            return

        table = Table(
            title="Stage 1 Requirements",
            header_style="bold bright_white",
        )
        table.add_column("Condition", style="bold")
        table.add_column("Status", justify="center")
        table.add_column("Current / Target", justify="right")
        table.add_column("Details", style="bright_white")

        sm_color = "bold green" if result["sm_pass"] else "bold red"
        micro_color = "bold green" if result["micro_pass"] else "bold red"
        boss_color = "bold green" if result["boss_pass"] else "bold red"
        magnet_color = "bold green" if result["magnet_pass"] else "bold red"

        moai_list = result.get("moais", [])
        moai_dirs = [m["dir"] for m in moai_list if m.get("dir") and m["dir"] != "Unknown"]
        moais_detail = f"Moais: {counts['moai']} ({', '.join(moai_dirs)})" if moai_dirs else f"Moais: {counts['moai']}"
        table.add_row(
            "Shady + Moai",
            f"[{sm_color}]{sm_mark}[/]",
            f"{sm_total} / {THRESHOLD_SHADY_PLUS_MOAI}",
            f"Shady: {counts['shady']}, {moais_detail}",
        )

        micro_list = result.get("microwaves", [])
        micro_parts = []
        for m in micro_list:
            sec_str = f" @ {m['map_sector']}" if m.get("map_sector") else ""
            micro_parts.append(f"{m['color']}{sec_str}")
        if micro_parts:
            micro_details = ", ".join(micro_parts)
        else:
            micro_details = ""

        micro_label = "Microwaves (2x White)" if REQUIRE_BOTH_MICROWAVES_WHITE else "Microwaves"
        white_cnt = sum(1 for m in micro_list if m.get("color") == "White")
        micro_cur_str = (
            f"{white_cnt} White ({counts['microwaves']} total)"
            if REQUIRE_BOTH_MICROWAVES_WHITE
            else f"{counts['microwaves']}"
        )
        table.add_row(
            micro_label,
            f"[{micro_color}]{micro_mark}[/]",
            f"{micro_cur_str} / {THRESHOLD_MICROWAVES}",
            micro_details,
        )
        boss_list = result.get("boss_curses", [])
        boss_dirs = [b["dir"] for b in boss_list if b.get("dir") and b["dir"] != "Unknown"]
        boss_detail = f"Directions: {', '.join(boss_dirs)}" if boss_dirs else ""
        table.add_row(
            "Boss Curses",
            f"[{boss_color}]{boss_mark}[/]",
            f"{counts['boss_curses']} / {THRESHOLD_BOSS_CURSES}",
            boss_detail,
        )
        table.add_row(
            "Magnet Curses",
            f"[{magnet_color}]{magnet_mark}[/]",
            f"{counts['magnets']} / {THRESHOLD_MAGNET_CURSES}",
            "",
        )

        offered_counts = dict(result.get("offered_item_counts") or {})

        if combined_ids:
            for iid in combined_ids:
                item_name = get_item_name(iid)
                target_label = f"Target Items ({item_name})"
                item_cnt = offered_counts.get(iid, 0)
                if item_cnt > 0:
                    table.add_row(
                        target_label,
                        "[bold green]PASS[/]",
                        f"{item_cnt} / 1 {item_name}",
                        item_name,
                    )
                else:
                    table.add_row(
                        target_label,
                        "[bold red]FAIL[/]",
                        f"0 / 1 {item_name}",
                        item_name,
                    )

        console.print(table)

        # Ranked Shady Items table when criteria is met
        if result.get("all_matched") and result.get("shady_guys"):
            if result.get("shady_guys"):
                ranked_items = get_all_shady_items_ranked(result["shady_guys"])
                available_items = sum(1 for it in ranked_items if not it.get("shady_done"))
                avail_str = (
                    f"{available_items}/{len(ranked_items)} available"
                    if available_items < len(ranked_items)
                    else f"{len(ranked_items)} items"
                )
                items_table = Table(
                    title=f"🎯 All Shady Items Ranked by Distance ({avail_str} across {len(result['shady_guys'])} Shady Guys)",
                    header_style="bold bright_white",
                )
                items_table.add_column("Rank", style="bold bright_white", justify="right")
                items_table.add_column("Distance", style="bright_white", justify="right")
                items_table.add_column("Direction", style="bold bright_white")
                items_table.add_column("Map Sector", style="bold white")
                items_table.add_column("Shady Guy", style="bold yellow")
                items_table.add_column("Tier", justify="center")
                items_table.add_column("Item", style="bold bright_white")
                items_table.add_column("Gold Price", justify="right", style="bold bright_yellow")
                items_table.add_column("Multiplier", justify="right")
                items_table.add_column("Status", justify="center")

                for item_rank, it in enumerate(ranked_items, 1):
                    is_taken = it.get("shady_done", False)
                    dist_str = f"{it['dist']}m" if it.get("dist") is not None else "??m"
                    dir_str = f"{it['direction']} {it['bearing_str']}".strip() if it.get("direction") else "-"

                    sg_label = f"Shady #{it['shady_num']}"
                    sector_str = it.get("map_sector") or "-"
                    tier_str = format_shady_rarity(it.get("shady_rarity") or it.get("rarity", "COMMON"), use_rich=True)
                    name_str = format_item_display(it.get("item_id"), it["item_name"], use_rich=True)

                    gold_str = f"{it['gold']}g" if it.get("gold") is not None else "-"
                    mult_str = f"{it['multiplier']:.2f}x" if it.get("multiplier") is not None else "-"

                    if is_taken:
                        rank_disp = f"[dim strike]{item_rank}[/]"
                        dist_disp = f"[dim strike]{dist_str}[/]"
                        dir_disp = f"[dim strike]{dir_str}[/]"
                        sec_disp = f"[dim strike]{sector_str}[/]"
                        sg_disp = f"[dim strike]{sg_label}[/] [dim red][DONE][/]"
                        tier_disp = f"[dim strike]{tier_str}[/]"
                        name_disp = f"[dim strike]{name_str}[/] [bold red][TAKEN][/]"
                        gold_disp = f"[dim strike]{gold_str}[/]"
                        mult_disp = f"[dim strike]{mult_str}[/]"
                        status_disp = "[dim red]TAKEN[/]"
                    else:
                        rank_disp = str(item_rank)
                        dist_disp = dist_str
                        dir_disp = dir_str
                        sec_disp = sector_str
                        sg_disp = sg_label
                        tier_disp = tier_str
                        name_disp = name_str
                        gold_disp = gold_str
                        mult_disp = mult_str
                        status_disp = "[green]AVAILABLE[/]"

                    items_table.add_row(
                        rank_disp,
                        dist_disp,
                        dir_disp,
                        sec_disp,
                        sg_disp,
                        tier_disp,
                        name_disp,
                        gold_disp,
                        mult_disp,
                        status_disp,
                    )

                    is_last_in_group = (
                        item_rank == len(ranked_items)
                        or ranked_items[item_rank]["shady_num"] != it["shady_num"]
                    )
                    if is_last_in_group and item_rank < len(ranked_items):
                        items_table.add_section()

                console.print(items_table)

            if result.get("shady_guys"):
                shady_guys = result["shady_guys"]
                available_sgs = sum(1 for sg in shady_guys if not sg.get("done"))
                sg_avail_str = (
                    f"{available_sgs}/{len(shady_guys)} available"
                    if available_sgs < len(shady_guys)
                    else f"{len(shady_guys)} found on map"
                )
                sg_table = Table(
                    title=f"STAGE 1 - SHADY GUY INVENTORIES ({sg_avail_str} - Ranked by Distance)",
                    header_style="bold bright_white",
                )
                sg_table.add_column("Rank", style="bold bright_white", justify="right")
                sg_table.add_column("Shady Guy", style="bold yellow")
                sg_table.add_column("Tier", justify="center")
                sg_table.add_column("Status", justify="center")
                sg_table.add_column("Distance & Direction", style="bright_white")
                sg_table.add_column("Map Sector", style="bold white")
                sg_table.add_column("Items Offered (Gold / Mult)", style="bright_white")

                for i, sg in enumerate(shady_guys):
                    is_done = sg.get("done", False)
                    status_tag = "[dim red]COMPLETED[/]" if is_done else "[green]AVAILABLE[/]"
                    prices = sg.get("gold_prices", [])
                    item_names = []
                    for it_idx, it in enumerate(sg["items"]):
                        name = it.get("item_name", "?")
                        item_id = it.get("item_id")
                        cost = ""
                        if it_idx < len(prices):
                            cost = f" ({prices[it_idx]}g)"
                        styled_name = format_item_display(item_id, name, use_rich=True)
                        if is_done:
                            item_names.append(f"[dim strike]{styled_name}{cost}[/]")
                        else:
                            item_names.append(f"{styled_name}{cost}")

                    loc_parts = []
                    if sg.get("rel_dir"):
                        rel = sg["rel_dir"]
                        loc_parts.append(f"{rel[2]}m {rel[0]}")
                    elif sg.get("dist") is not None:
                        loc_parts.append(f"{sg['dist']}m")
                    loc_str = ", ".join(loc_parts) if loc_parts else "-"
                    sector_str = sg.get("map_sector") or "-"
                    tier_str = format_shady_rarity(sg.get("rarity", "COMMON"), use_rich=True)

                    if is_done:
                        rank_disp = f"[dim strike]{i + 1}[/]"
                        sg_disp = f"[dim strike]Shady #{sg.get('shady_num', i + 1)}[/]"
                        tier_disp = f"[dim strike]{tier_str}[/] [dim red][DONE][/]"
                        loc_disp = f"[dim strike]{loc_str}[/]"
                        sector_disp = f"[dim strike]{sector_str}[/]"
                    else:
                        rank_disp = str(i + 1)
                        sg_disp = f"Shady #{sg.get('shady_num', i + 1)}"
                        tier_disp = tier_str
                        loc_disp = loc_str
                        sector_disp = sector_str

                    sg_table.add_row(
                        rank_disp,
                        sg_disp,
                        tier_disp,
                        status_tag,
                        loc_disp,
                        sector_disp,
                        ", ".join(item_names),
                    )
                console.print(sg_table)
            elif counts.get("shady", 0) == 0:
                console.print(
                    Panel(
                        f"[cyan]ℹ No Shady Guys spawned on this map ({counts.get('moai', 0)} Moai Shrines present).[/]",
                        title="Shady Guys",
                        style="cyan",
                        expand=False,
                    )
                )
            else:
                console.print(
                    Panel(
                        f"[yellow]⚠ {counts.get('shady', 0)} Shady Guy(s) expected on map, but instances were not resolved from memory.[/]",
                        title="Shady Guys Warning",
                        style="yellow",
                        expand=False,
                    )
                )

        if result.get("all_matched") and result.get("microwaves"):
            microwaves = result["microwaves"]
            micro_table = Table(
                title=f"STAGE 1 - MICROWAVES ON MAP ({len(microwaves)} found on map - Ranked by Distance)",
                header_style="bold bright_white",
            )
            micro_table.add_column("Rank", style="bold bright_white", justify="right")
            micro_table.add_column("Microwave Color / Tier", style="bold")
            micro_table.add_column("Distance", style="bright_white", justify="right")
            micro_table.add_column("Direction", style="bold bright_white")
            micro_table.add_column("Map Sector", style="bold white")
            micro_table.add_column("Uses Left", justify="center")

            for i, m in enumerate(microwaves, 1):
                dist_disp = f"{m['dist']}m" if m.get("dist") is not None else "-"
                rel = m.get("rel_dir")
                if rel:
                    dir_disp = f"{rel[0]} ({rel[1]}°)"
                else:
                    dir_disp = "-"
                c_style = m.get("style", "bright_white")
                rarity = m.get("rarity", 0)
                color_tier_str = f"[{c_style}]{m['color']} (Tier {rarity})[/]"
                sector_disp = m.get("map_sector") or "-"
                micro_table.add_row(
                    str(i),
                    color_tier_str,
                    dist_disp,
                    dir_disp,
                    sector_disp,
                    str(m.get("uses_left", 3)),
                )
            console.print(micro_table)

        render_active_powerups_block(powerup_data, use_rich=True)
        print("", flush=True)
        return

    # Plain-text fallback if rich is unavailable
    print("\n" + "=" * 80, flush=True)
    if result["all_matched"]:
        reason = result.get("match_reason")
        if reason == "PERFECT_MATCH_ALL":
            print(f">>> [PERFECT SEED MATCH ON STAGE 1! (Thresholds + Required Items){reroll_info}] <<<", flush=True)
            print("=" * 80, flush=True)
            print(f"ALL THRESHOLDS & REQUIRED ITEMS MATCHED (Scan took {result['elapsed_s']}s):", flush=True)
        else:
            print(f">>> [PERFECT SEED MATCH ON STAGE 1!{reroll_info}] <<<", flush=True)
            print("=" * 80, flush=True)
            print(f"ALL THRESHOLDS MATCHED (Scan took {result['elapsed_s']}s):", flush=True)
    else:
        char_plain = f" | Character: {result.get('character', 'Unknown')}" if result.get("character") else ""
        print(f"[STAGE 1 SEED EVALUATION]{reroll_info}{char_plain} (Scan took {result['elapsed_s']}s)", flush=True)
        print("-" * 80, flush=True)
        reason = result.get("match_reason")
        if reason == "REQUIRED_ITEMS_CONFLICT_SAME_SHADY":
            print(f"Status: [-] CRITERIA NOT MET (Required items found on map, but conflict on the same Shady Guy! Must appear across at least {min_shadys_needed} different Shady Guys)", flush=True)
        elif reason == "MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS":
            print(f"Status: [-] CRITERIA NOT MET (Threshold criteria met [{sm_total}/{THRESHOLD_SHADY_PLUS_MOAI}], but requires {req_label} on map)", flush=True)
        elif reason == "REQUIRED_ITEMS_FOUND_CRITERIA_FAILED":
            print(f"Status: [-] CRITERIA NOT MET ({found_label} found, but other criteria failed: {sm_total}/{THRESHOLD_SHADY_PLUS_MOAI} Shady+Moai)", flush=True)
        elif reason == "MISSING_REQUIRED_ITEMS":
            print(f"Status: [-] CRITERIA NOT MET (Strictly requires {req_label} on map)", flush=True)
        else:
            print("Status: [-] CRITERIA NOT MET", flush=True)
        print("=" * 80 + "\n", flush=True)
        return

    micro_list = result.get("microwaves", [])
    if micro_list:
        micro_str_parts = []
        for m in micro_list:
            sec_str = f" @ {m['map_sector']}" if m.get("map_sector") else ""
            micro_str_parts.append(f"{m['color']}{sec_str}")
        micro_info = f" ({', '.join(micro_str_parts)})"
    else:
        micro_info = ""

    micro_label = "Microwaves (2x White)" if REQUIRE_BOTH_MICROWAVES_WHITE else "Microwaves"
    white_cnt = sum(1 for m in micro_list if m.get("color") == "White")
    micro_cur_str = (
        f"{white_cnt} White ({counts['microwaves']} total)"
        if REQUIRE_BOTH_MICROWAVES_WHITE
        else f"{counts['microwaves']:>2d}"
    )
    moai_list = result.get("moais", [])
    moai_dirs = [m["dir"] for m in moai_list if m.get("dir") and m["dir"] != "Unknown"]
    moais_detail = f"Moais: {counts['moai']} ({', '.join(moai_dirs)})" if moai_dirs else f"Moais: {counts['moai']}"
    print(f"  [{sm_mark:^4}] Shady + Moai:         {sm_total:>2d} / {THRESHOLD_SHADY_PLUS_MOAI}  (Shady: {counts['shady']}, {moais_detail})", flush=True)
    print(f"  [{micro_mark:^4}] {micro_label:<21}: {micro_cur_str} / {THRESHOLD_MICROWAVES}{micro_info}", flush=True)
    boss_list = result.get("boss_curses", [])
    boss_dirs = [b["dir"] for b in boss_list if b.get("dir") and b["dir"] != "Unknown"]
    boss_detail_str = f" ({', '.join(boss_dirs)})" if boss_dirs else ""
    print(f"  [{boss_mark:^4}] Boss Curses:          {counts['boss_curses']:>2d} / {THRESHOLD_BOSS_CURSES}{boss_detail_str}", flush=True)
    print(f"  [{magnet_mark:^4}] Magnet Curses:        {counts['magnets']:>2d} / {THRESHOLD_MAGNET_CURSES}", flush=True)

    offered_counts_plain = dict(result.get("offered_item_counts") or {})

    if combined_ids:
        for iid in combined_ids:
            item_name = get_item_name(iid)
            target_label = f"Target Items ({item_name})"
            item_cnt = offered_counts_plain.get(iid, 0)
            if item_cnt > 0:
                print(f"  [PASS] {target_label}:    MATCHED ({item_cnt} {item_name} found on map)", flush=True)
            else:
                print(f"  [FAIL] {target_label}:    FAILED (0 {item_name} found on map)", flush=True)

    if result.get("all_matched") and result.get("shady_guys"):
        if result.get("shady_guys"):
            ranked_items = get_all_shady_items_ranked(result["shady_guys"])
            available_items = sum(1 for it in ranked_items if not it.get("shady_done"))
            avail_str = (
                f"{available_items}/{len(ranked_items)} available"
                if available_items < len(ranked_items)
                else f"{len(ranked_items)} items"
            )
            print("-" * 80, flush=True)
            print(f"🎯 ALL SHADY ITEMS RANKED BY DISTANCE ({avail_str} across {len(result['shady_guys'])} Shady Guys):", flush=True)
            print("-" * 80, flush=True)
            for item_rank, it in enumerate(ranked_items, 1):
                is_taken = it.get("shady_done", False)
                dist_str = f"{it['dist']}m" if it.get("dist") is not None else "??m"
                dir_str = f"{it['direction']} {it['bearing_str']}".strip() if it.get("direction") else ""
                loc_str = f"{dist_str} {dir_str}".strip()

                cost_parts = []
                if it.get("gold") is not None:
                    cost_parts.append(f"{it['gold']}g")
                if it.get("multiplier") is not None:
                    cost_parts.append(f"{it['multiplier']}x")
                cost_str = f"({', '.join(cost_parts)})" if cost_parts else ""

                item_id = it.get("item_id")
                name = it.get("item_name")
                if is_target_item(item_id, name):
                    target_star = "*"
                elif is_highlighted_item(item_id, name):
                    target_star = HIGHLIGHTED_ITEM_MARKER
                else:
                    target_star = " "
                sec_str = f"[{it['map_sector']}]"
                sh_rarity = it.get("shady_rarity") or it.get("rarity", "")
                if is_taken:
                    vendor_str = f"Shady #{it['shady_num']} [{sh_rarity}] [DONE]"
                    item_disp = f"{it['item_name']}{target_star} [TAKEN]"
                    line_out = f"  #{item_rank:>2d}  [{loc_str:<16}] {item_disp:<24} {cost_str:<16} @ {vendor_str} {sec_str}"
                    print(f"\033[2;9m{line_out}\033[0m", flush=True)
                else:
                    vendor_str = f"Shady #{it['shady_num']} [{sh_rarity}]"
                    item_disp = f"{it['item_name']}{target_star}"
                    print(f"  #{item_rank:>2d}  [{loc_str:<16}] {item_disp:<24} {cost_str:<16} @ {vendor_str} {sec_str}", flush=True)

                is_last_in_group = (
                    item_rank == len(ranked_items)
                    or ranked_items[item_rank]["shady_num"] != it["shady_num"]
                )
                if is_last_in_group and item_rank < len(ranked_items):
                    print("  " + "-" * 76, flush=True)

            print("-" * 80, flush=True)
            available_sgs = sum(1 for sg in result["shady_guys"] if not sg.get("done"))
            sg_avail_str = (
                f"{available_sgs}/{result['shady_count']} available"
                if available_sgs < result["shady_count"]
                else f"{result['shady_count']} found on map"
            )
            print(f"SHADY GUY INVENTORIES ({sg_avail_str} - Ranked by Distance):", flush=True)
            for i, sg in enumerate(result["shady_guys"]):
                is_done = sg.get("done", False)
                done_tag = " [DONE]" if is_done else ""
                prices = sg.get("gold_prices", [])
                mults = sg.get("multipliers", [])
                item_names = []
                for it_idx, it in enumerate(sg["items"]):
                    name = it.get("item_name", "?")
                    item_id = it.get("item_id")
                    cost = ""
                    if it_idx < len(prices):
                        cost = f" ({prices[it_idx]}g)"
                    item_tag = "*" if is_target_item(item_id, name) else (HIGHLIGHTED_ITEM_MARKER if is_highlighted_item(item_id, name) else "")
                    if is_done:
                        item_names.append(f"\033[2;9m{name}{item_tag}{cost} [TAKEN]\033[0m")
                    else:
                        item_names.append(f"{name}{item_tag}{cost}")
                loc_parts = []
                if sg.get("map_sector"):
                    loc_parts.append(f"Map: {sg['map_sector']}")
                if sg.get("rel_dir"):
                    rel = sg["rel_dir"]
                    loc_parts.append(f"{rel[2]}m {rel[0]}")
                elif sg.get("dist") is not None:
                    loc_parts.append(f"{sg['dist']}m")
                loc_str = f" ({', '.join(loc_parts)})" if loc_parts else ""
                line_str = f"  Rank #{i+1} - Shady Guy [{sg.get('rarity', 'COMMON')}]{done_tag}{loc_str}: {', '.join(item_names)}"
                if is_done:
                    print(f"\033[2;9m{line_str}\033[0m", flush=True)
                else:
                    print(line_str, flush=True)
        elif counts.get("shady", 0) == 0:
            print(f"  [Shady Guys] ℹ No Shady Guys spawned on this map ({counts.get('moai', 0)} Moai Shrines present).", flush=True)
        else:
            print(f"  [Shady Guys] ⚠ {counts.get('shady', 0)} Shady Guy(s) expected on map, but instances could not be resolved from memory.", flush=True)

    if result.get("all_matched") and result.get("microwaves"):
        print("-" * 80, flush=True)
        print(f"MICROWAVES ON MAP ({len(result['microwaves'])} found on map - Ranked by Distance):", flush=True)
        for i, m in enumerate(result["microwaves"]):
            dist_str = f"{m['dist']}m" if m.get("dist") is not None else "??m"
            rel = m.get("rel_dir")
            dir_str = f"{rel[0]} ({rel[1]}°)" if rel else ""
            loc_str = f"{dist_str} {dir_str}".strip()
            sec_str = f"[{m.get('map_sector', 'Unknown')}]"
            rarity = m.get("rarity", 0)
            uses_str = f"{m.get('uses_left', 3)} uses"
            print(f"  #{i+1:>2d}  [{loc_str:<16}] Microwave [{m['color']} / Tier {rarity}] {sec_str} ({uses_str})", flush=True)
    render_active_powerups_block(powerup_data, use_rich=False)
    print("=" * 80 + "\n", flush=True)


def print_stage_inspect_report(
    result: dict,
    clear_screen: bool = False,
    powerup_data: dict | None = None,
) -> None:
    """Print complete inspection stats for Stage 2, Stage 3, etc. without rerolling."""
    if clear_screen and CLEAR_CONSOLE_ON_OUTPUT:
        clear_console()

    if powerup_data is None:
        powerup_data = result.get("powerup_data")

    stage_num = result.get("stage_num", result.get("stage_index", 0) + 1)
    counts = result.get("map_counts", {})
    shady_guys = result.get("shady_guys", [])
    microwaves = result.get("microwaves", [])
    target_matches = result.get("target_matches", [])

    if console and Table and Panel:
        title_color = "bold cyan"
        char_name = result.get("character")
        char_info = f" | Character: [bold]{char_name}[/]" if char_name and char_name != "Unknown" else ""
        panel_lines = [
            f"[bold cyan]STAGE {stage_num} MAP OVERVIEW[/]",
            f"Found {len(shady_guys)} Shady Guys and {len(microwaves)} Microwaves | Scan took {result['elapsed_s']}s{char_info}",
        ]
        if target_matches:
            target_names = ", ".join(m["item_name"] for m in target_matches)
            panel_lines.append(f"[bold yellow]🎯 Target Items Present: {target_names}[/]")

        console.print(
            Panel(
                "\n".join(panel_lines),
                title=f"Stage {stage_num} Overview",
                style=title_color,
                expand=False,
            )
        )

        # 1. Map Interactables Summary Table
        table = Table(title=f"Stage {stage_num} Interactables Summary", header_style="bold bright_white")
        table.add_column("Interactable", style="bold")
        table.add_column("Count", justify="right")
        table.add_column("Details", style="bright_white")

        sm_total = result.get("sm_total", counts.get("shady", 0) + counts.get("moai", 0))
        table.add_row(
            "Shady Guys",
            str(len(shady_guys)),
            f"{counts.get('shady', 0)} reported by map",
        )
        moais = result.get("moais", [])
        moai_dirs = [m["dir"] for m in moais if m.get("dir") and m["dir"] != "Unknown"]
        moai_detail = f"Directions: {', '.join(moai_dirs)}" if moai_dirs else ""
        table.add_row(
            "Moai Shrines",
            str(counts.get("moai", 0)),
            moai_detail,
        )
        table.add_row(
            "Shady + Moai Total",
            str(sm_total),
            "",
        )

        if microwaves:
            micro_summaries = []
            for m in microwaves:
                sec_str = f" @ {m['map_sector']}" if m.get("map_sector") else ""
                style = m.get("style", "bright_white")
                micro_summaries.append(f"[{style}]{m['color']}[/]{sec_str}")
            micro_details = ", ".join(micro_summaries)
        else:
            micro_details = f"{counts.get('microwaves', 0)} reported by map"

        table.add_row(
            "Microwaves",
            str(len(microwaves)),
            micro_details,
        )
        boss_list = result.get("boss_curses", [])
        boss_dirs = [b["dir"] for b in boss_list if b.get("dir") and b["dir"] != "Unknown"]
        boss_detail = f"Directions: {', '.join(boss_dirs)}" if boss_dirs else ""
        table.add_row(
            "Boss Curses",
            str(counts.get("boss_curses", 0)),
            boss_detail,
        )
        table.add_row(
            "Magnet Curses",
            str(counts.get("magnets", 0)),
            "",
        )

        console.print(table)

        # 2. Ranked Shady Items table
        if shady_guys:
            ranked_items = get_all_shady_items_ranked(shady_guys)
            available_items = sum(1 for it in ranked_items if not it.get("shady_done"))
            avail_str = (
                f"{available_items}/{len(ranked_items)} available"
                if available_items < len(ranked_items)
                else f"{len(ranked_items)} items"
            )
            items_table = Table(
                title=f"🎯 Stage {stage_num} - All Shady Items Ranked by Distance ({avail_str} across {len(shady_guys)} Shady Guys)",
                header_style="bold bright_white",
            )
            items_table.add_column("Rank", style="bold bright_white", justify="right")
            items_table.add_column("Distance", style="bright_white", justify="right")
            items_table.add_column("Direction", style="bold bright_white")
            items_table.add_column("Map Sector", style="bold white")
            items_table.add_column("Item Name")
            items_table.add_column("Price (Mult)", style="bold bright_yellow", justify="right")
            items_table.add_column("Vendor")

            for item_rank, it in enumerate(ranked_items, 1):
                is_taken = it.get("shady_done", False)
                dist_disp = f"{it['dist']}m" if it.get("dist") is not None else "-"
                dir_disp = f"{it['direction']} {it['bearing_str']}".strip() if it.get("direction") else "-"

                cost_parts = []
                if it.get("gold") is not None:
                    cost_parts.append(f"{it['gold']}g")
                if it.get("multiplier") is not None:
                    cost_parts.append(f"{it['multiplier']}x")
                cost_str = f"{', '.join(cost_parts)}" if cost_parts else "-"

                name = it["item_name"]
                item_id = it.get("item_id")
                name_styled = format_item_display(item_id, name, use_rich=True)
                vendor_str = format_vendor_display(it["shady_num"], it.get("shady_rarity"), use_rich=True)

                if is_taken:
                    rank_disp = f"[dim strike]{item_rank}[/]"
                    dist_disp = f"[dim strike]{dist_disp}[/]"
                    dir_disp = f"[dim strike]{dir_disp}[/]"
                    sec_disp = f"[dim strike]{it['map_sector']}[/]"
                    name_disp = f"[dim strike]{name_styled}[/] [bold red][TAKEN][/]"
                    cost_disp = f"[dim strike]{cost_str}[/]"
                    vendor_disp = f"[dim strike]{vendor_str}[/] [dim red][DONE][/]"
                else:
                    rank_disp = str(item_rank)
                    sec_disp = it["map_sector"]
                    name_disp = name_styled
                    cost_disp = cost_str
                    vendor_disp = vendor_str

                is_last_in_group = (
                    item_rank == len(ranked_items)
                    or ranked_items[item_rank]["shady_num"] != it["shady_num"]
                )
                items_table.add_row(
                    rank_disp,
                    dist_disp,
                    dir_disp,
                    sec_disp,
                    name_disp,
                    cost_disp,
                    vendor_disp,
                    end_section=is_last_in_group,
                )

            console.print(items_table)

            # 3. Shady Guy Inventories Table
            available_sgs = sum(1 for sg in shady_guys if not sg.get("done"))
            sg_avail_str = (
                f"{available_sgs}/{len(shady_guys)} available"
                if available_sgs < len(shady_guys)
                else f"{len(shady_guys)} found on map"
            )
            sg_table = Table(
                title=f"Stage {stage_num} - Shady Guy Inventories ({sg_avail_str} - Ranked by Distance)",
                header_style="bold bright_white",
            )
            sg_table.add_column("Rank", justify="right")
            sg_table.add_column("Rarity")
            sg_table.add_column("Map Sector", style="bold white")
            sg_table.add_column("From Spawn", justify="right")
            sg_table.add_column("Offered Items (Price, Mult)")

            for i, sg in enumerate(shady_guys):
                is_done = sg.get("done", False)
                dist_str = f"{sg['dist']}m" if sg.get("dist") is not None else "-"
                if sg.get("rel_dir"):
                    rel = sg["rel_dir"]
                    dist_str = f"{rel[2]}m {rel[0]}"

                item_strs = []
                prices = sg.get("gold_prices", [])
                mults = sg.get("multipliers", [])
                for it_idx, it in enumerate(sg.get("items", [])):
                    name = it.get("item_name", "?")
                    item_id = it.get("item_id")
                    cost_info = ""
                    if it_idx < len(prices):
                        p_val = f"{prices[it_idx]}g"
                        if it_idx < len(mults):
                            p_val += f", {mults[it_idx]}x"
                            cost_info = f" ({p_val})"
                    item_str = format_item_display(item_id, name, cost_info=cost_info, use_rich=True)
                    if is_done:
                        item_strs.append(f"[dim strike]{item_str}[/]")
                    else:
                        item_strs.append(item_str)

                sector_str = sg.get("map_sector") or "-"
                vendor_rarity = format_shady_rarity(sg.get("rarity", "-"), use_rich=True)
                if is_done:
                    rank_str = f"[dim strike]{i + 1}[/]"
                    vendor_rarity = f"[dim strike]{vendor_rarity}[/] [dim red][DONE][/]"
                    sector_str = f"[dim strike]{sector_str}[/]"
                    dist_str = f"[dim strike]{dist_str}[/]"
                else:
                    rank_str = str(i + 1)

                sg_table.add_row(
                    rank_str,
                    vendor_rarity,
                    sector_str,
                    dist_str,
                    ", ".join(item_strs),
                )

            console.print(sg_table)

        # 4. Microwaves Table
        if microwaves:
            micro_table = Table(
                title=f"Stage {stage_num} - Microwaves on Map ({len(microwaves)} found - Ranked by Distance)",
                header_style="bold bright_white",
            )
            micro_table.add_column("Rank", style="bold bright_white", justify="right")
            micro_table.add_column("Color / Tier", style="bold")
            micro_table.add_column("Distance", style="bright_white", justify="right")
            micro_table.add_column("Direction", style="bold bright_white")
            micro_table.add_column("Map Sector", style="bold white")
            micro_table.add_column("Uses Left", justify="right")

            for i, m in enumerate(microwaves, 1):
                dist_disp = f"{m['dist']}m" if m.get("dist") is not None else "-"
                rel = m.get("rel_dir")
                if rel:
                    dir_disp = f"{rel[0]} ({rel[1]}°)"
                else:
                    dir_disp = "-"
                c_style = m.get("style", "bright_white")
                rarity = m.get("rarity", 0)
                color_tier_str = f"[{c_style}]{m['color']} (Tier {rarity})[/]"
                sector_disp = m.get("map_sector") or "-"
                micro_table.add_row(
                    str(i),
                    color_tier_str,
                    dist_disp,
                    dir_disp,
                    sector_disp,
                    str(m.get("uses_left", 3)),
                )
            console.print(micro_table)

        render_active_powerups_block(powerup_data, use_rich=True)
        print("", flush=True)
        return

    # Plain text fallback
    print("\n" + "=" * 80, flush=True)
    print(f"[STAGE {stage_num} MAP OVERVIEW] (Scan took {result['elapsed_s']}s)", flush=True)
    print("=" * 80, flush=True)
    micro_list = microwaves
    if micro_list:
        micro_str_parts = []
        for m in micro_list:
            sec_str = f" @ {m['map_sector']}" if m.get("map_sector") else ""
            micro_str_parts.append(f"{m['color']}{sec_str}")
        micro_info = f" ({', '.join(micro_str_parts)})"
    else:
        micro_info = ""

    moais = result.get("moais", [])
    moai_dirs = [m["dir"] for m in moais if m.get("dir") and m["dir"] != "Unknown"]
    moais_detail = f"Moais: {counts.get('moai', 0)} ({', '.join(moai_dirs)})" if moai_dirs else f"Moais: {counts.get('moai', 0)}"
    print(f"  Shady + Moai:    {sm_total:>2d}  (Shady: {counts.get('shady', len(shady_guys))}, {moais_detail})", flush=True)
    print(f"  Microwaves:      {len(microwaves):>2d}{micro_info}", flush=True)
    boss_list = result.get("boss_curses", [])
    boss_dirs = [b["dir"] for b in boss_list if b.get("dir") and b["dir"] != "Unknown"]
    boss_detail = f" (Directions: {', '.join(boss_dirs)})" if boss_dirs else ""
    print(f"  Boss Curses:     {counts.get('boss_curses', 0):>2d}{boss_detail}", flush=True)
    print(f"  Magnet Curses:   {counts.get('magnets', 0):>2d}", flush=True)

    if shady_guys:
        ranked_items = get_all_shady_items_ranked(shady_guys)
        available_items = sum(1 for it in ranked_items if not it.get("shady_done"))
        avail_str = (
            f"{available_items}/{len(ranked_items)} available"
            if available_items < len(ranked_items)
            else f"{len(ranked_items)} items"
        )
        print("-" * 80, flush=True)
        print(f"🎯 STAGE {stage_num} - ALL SHADY ITEMS RANKED BY DISTANCE ({avail_str} across {len(shady_guys)} Shady Guys):", flush=True)
        print("-" * 80, flush=True)
        for item_rank, it in enumerate(ranked_items, 1):
            is_taken = it.get("shady_done", False)
            dist_str = f"{it['dist']}m" if it.get("dist") is not None else "??m"
            dir_str = f"{it['direction']} {it['bearing_str']}".strip() if it.get("direction") else ""
            loc_str = f"{dist_str} {dir_str}".strip()

            cost_parts = []
            if it.get("gold") is not None:
                cost_parts.append(f"{it['gold']}g")
            if it.get("multiplier") is not None:
                cost_parts.append(f"{it['multiplier']}x")
            cost_str = f"({', '.join(cost_parts)})" if cost_parts else ""

            item_id = it.get("item_id")
            name = it.get("item_name")
            if is_target_item(item_id, name):
                target_star = "*"
            elif is_highlighted_item(item_id, name):
                target_star = HIGHLIGHTED_ITEM_MARKER
            else:
                target_star = " "
            sec_str = f"[{it['map_sector']}]"
            sh_rarity = it.get("shady_rarity") or it.get("rarity", "")
            if is_taken:
                vendor_str = f"Shady #{it['shady_num']} [{sh_rarity}] [DONE]"
                item_disp = f"{it['item_name']}{target_star} [TAKEN]"
                line_out = f"  #{item_rank:>2d}  [{loc_str:<16}] {item_disp:<24} {cost_str:<16} @ {vendor_str} {sec_str}"
                print(f"\033[2;9m{line_out}\033[0m", flush=True)
            else:
                vendor_str = f"Shady #{it['shady_num']} [{sh_rarity}]"
                item_disp = f"{it['item_name']}{target_star}"
                print(f"  #{item_rank:>2d}  [{loc_str:<16}] {item_disp:<24} {cost_str:<16} @ {vendor_str} {sec_str}", flush=True)

            is_last_in_group = (
                item_rank == len(ranked_items)
                or ranked_items[item_rank]["shady_num"] != it["shady_num"]
            )
            if is_last_in_group and item_rank < len(ranked_items):
                print("  " + "-" * 76, flush=True)

        print("-" * 80, flush=True)
        available_sgs = sum(1 for sg in shady_guys if not sg.get("done"))
        sg_avail_str = (
            f"{available_sgs}/{len(shady_guys)} available"
            if available_sgs < len(shady_guys)
            else f"{len(shady_guys)} found on map"
        )
        print(f"STAGE {stage_num} - SHADY GUY INVENTORIES ({sg_avail_str} - Ranked by Distance):", flush=True)
        for i, sg in enumerate(shady_guys):
            is_done = sg.get("done", False)
            done_tag = " [DONE]" if is_done else ""
            prices = sg.get("gold_prices", [])
            mults = sg.get("multipliers", [])
            item_names = []
            for it_idx, it in enumerate(sg["items"]):
                name = it.get("item_name", "?")
                item_id = it.get("item_id")
                cost = ""
                if it_idx < len(prices):
                    cost = f" ({prices[it_idx]}g)"
                item_tag = "*" if is_target_item(item_id, name) else (HIGHLIGHTED_ITEM_MARKER if is_highlighted_item(item_id, name) else "")
                if is_done:
                    item_names.append(f"\033[2;9m{name}{item_tag}{cost} [TAKEN]\033[0m")
                else:
                    item_names.append(f"{name}{item_tag}{cost}")
            loc_parts = []
            if sg.get("map_sector"):
                loc_parts.append(f"Map: {sg['map_sector']}")
            if sg.get("rel_dir"):
                rel = sg["rel_dir"]
                loc_parts.append(f"{rel[2]}m {rel[0]}")
            elif sg.get("dist") is not None:
                loc_parts.append(f"{sg['dist']}m")
            loc_str = f" ({', '.join(loc_parts)})" if loc_parts else ""
            line_str = f"  Rank #{i+1} - Shady Guy [{sg.get('rarity', 'COMMON')}]{done_tag}{loc_str}: {', '.join(item_names)}"
            if is_done:
                print(f"\033[2;9m{line_str}\033[0m", flush=True)
            else:
                print(line_str, flush=True)

    if microwaves:
        print("-" * 80, flush=True)
        print(f"STAGE {stage_num} - MICROWAVES ON MAP ({len(microwaves)} found on map - Ranked by Distance):", flush=True)
        for i, m in enumerate(microwaves):
            dist_str = f"{m['dist']}m" if m.get("dist") is not None else "??m"
            rel = m.get("rel_dir")
            dir_str = f"{rel[0]} ({rel[1]}°)" if rel else ""
            loc_str = f"{dist_str} {dir_str}".strip()
            sec_str = f"[{m.get('map_sector', 'Unknown')}]"
            rarity = m.get("rarity", 0)
            uses_str = f"{m.get('uses_left', 3)} uses"
            print(f"  #{i+1:>2d}  [{loc_str:<16}] Microwave [{m['color']} / Tier {rarity}] {sec_str} ({uses_str})", flush=True)
    render_active_powerups_block(powerup_data, use_rich=False)
    print("=" * 80 + "\n", flush=True)


def is_game_window_active(memory: ProcessMemory) -> bool:
    """Check if Megabonk.exe is currently the foreground active window."""
    if win32gui is None or win32process is None:
        return True
    try:
        fg_window = win32gui.GetForegroundWindow()
        if not fg_window:
            return True
        _, fg_pid = win32process.GetWindowThreadProcessId(fg_window)
        fg_pid = int(fg_pid) & 0xFFFFFFFF
        game_pid = getattr(getattr(memory, "_pm", None), "process_id", None)
        if game_pid is not None:
            return fg_pid == (int(game_pid) & 0xFFFFFFFF)
    except Exception:
        pass
    return True


def wait_for_game_focus(memory: ProcessMemory) -> None:
    """Pause execution until the Megabonk game window is active."""
    if is_game_window_active(memory):
        return
    print("[WAIT] Megabonk is not focused. Auto-restart paused...", flush=True)
    while not is_game_window_active(memory):
        time.sleep(0.25)
    print("[+] Megabonk focused again. Resuming auto-restart.", flush=True)


# ==============================================================================
# In-Game Settings Reader (Rewired / Game Config)
# ==============================================================================
REWIRED_QUICK_RESET_ACTION_ID = 16

UNITY_KEY_MAP = {
    8: "backspace", 9: "tab", 12: "clear", 13: "enter", 19: "pause", 27: "esc",
    32: "space", 127: "delete",
    256: "0", 257: "1", 258: "2", 259: "3", 260: "4",
    261: "5", 262: "6", 263: "7", 264: "8", 265: "9",
    273: "up", 274: "down", 275: "right", 276: "left",
    277: "insert", 278: "home", 279: "end",
    280: "page up", 281: "page down",
    303: "right shift", 304: "shift",
    305: "right ctrl", 306: "ctrl",
    307: "right alt", 308: "alt",
}
for i in range(1, 13):
    UNITY_KEY_MAP[281 + i] = f"f{i}"


def unity_keycode_to_str(code: int) -> str:
    """Convert a Unity KeyCode integer to a keyboard-module key name."""
    if 97 <= code <= 122:
        return chr(code)
    if 48 <= code <= 57:
        return chr(code)
    if code in UNITY_KEY_MAP:
        return UNITY_KEY_MAP[code]
    if 32 <= code <= 126:
        return chr(code)
    return f"key_{code}"


def get_game_reset_hotkey() -> str:
    """Read the quick reset key binding directly from Megabonk's controller_config.json."""
    pattern = os.path.expandvars(
        r"%USERPROFILE%\AppData\LocalLow\Ved\Megabonk\Saves\CloudDir\*\controller_config.json"
    )
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    for p in files:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                if "ControllerMap|" in k and "controllerMapType=0" in k:
                    parsed = json.loads(v) if isinstance(v, str) else v
                    for bm in parsed.get("buttonMaps", []):
                        if bm.get("actionId") == REWIRED_QUICK_RESET_ACTION_ID and bm.get("enabled", True):
                            kc = bm.get("keyboardKeyCode", 0)
                            if kc > 0:
                                return unity_keycode_to_str(kc)
        except Exception:
            pass
    return "r"


def get_game_reset_duration(safety_margin: float = 0.05) -> float:
    """Read the quick reset hold time from Megabonk's config.json plus safety margin."""
    path = os.path.expandvars(
        r"%USERPROFILE%\AppData\LocalLow\Ved\Megabonk\Saves\LocalDir\config.json"
    )
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_time = data.get("cfGameSettings", {}).get("quick_reset_time")
            if raw_time is not None:
                parsed = float(raw_time)
                if math.isfinite(parsed) and parsed > 0:
                    return round(parsed + safety_margin, 2)
    except Exception:
        pass
    return 0.35


def perform_restart(
    hotkey: str,
    hold_duration: float,
    game_client: GameDataClient | None = None,
) -> bool:
    """Send the restart hotkey to restart the run, matching BonkScanner mechanics."""
    if keyboard is None:
        print("[-] 'keyboard' library not installed; cannot send restart key.", flush=True)
        return False
    try:
        if game_client:
            try:
                state = game_client.get_runtime_game_state()
                if state and state.is_paused:
                    print("[*] Game is paused. Dismissing pause menu before quick reset...", flush=True)
                    keyboard.press_and_release("esc")
                    time.sleep(0.12)
            except Exception:
                pass

        effective_hold = max(0.35, hold_duration)
        keyboard.press(hotkey)
        time.sleep(effective_hold)
        return True
    except Exception as exc:
        print(f"[-] Error sending restart key: {exc}", flush=True)
        return False
    finally:
        try:
            keyboard.release(hotkey)
        except Exception:
            pass


def pause_game(
    game_client: GameDataClient | None = None,
    pause_key: str = "esc",
    hold_duration: float = 0.05,
) -> bool:
    """Pause Megabonk by sending Escape if it is not already paused."""
    if game_client:
        try:
            state = game_client.get_runtime_game_state()
            if state and state.is_paused:
                print("[*] Game is already paused.", flush=True)
                return True
        except Exception:
            pass

    if keyboard is None:
        print("[-] 'keyboard' library not installed; cannot send pause key.", flush=True)
        return False

    try:
        print("[*] Perfect seed found! Pausing game (Escape)...", flush=True)
        keyboard.press(pause_key)
        time.sleep(hold_duration)
        keyboard.release(pause_key)
        time.sleep(0.1)

        if game_client:
            try:
                state = game_client.get_runtime_game_state()
                if state and state.is_paused:
                    print("[+] Game successfully paused!", flush=True)
                    return True
            except Exception:
                pass
        return True
    except Exception as exc:
        print(f"[-] Error sending pause key: {exc}", flush=True)
        return False
    finally:
        try:
            keyboard.release(pause_key)
        except Exception:
            pass




def save_seed_reroll_data(
    seed: int | str | None,
    scan_result: dict,
    reroll_num: int | None = None,
    file_path: Path = SEED_TRACKER_FILE,
) -> int:
    """Record comprehensive evaluation details, shrine counts, and Shady Guy offerings per re-roll.

    Captures all console report information (statuses, thresholds, counts, target items,
    coordinates, map sectors, distances) into a persistent JSON dataset.
    """
    if not scan_result or not scan_result.get("is_stage_1"):
        return 0

    seed_key = (
        str(seed)
        if seed is not None and str(seed).strip() not in ("", "?")
        else f"unknown_{int(time.time())}"
    )
    now_iso = datetime.now().isoformat(timespec="seconds")

    counts = scan_result.get("map_counts", {})
    shady_guys = scan_result.get("shady_guys", [])
    target_matches = scan_result.get("target_matches", [])

    # 1. Format target matches
    target_locations = []
    for m in target_matches:
        rel_str = (
            f"{m['dist']}m {m['direction']}"
            if m.get("direction") and m.get("dist") is not None
            else (f"{m['dist']}m" if m.get("dist") is not None else None)
        )
        sg = m.get("shady", {}) if isinstance(m.get("shady"), dict) else {}
        target_locations.append(
            {
                "item": m.get("item_name"),
                "item_id": m.get("item_id"),
                "shady_num": m.get("shady_num"),
                "slot": m.get("slot"),
                "gold": m.get("gold"),
                "multiplier": m.get("multiplier"),
                "rarity": sg.get("rarity"),
                "map_part": m.get("map_sector") or "Unknown",
                "coordinates": list(m["pos"]) if m.get("pos") else None,
                "distance_m": m.get("dist"),
                "direction_from_spawn": rel_str,
                "direction": m.get("direction"),
                "bearing_deg": m.get("bearing_deg"),
            }
        )

    # 2. Format all active Shady Guys
    all_shady_guys = []
    all_items_flat = []
    for i, sg in enumerate(shady_guys):
        rel = sg.get("rel_dir")
        rel_str = (
            f"{rel[2]}m {rel[0]}"
            if rel
            else (f"{sg['dist']}m" if sg.get("dist") is not None else None)
        )
        sg_item_names = []
        for it in sg.get("items", []):
            name = it.get("item_name") or get_item_name(it.get("item_id", -1))
            if name and name != "Unknown":
                sg_item_names.append(name)
                all_items_flat.append(name)

        all_shady_guys.append(
            {
                "shady_num": i + 1,
                "rarity": sg.get("rarity", "COMMON"),
                "map_part": sg.get("map_sector") or "Unknown",
                "coordinates": list(sg["pos"]) if sg.get("pos") else None,
                "distance_m": sg.get("dist"),
                "direction_from_spawn": rel_str,
                "direction": rel[0] if rel else None,
                "bearing_deg": rel[1] if rel else None,
                "items": sg_item_names,
                "gold_prices": sg.get("gold_prices", []),
                "multipliers": sg.get("multipliers", []),
            }
        )

    microwaves_serializable = [
        {
            "color": m.get("color", "White"),
            "rarity": m.get("rarity", 0),
            "map_sector": m.get("map_sector"),
            "coordinates": list(m["pos"]) if m.get("pos") else None,
            "distance_m": m.get("dist"),
            "direction": m["rel_dir"][0] if m.get("rel_dir") else None,
            "bearing_deg": m["rel_dir"][1] if m.get("rel_dir") else None,
            "direction_from_spawn": (
                f"{m['rel_dir'][2]}m {m['rel_dir'][0]}"
                if m.get("rel_dir")
                else (f"{m['dist']}m" if m.get("dist") is not None else None)
            ),
            "uses_left": m.get("uses_left", 3),
        }
        for m in scan_result.get("microwaves", [])
    ]

    moais_serializable = [
        {
            "direction": m.get("dir"),
            "coordinates": list(m["pos"]) if m.get("pos") else None,
            "distance_m": m.get("dist"),
        }
        for m in scan_result.get("moais", [])
    ]

    boss_curses_serializable = [
        {
            "direction": b.get("dir"),
            "coordinates": list(b["pos"]) if b.get("pos") else None,
            "distance_m": b.get("dist"),
        }
        for b in scan_result.get("boss_curses", [])
    ]

    # 3. Requirements breakdown matching console table
    requirements = {
        "shady_plus_moai": {
            "status": "PASS" if scan_result.get("sm_pass") else "FAIL",
            "passed": bool(scan_result.get("sm_pass")),
            "current": scan_result.get("sm_total", counts.get("shady", 0) + counts.get("moai", 0)),
            "required": THRESHOLD_SHADY_PLUS_MOAI,
            "shady_count": counts.get("shady", 0),
            "moai_count": counts.get("moai", 0),
            "moai_directions": [m["dir"] for m in scan_result.get("moais", []) if m.get("dir")],
        },
        "microwaves": {
            "status": "PASS" if scan_result.get("micro_pass") else "FAIL",
            "passed": bool(scan_result.get("micro_pass")),
            "current": counts.get("microwaves", 0),
            "required": THRESHOLD_MICROWAVES,
            "require_both_white": REQUIRE_BOTH_MICROWAVES_WHITE,
            "colors": [m.get("color", "White") for m in scan_result.get("microwaves", [])],
            "microwaves": microwaves_serializable,
        },
        "boss_curses": {
            "status": "PASS" if scan_result.get("boss_pass") else "FAIL",
            "passed": bool(scan_result.get("boss_pass")),
            "current": counts.get("boss_curses", 0),
            "required": THRESHOLD_BOSS_CURSES,
            "boss_directions": [b["dir"] for b in scan_result.get("boss_curses", []) if b.get("dir")],
            "boss_curses": boss_curses_serializable,
        },
        "magnet_curses": {
            "status": "PASS" if scan_result.get("magnet_pass") else "FAIL",
            "passed": bool(scan_result.get("magnet_pass")),
            "current": counts.get("magnets", 0),
            "required": THRESHOLD_MAGNET_CURSES,
        },
        "required_items": {
            "status": "PASS" if scan_result.get("target_items_pass") else "FAIL",
            "passed": bool(scan_result.get("target_items_pass")),
            "character": scan_result.get("character", "Unknown"),
            "character_id": scan_result.get("character_id"),
            "required_all_item_ids": scan_result.get("required_all_item_ids", REQUIRED_ALL_ITEM_IDS),
            "required_any_item_ids": scan_result.get("required_any_item_ids", REQUIRED_ANY_ITEM_IDS),
            "required_items_satisfied": bool(scan_result.get("required_items_satisfied", False)),
            "found_count": len(target_matches),
            "targets_sought": list(TARGET_SHADY_ITEMS.values()),
            "prices_found": [
                {
                    "item": m.get("item_name"),
                    "gold": m.get("gold"),
                    "multiplier": m.get("multiplier"),
                }
                for m in target_matches
            ],
            "skipped": bool(scan_result.get("shady_skipped", False)),
        },
    }

    entry = {
        "seed": seed if isinstance(seed, int) else (int(seed) if str(seed).isdigit() else seed_key),
        "reroll": reroll_num if reroll_num is not None else 0,
        "timestamp": now_iso,
        "character": scan_result.get("character", "Unknown"),
        "character_id": scan_result.get("character_id"),
        "elapsed_s": scan_result.get("elapsed_s", 0.0),
        "status": scan_result.get("match_reason", "PERFECT_MATCH" if scan_result.get("all_matched") else "CRITERIA_NOT_MET"),
        "all_matched": bool(scan_result.get("all_matched")),
        "requirements": requirements,
        "target_locations": target_locations,
        "items": all_items_flat,
        "shady_guys": all_shady_guys,
        "microwaves": microwaves_serializable,
        "moais": moais_serializable,
        "boss_curses": boss_curses_serializable,
    }

    data: dict[str, Any] = {}
    try:
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
    except Exception as exc:
        print(f"[-] Warning reading {file_path.name}: {exc}", flush=True)
        data = {}

    data[seed_key] = entry

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = file_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp_path.replace(file_path)
    except Exception as exc:
        print(f"[-] Error saving seed tracker to {file_path}: {exc}", flush=True)

    return len(data)




def analyze_seed_data(file_path: Path = SEED_TRACKER_FILE, clear_screen: bool = True) -> None:
    """Analyze the collected seed dataset using pandas and rich."""
    if clear_screen and CLEAR_CONSOLE_ON_OUTPUT:
        clear_console()

    if not file_path.exists():
        print(f"[-] No seed tracker file found at {file_path}", flush=True)
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        print(f"[-] Error reading {file_path}: {exc}", flush=True)
        return

    if not data:
        print(f"[*] {file_path.name} is empty. Record some seeds first!", flush=True)
        return

    if console and Panel and Table and pd:
        console.print(
            Panel(
                f"[bold cyan]Shady Guy Seed Dataset Analysis[/]\nFile: [yellow]{file_path.name}[/] | Total Seeds Tracked: [bold green]{len(data)}[/]",
                expand=False,
            )
        )

        item_records = []
        shady_records = []
        target_records = []
        microwave_records = []

        for seed, entry in data.items():
            if isinstance(entry, dict):
                for it in entry.get("items", []):
                    item_records.append({"seed": seed, "item": it})
                for sg in entry.get("shady_guys", []):
                    shady_records.append({"seed": seed, "map_part": sg.get("map_part"), "rarity": sg.get("rarity")})
                    prices = sg.get("gold_prices", [])
                    mults = sg.get("multipliers", [])
                    for i, it in enumerate(sg.get("items", [])):
                        it_name = it.get("item_name") if isinstance(it, dict) else str(it)
                        if it_name in TARGET_SHADY_ITEMS.values() or it_name in HIGHLIGHTED_SHADY_ITEMS.values():
                            target_records.append({
                                "seed": seed,
                                "item": it_name,
                                "map_part": sg.get("map_part"),
                                "gold": prices[i] if i < len(prices) else None,
                                "multiplier": mults[i] if i < len(mults) else None,
                            })
                micros = entry.get("microwaves", [])
                if not micros and "requirements" in entry:
                    micros = entry["requirements"].get("microwaves", {}).get("microwaves", [])
                for m in micros:
                    if isinstance(m, dict):
                        microwave_records.append({
                            "seed": seed,
                            "color": m.get("color", "Unknown"),
                            "rarity": m.get("rarity", "Unknown"),
                            "map_sector": m.get("map_sector", "Unknown"),
                        })
                if not micros and "requirements" in entry:
                    colors = entry["requirements"].get("microwaves", {}).get("colors", [])
                    for c in colors:
                        microwave_records.append({
                            "seed": seed,
                            "color": c,
                            "rarity": "Unknown",
                            "map_sector": "Unknown",
                        })
            elif isinstance(entry, list):
                for it in entry:
                    item_records.append({"seed": seed, "item": it})

        # Rerolls & Threshold Evaluation Statistics
        req_records = []
        for seed, entry in data.items():
            if isinstance(entry, dict) and "requirements" in entry:
                reqs = entry["requirements"]
                sm_info = reqs.get("shady_plus_moai", {})
                sm_cur = sm_info.get("current")
                sm_p = (sm_cur >= THRESHOLD_SHADY_PLUS_MOAI) if sm_cur is not None else sm_info.get("passed", False)
                micro_info = reqs.get("microwaves", {})
                if REQUIRE_BOTH_MICROWAVES_WHITE and "colors" in micro_info and micro_info["colors"]:
                    colors = micro_info["colors"]
                    micro_p = len(colors) >= THRESHOLD_MICROWAVES and all(c == "White" for c in colors)
                else:
                    micro_p = micro_info.get("passed", False)
                boss_info = reqs.get("boss_curses", {})
                boss_p = boss_info.get("passed", False)
                magnet_info = reqs.get("magnet_curses", {})
                magnet_p = magnet_info.get("passed", False)
                target_info = reqs.get("required_items", reqs.get("target_items", {}))
                target_p = target_info.get("passed", False)
                has_req = bool(REQUIRED_ALL_ITEM_IDS or REQUIRED_ANY_ITEM_IDS)
                all_p = sm_p and micro_p and boss_p and magnet_p and (target_p if has_req else True)

                req_records.append(
                    {
                        "seed": seed,
                        "reroll": entry.get("reroll", 0),
                        "all_matched": all_p,
                        "sm_pass": sm_p,
                        "micro_pass": micro_p,
                        "boss_pass": boss_p,
                        "magnet_pass": magnet_p,
                        "target_pass": target_p,
                    }
                )

        if req_records:
            df_req = pd.DataFrame(req_records)
            n_eval = len(df_req)
            table_eval = Table(
                title=f"Stage 1 Reroll Evaluation Summary ({n_eval} evaluations recorded)",
                header_style="bold bright_white",
            )
            table_eval.add_column("Evaluation Criterion", style="bold")
            table_eval.add_column("Passed", justify="right")
            table_eval.add_column("Failed", justify="right")
            table_eval.add_column("Pass Rate (%)", justify="right")
            micro_crit_label = (
                f"Microwaves (>= {THRESHOLD_MICROWAVES}, both White)"
                if REQUIRE_BOTH_MICROWAVES_WHITE
                else f"Microwaves (>= {THRESHOLD_MICROWAVES})"
            )
            req_all_names = [get_item_name(i) for i in REQUIRED_ALL_ITEM_IDS]
            req_any_names = [get_item_name(i) for i in REQUIRED_ANY_ITEM_IDS]
            parts = []
            if req_all_names:
                parts.append(f"ALL: {', '.join(req_all_names)}")
            if req_any_names:
                parts.append(f"ANY: {', '.join(req_any_names)}")
            target_crit_label = f"Required Items ({'; '.join(parts)})" if parts else "Required Items (None configured)"
            criteria = [
                (f"Shady + Moai (>= {THRESHOLD_SHADY_PLUS_MOAI})", "sm_pass"),
                (micro_crit_label, "micro_pass"),
                (f"Boss Curses (>= {THRESHOLD_BOSS_CURSES})", "boss_pass"),
                (f"Magnet Curses (>= {THRESHOLD_MAGNET_CURSES})", "magnet_pass"),
                (target_crit_label, "target_pass"),
                ("[bold]ALL CRITERIA MATCHED (Perfect Seed)[/]", "all_matched"),
            ]
            for label, col in criteria:
                passed = int(df_req[col].sum())
                failed = n_eval - passed
                pct = (passed / n_eval) * 100 if n_eval > 0 else 0.0
                table_eval.add_row(label, str(passed), str(failed), f"{pct:.1f}%")
            console.print(table_eval)

        if item_records:
            df_items = pd.DataFrame(item_records)
            table_items = Table(
                title=f"Top 10 Most Common Items ({len(df_items)} total offerings across {len(data)} seeds)",
                header_style="bold bright_white",
            )
            table_items.add_column("Rank", justify="right")
            table_items.add_column("Item Name")
            table_items.add_column("Offerings", justify="right")
            table_items.add_column("Frequency (%)", justify="right")
            for rank, (name, cnt) in enumerate(df_items["item"].value_counts().head(10).items(), start=1):
                name_styled = format_item_display(item_name=name, use_rich=True)
                table_items.add_row(str(rank), name_styled, str(cnt), f"{(cnt / len(df_items))*100:.1f}%")
            console.print(table_items)

            # Favoured Items Pricing & Spawn Statistics table
            target_names = list(TARGET_SHADY_ITEMS.values())
            table_targets = Table(title="Favoured Items Pricing & Spawn Statistics", header_style="bold bright_white")
            table_targets.add_column("Favoured Item")
            table_targets.add_column("Spawns", justify="right")
            table_targets.add_column("Min Gold", justify="right", style="bold bright_yellow")
            table_targets.add_column("Avg Gold", justify="right", style="bold bright_yellow")
            table_targets.add_column("Max Gold", justify="right", style="bold bright_yellow")
            table_targets.add_column("Multiplier Range", justify="right")
            table_targets.add_column("Seeds", justify="right")
            table_targets.add_column("Rate (%)", justify="right")

            df_targets = pd.DataFrame(target_records) if target_records else pd.DataFrame()

            for t_name in target_names:
                cnt = int((df_items["item"] == t_name).sum())
                seeds_with = df_items[df_items["item"] == t_name]["seed"].nunique() if cnt > 0 else 0
                pct = (seeds_with / len(data)) * 100 if len(data) > 0 else 0.0

                min_price_str = "-"
                avg_price_str = "-"
                max_price_str = "-"
                range_str = "-"

                if not df_targets.empty and "item" in df_targets.columns and "gold" in df_targets.columns:
                    t_rows = df_targets[(df_targets["item"] == t_name) & df_targets["gold"].notna()]
                    if not t_rows.empty:
                        golds = t_rows["gold"].astype(float)
                        mults = t_rows["multiplier"].dropna().astype(float) if "multiplier" in t_rows.columns else []
                        min_g = int(golds.min())
                        max_g = int(golds.max())
                        avg_g = round(golds.mean(), 1)
                        min_price_str = f"{min_g}g"
                        avg_price_str = f"{avg_g}g"
                        max_price_str = f"{max_g}g"
                        if len(mults) > 0:
                            min_m = mults.min()
                            max_m = mults.max()
                            range_str = f"{min_m:.2f}x - {max_m:.2f}x"
                        else:
                            range_str = "-"

                name_styled = format_item_display(item_name=t_name, use_rich=True)
                table_targets.add_row(
                    name_styled,
                    str(cnt),
                    min_price_str,
                    avg_price_str,
                    max_price_str,
                    range_str,
                    str(seeds_with),
                    f"{pct:.1f}%",
                )
            console.print(table_targets)

            # Highlighted Items Pricing & Spawn Statistics table
            highlight_names = list(HIGHLIGHTED_SHADY_ITEMS.values())
            table_highlights = Table(title="Highlighted Items Pricing & Spawn Statistics", header_style="bold bright_white")
            table_highlights.add_column("Highlighted Item")
            table_highlights.add_column("Spawns", justify="right")
            table_highlights.add_column("Min Gold", justify="right", style="bold bright_yellow")
            table_highlights.add_column("Avg Gold", justify="right", style="bold bright_yellow")
            table_highlights.add_column("Max Gold", justify="right", style="bold bright_yellow")
            table_highlights.add_column("Multiplier Range", justify="right")
            table_highlights.add_column("Seeds", justify="right")
            table_highlights.add_column("Rate (%)", justify="right")

            for h_name in highlight_names:
                cnt = int((df_items["item"] == h_name).sum())
                seeds_with = df_items[df_items["item"] == h_name]["seed"].nunique() if cnt > 0 else 0
                pct = (seeds_with / len(data)) * 100 if len(data) > 0 else 0.0

                min_price_str = "-"
                avg_price_str = "-"
                max_price_str = "-"
                range_str = "-"

                if not df_targets.empty and "item" in df_targets.columns and "gold" in df_targets.columns:
                    h_rows = df_targets[(df_targets["item"] == h_name) & df_targets["gold"].notna()]
                    if not h_rows.empty:
                        golds = h_rows["gold"].astype(float)
                        mults = h_rows["multiplier"].dropna().astype(float) if "multiplier" in h_rows.columns else []
                        min_g = int(golds.min())
                        max_g = int(golds.max())
                        avg_g = round(golds.mean(), 1)
                        min_price_str = f"{min_g}g"
                        avg_price_str = f"{avg_g}g"
                        max_price_str = f"{max_g}g"
                        if len(mults) > 0:
                            min_m = mults.min()
                            max_m = mults.max()
                            range_str = f"{min_m:.2f}x - {max_m:.2f}x"
                        else:
                            range_str = "-"

                name_styled = format_item_display(item_name=h_name, use_rich=True)
                table_highlights.add_row(
                    name_styled,
                    str(cnt),
                    min_price_str,
                    avg_price_str,
                    max_price_str,
                    range_str,
                    str(seeds_with),
                    f"{pct:.1f}%",
                )
            console.print(table_highlights)

        if shady_records:
            df_sg = pd.DataFrame(shady_records)
            table_sectors = Table(title="Shady Guy Map Sector Distribution", header_style="bold bright_white")
            table_sectors.add_column("Map Sector", style="bold")
            table_sectors.add_column("Spawns", justify="right")
            table_sectors.add_column("Share (%)", justify="right")
            for sector, cnt in df_sg["map_part"].value_counts().items():
                table_sectors.add_row(str(sector), str(cnt), f"{(cnt / len(df_sg))*100:.1f}%")
            console.print(table_sectors)

        if microwave_records:
            df_micro = pd.DataFrame(microwave_records)
            table_micro = Table(
                title=f"Microwave Color Distribution ({len(df_micro)} microwaves recorded across {df_micro['seed'].nunique()} seeds)",
                header_style="bold bright_white",
            )
            table_micro.add_column("Microwave Color / Tier", style="bold")
            table_micro.add_column("Count", justify="right")
            table_micro.add_column("Share (%)", justify="right")
            for col_val, cnt in df_micro["color"].value_counts().items():
                pct = (cnt / len(df_micro)) * 100
                style = ""
                if col_val == "Gold":
                    style = "[bold yellow]Gold (Tier 3)[/]"
                elif col_val == "Purple":
                    style = "[bold magenta]Purple (Tier 2)[/]"
                elif col_val == "Blue":
                    style = "[bold cyan]Blue (Tier 1)[/]"
                elif col_val == "White":
                    style = "[bright_white]White (Tier 0)[/]"
                else:
                    style = str(col_val)
                table_micro.add_row(style, str(cnt), f"{pct:.1f}%")
            console.print(table_micro)
    else:
        print(f"\n[*] Seed Dataset Analysis for {file_path.name}: {len(data)} seeds tracked.", flush=True)
        all_items = []
        for v in data.values():
            if isinstance(v, dict):
                all_items.extend(v.get("items", []))
            elif isinstance(v, list):
                all_items.extend(v)
        from collections import Counter
        counts = Counter(all_items).most_common(10)
        print("Top 10 items:", counts, flush=True)

        if target_records:
            print("\nFavoured Items Pricing Summary:", flush=True)
            for t_name in TARGET_SHADY_ITEMS.values():
                t_golds = [r["gold"] for r in target_records if r.get("item") == t_name and r.get("gold") is not None]
                if t_golds:
                    print(f"  {t_name}: Min {min(t_golds)}g, Avg {sum(t_golds)/len(t_golds):.1f}g, Max {max(t_golds)}g ({len(t_golds)} spawns)", flush=True)
                else:
                    print(f"  {t_name}: No spawns recorded yet", flush=True)

        if target_records:
            print("\nHighlighted Items Pricing Summary:", flush=True)
            for h_name in HIGHLIGHTED_SHADY_ITEMS.values():
                h_golds = [r["gold"] for r in target_records if r.get("item") == h_name and r.get("gold") is not None]
                if h_golds:
                    print(f"  {h_name}: Min {min(h_golds)}g, Avg {sum(h_golds)/len(h_golds):.1f}g, Max {max(h_golds)}g ({len(h_golds)} spawns)", flush=True)
                else:
                    print(f"  {h_name}: No spawns recorded yet", flush=True)

        if microwave_records:
            print(f"\nMicrowave Color Distribution ({len(microwave_records)} recorded):", flush=True)
            from collections import Counter
            m_counts = Counter(r["color"] for r in microwave_records)
            for c, cnt in m_counts.items():
                print(f"  {c}: {cnt} ({(cnt/len(microwave_records))*100:.1f}%)", flush=True)


def main():
    if any(arg in sys.argv for arg in ("--analyze", "-a", "analyze")):
        analyze_seed_data()
        return

    global REQUIRED_ALL_ITEM_IDS, REQUIRED_ANY_ITEM_IDS

    # Parse REQUIRED_ALL_ITEM_IDS and REQUIRED_ANY_ITEM_IDS from CLI / env
    if "--no-required-items" in sys.argv:
        REQUIRED_ALL_ITEM_IDS = []
        REQUIRED_ANY_ITEM_IDS = []

    # REQUIRED_ALL_ITEM_IDS (--required-all-items, --must-have-items)
    if any(arg.startswith(("--required-all-items=", "--must-have-items=", "--required-all-item-ids=")) for arg in sys.argv):
        for arg in sys.argv:
            if arg.startswith(("--required-all-items=", "--must-have-items=", "--required-all-item-ids=")):
                val = arg.split("=", 1)[1].strip()
                try:
                    REQUIRED_ALL_ITEM_IDS = [int(x.strip()) for x in val.split(",") if x.strip().isdigit()]
                except Exception:
                    pass
    elif any(arg in sys.argv for arg in ("--required-all-items", "--must-have-items", "--required-all-item-ids")):
        for i, arg in enumerate(sys.argv):
            if arg in ("--required-all-items", "--must-have-items", "--required-all-item-ids") and i + 1 < len(sys.argv):
                val = sys.argv[i + 1].strip()
                try:
                    REQUIRED_ALL_ITEM_IDS = [int(x.strip()) for x in val.split(",") if x.strip().isdigit()]
                except Exception:
                    pass
                break
    elif "REQUIRED_ALL_ITEM_IDS" in os.environ or "MUST_HAVE_ITEM_IDS" in os.environ:
        raw_env = (os.environ.get("REQUIRED_ALL_ITEM_IDS") or os.environ.get("MUST_HAVE_ITEM_IDS", "")).strip()
        cleaned = raw_env.strip("[]() ")
        if cleaned:
            try:
                REQUIRED_ALL_ITEM_IDS = [int(x.strip()) for x in cleaned.split(",") if x.strip().isdigit()]
            except Exception:
                pass
        else:
            REQUIRED_ALL_ITEM_IDS = []

    # REQUIRED_ANY_ITEM_IDS (--required-any-items, --any-items)
    if any(arg.startswith(("--required-any-items=", "--any-items=", "--required-any-item-ids=")) for arg in sys.argv):
        for arg in sys.argv:
            if arg.startswith(("--required-any-items=", "--any-items=", "--required-any-item-ids=")):
                val = arg.split("=", 1)[1].strip()
                try:
                    REQUIRED_ANY_ITEM_IDS = [int(x.strip()) for x in val.split(",") if x.strip().isdigit()]
                except Exception:
                    pass
    elif any(arg in sys.argv for arg in ("--required-any-items", "--any-items", "--required-any-item-ids")):
        for i, arg in enumerate(sys.argv):
            if arg in ("--required-any-items", "--any-items", "--required-any-item-ids") and i + 1 < len(sys.argv):
                val = sys.argv[i + 1].strip()
                try:
                    REQUIRED_ANY_ITEM_IDS = [int(x.strip()) for x in val.split(",") if x.strip().isdigit()]
                except Exception:
                    pass
                break
    elif "REQUIRED_ANY_ITEM_IDS" in os.environ or "ANY_OF_ITEM_IDS" in os.environ:
        raw_env = (os.environ.get("REQUIRED_ANY_ITEM_IDS") or os.environ.get("ANY_OF_ITEM_IDS", "")).strip()
        cleaned = raw_env.strip("[]() ")
        if cleaned:
            try:
                REQUIRED_ANY_ITEM_IDS = [int(x.strip()) for x in cleaned.split(",") if x.strip().isdigit()]
            except Exception:
                pass
        else:
            REQUIRED_ANY_ITEM_IDS = []


    print(f"[*] Attaching to {PROCESS_NAME}...", flush=True)
    try:
        memory = ProcessMemory(PROCESS_NAME)
    except Exception as exc:
        print(f"[-] Could not attach to {PROCESS_NAME}: {exc}", flush=True)
        return

    module_base = memory.module_base_address(MODULE_NAME)
    print(f"[+] Connected! GameAssembly.dll: 0x{module_base:X}", flush=True)

    marker_client = None
    try:
        marker_client = MapMarkerMemoryClient(memory=memory)
    except Exception:
        pass

    game_client = None
    try:
        game_client = GameDataClient(memory=memory)
    except Exception:
        pass

    # Resolve Quick Reset key and hold duration from game settings or overrides
    reset_hotkey = (
        get_game_reset_hotkey()
        if (READ_SETTINGS_FROM_GAME and MANUAL_RESET_HOTKEY is None)
        else (MANUAL_RESET_HOTKEY or "r")
    )
    reset_hold_duration = (
        get_game_reset_duration()
        if (READ_SETTINGS_FROM_GAME and MANUAL_HOLD_DURATION is None)
        else (MANUAL_HOLD_DURATION or 0.35)
    )

    auto_restart_active = AUTO_RESTART_ON_FAIL
    user_toggled_off = not AUTO_RESTART_ON_FAIL
    reroll_count = 0

    if keyboard and HOTKEY_TOGGLE_AUTORESTART:
        def toggle_autorestart():
            nonlocal auto_restart_active, user_toggled_off
            auto_restart_active = not auto_restart_active
            user_toggled_off = not auto_restart_active
            status = "ENABLED [ON]" if auto_restart_active else "DISABLED [OFF]"
            print(f"\n[***] Auto-Restart is now {status} (Press {HOTKEY_TOGGLE_AUTORESTART.upper()} to toggle) [***]\n", flush=True)

        try:
            keyboard.add_hotkey(HOTKEY_TOGGLE_AUTORESTART, toggle_autorestart)
        except Exception:
            pass

    print("[*] Stage 1 Seed Filter ready!", flush=True)
    if TRACK_SEED_OFFERINGS:
        print(f"[*] Seed Offerings Tracker: ACTIVE -> {SEED_TRACKER_FILE.name}", flush=True)
    pause_mode_str = "ENABLED (Escape)" if PAUSE_GAME_ON_MATCH else "DISABLED"
    print(f"[*] Pause on Match: {pause_mode_str}", flush=True)

    banner_parts = []
    if REQUIRED_ALL_ITEM_IDS:
        all_names = [get_item_name(i) for i in REQUIRED_ALL_ITEM_IDS]
        banner_parts.append(f"ALL (Must-have): {', '.join(all_names)} [IDs: {REQUIRED_ALL_ITEM_IDS}]")
    if REQUIRED_ANY_ITEM_IDS:
        any_names = [get_item_name(i) for i in REQUIRED_ANY_ITEM_IDS]
        banner_parts.append(f"ANY (At least 1): {', '.join(any_names)} [IDs: {REQUIRED_ANY_ITEM_IDS}]")

    if banner_parts:
        print(f"[*] Required Items: ENABLED ({' | '.join(banner_parts)})", flush=True)
    else:
        print("[*] Required Items: DISABLED (Shrine thresholds only)", flush=True)
    restart_mode_str = f"ENABLED (Press {HOTKEY_TOGGLE_AUTORESTART.upper()} to toggle)" if auto_restart_active else "DISABLED"
    print(f"[*] Auto-Restart on fail: {restart_mode_str}\n", flush=True)

    heartbeat_time = 0
    scanned_stage_key = None
    cached_character: tuple[int, str] | None = None
    active_stage_report: dict | None = None
    last_shady_poll_time = 0.0
    last_powerup_poll_time = 0.0
    powerup_tracker = PowerupDisplayTracker(console_obj=console)

    while True:
        time.sleep(0.05)
        now = time.time()

        player = 0

        try:
            type_info = memory.read_ptr(module_base + MY_PLAYER_TYPE_INFO_OFFSET)
            if type_info:
                static_fields = memory.read_ptr(type_info + CLASS_STATIC_FIELDS_OFFSET)
                if static_fields:
                    player = memory.read_ptr(static_fields + MY_PLAYER_INSTANCE_OFFSET)
        except Exception:
            pass

        # Check map state from GameDataClient
        map_state = None
        current_seed = None
        if game_client:
            try:
                map_state = game_client.get_map_generation_state()
                current_seed = map_state.map_seed
            except Exception:
                pass

        stage_idx = (
            map_state.stage_index
            if map_state and map_state.stage_index is not None
            else get_stage_index(memory, module_base)
        )

        scan_key = (current_seed, stage_idx) if current_seed is not None else (player, stage_idx)
        map_ready = (
            map_state.has_loaded_map and not map_state.is_generating and not map_state.is_resetting
            if map_state
            else bool(player)
        )

        # Check if new run / stage started -> trigger Stage 1 evaluation
        if map_ready and scan_key != scanned_stage_key:
            powerup_tracker.reset()
            scanned_stage_key = scan_key
            active_stage_report = None
            char_info = get_character_identity(memory, module_base)
            if char_info:
                cached_character = char_info

            if stage_idx == 0:
                is_fresh_run = not auto_restart_active or reroll_count == 0
                if is_fresh_run:
                    # Give Unity's main thread a brief window to complete Awake/Start on newly
                    # instantiated prefabs (mirrors the settling time built into auto-rerolls)
                    time.sleep(0.05)
                    if cached_character is None:
                        cached_character = get_character_identity(memory, module_base)

                if CLEAR_CONSOLE_ON_OUTPUT:
                    clear_console()

                if AUTO_RESTART_ON_FAIL and not user_toggled_off and not auto_restart_active:
                    auto_restart_active = True
                    reroll_count = 0
                    print(f"[*] New run detected ({current_seed}). Auto-restart re-armed!", flush=True)

                reroll_label = reroll_count if auto_restart_active else None
                seed_str = f"Seed: {current_seed}" if current_seed is not None else f"Player: 0x{player:X}"
                char_str = f" | Char: {cached_character[1]}" if cached_character else ""
                print(f"[+] Stage 1 active ({seed_str}{char_str})! Evaluating seed...", flush=True)
                scan_res = scan_stage1_seed_filter(
                    memory,
                    module_base,
                    marker_client=marker_client,
                    game_client=game_client,
                    fast_eval=FAST_EVALUATION and auto_restart_active,
                    character=cached_character,
                )
                if scan_res.get("character") and scan_res.get("character") != "Unknown":
                    cached_character = (scan_res.get("character_id"), scan_res.get("character"))
                try:
                    pu_data = read_active_powerups(memory, module_base)
                except Exception:
                    pu_data = None
                print_stage1_report(scan_res, reroll_num=reroll_label, powerup_data=pu_data)

                if TRACK_SEED_OFFERINGS:
                    total_seeds = save_seed_reroll_data(
                        current_seed,
                        scan_res,
                        reroll_num=reroll_count if auto_restart_active else 0,
                    )
                    reroll_tag = f"Reroll #{reroll_count}" if (auto_restart_active and reroll_count > 0) else "Initial scan"
                    seed_disp = f"Seed {current_seed}" if current_seed is not None else "Unknown Seed"
                    print(f"[*] Recorded {reroll_tag} ({seed_disp}) to {SEED_TRACKER_FILE.name} (Total entries: {total_seeds})", flush=True)

                if scan_res.get("shady_guys"):
                    active_stage_report = scan_res

                if scan_res["all_matched"]:
                    reason = scan_res.get("match_reason")
                    if reason == "PERFECT_MATCH_ALL":
                        parts = []
                        if scan_res.get("required_all_item_ids"):
                            r_names = [get_item_name(i) for i in scan_res["required_all_item_ids"]]
                            parts.append(f"ALL: {', '.join(r_names)}")
                        if scan_res.get("required_any_item_ids"):
                            r_names = [get_item_name(i) for i in scan_res["required_any_item_ids"]]
                            parts.append(f"ANY: {', '.join(r_names)}")

                        items_str = f" + Required Items ({'; '.join(parts)})" if parts else ""
                        print(f"🎉 [PERFECT SEED FOUND (Thresholds{items_str})!] Stopping auto-restart. Enjoy your run!\n", flush=True)
                    else:
                        print("🎉 [PERFECT SEED FOUND (Thresholds Met)!] Stopping auto-restart. Enjoy your run!\n", flush=True)

                    auto_restart_active = False
                    if PAUSE_GAME_ON_MATCH:
                        pause_game(game_client=game_client)
                elif auto_restart_active:
                    if MAX_REROLLS > 0 and reroll_count >= MAX_REROLLS:
                        print(f"[*] Reached max rerolls ({MAX_REROLLS}). Auto-restart stopped.\n", flush=True)
                        auto_restart_active = False
                    else:
                        if REQUIRE_GAME_WINDOW_FOCUS:
                            wait_for_game_focus(memory)
                        reroll_count += 1
                        print(f"[*] Criteria not met. Auto-restarting Stage 1 (Reroll #{reroll_count})...\n", flush=True)
                        last_state = map_state or (game_client.get_map_generation_state() if game_client else None)
                        perform_restart(reset_hotkey, reset_hold_duration, game_client=game_client)
                        if game_client and last_state:
                            try:
                                game_client.wait_for_map_ready(
                                    previous_state=last_state,
                                    require_change=True,
                                    timeout=10.0,
                                )
                                time.sleep(0.05)
                            except TimeoutError:
                                time.sleep(1.0)
                            except Exception:
                                time.sleep(1.0)
                        else:
                            time.sleep(1.5)

            elif stage_idx > 0:
                if CLEAR_CONSOLE_ON_OUTPUT:
                    clear_console()
                stage_num = stage_idx + 1
                seed_str = f"Seed: {current_seed}" if current_seed is not None else f"Player: 0x{player:X}"
                char_str = f" | Char: {cached_character[1]}" if cached_character else ""
                print(f"[+] Stage {stage_num} active ({seed_str}{char_str})! Scanning Shady Guys and Microwaves...", flush=True)
                scan_res = scan_stage_inspect(
                    memory,
                    module_base,
                    marker_client=marker_client,
                    game_client=game_client,
                    stage_idx=stage_idx,
                    character=cached_character,
                )
                if scan_res.get("character") and scan_res.get("character") != "Unknown":
                    cached_character = (scan_res.get("character_id"), scan_res.get("character"))
                active_stage_report = scan_res
                try:
                    pu_data = read_active_powerups(memory, module_base)
                except Exception:
                    pu_data = None
                print_stage_inspect_report(scan_res, powerup_data=pu_data)

        # Check for Shady Guy purchases during active gameplay
        if active_stage_report and active_stage_report.get("shady_guys") and (now - last_shady_poll_time >= 0.25):
            last_shady_poll_time = now
            shady_state_changed = False
            for sg in active_stage_report["shady_guys"]:
                if sg.get("done", False):
                    continue
                ptr = sg.get("ptr")
                if ptr:
                    if is_shady_guy_done(memory, ptr, sg_dict=sg, marker_client=marker_client):
                        sg["done"] = True
                        shady_state_changed = True
            if shady_state_changed:
                if CLEAR_CONSOLE_ON_OUTPUT:
                    clear_console()
                s_num = active_stage_report.get("stage_num", active_stage_report.get("stage_index", 0) + 1)
                print(f"[*] Shady Guy item taken! Updated Stage {s_num} status:\n", flush=True)
                try:
                    pu_data = read_active_powerups(memory, module_base)
                except Exception:
                    pu_data = None
                if active_stage_report.get("is_stage_1"):
                    print_stage1_report(active_stage_report, reroll_num=None, powerup_data=pu_data)
                else:
                    print_stage_inspect_report(active_stage_report, powerup_data=pu_data)
                powerup_tracker.on_console_cleared()

        # Check for active power-ups and Za Warudo during active gameplay
        if (map_ready or player) and (now - last_powerup_poll_time >= 0.15):
            last_powerup_poll_time = now
            try:
                pu_data = read_active_powerups(memory, module_base)
                powerup_tracker.update(pu_data)
            except Exception:
                pass

        # Heartbeat every 5 seconds if idle
        if now - heartbeat_time > 5.0:
            heartbeat_time = now
            if not player and not (map_state and map_state.has_loaded_map):
                print("[*] Waiting for active game/player...", flush=True)
                powerup_tracker.on_other_print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        clear_live_line()
        print("\n[*] Exiting.", flush=True)

