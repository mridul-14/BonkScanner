"""Diagnostic memory inspection tool for Megabonk interactables.

This script checks both:
1. The global interactables dictionary (Moais, Shady Guy containers)
2. The player's proximity sensor (DetectInteractables)
"""

from __future__ import annotations

import os
import struct
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.item_metadata import ITEM_DISPLAY_NAME_BY_RAW_VALUE, ITEM_ENUM_NAMES_BY_ID
from infra.memory.reader import MemoryReadError, ProcessMemory

PROCESS_NAME = "Megabonk.exe"
MODULE_NAME = "GameAssembly.dll"

# Static TypeInfo offsets in GameAssembly.dll
MY_PLAYER_TYPE_INFO_OFFSET = 0x2F620F8
INTERACTABLES_DICT_TYPE_INFO_OFFSET = 0x2FB5E68

CLASS_STATIC_FIELDS_OFFSET = 0xB8
MY_PLAYER_INSTANCE_OFFSET = 0x00
PLAYER_INPUT_OFFSET = 0x48
DETECT_INTERACTABLES_OFFSET = 0x20
CURRENT_INTERACTABLE_OFFSET = 0x28

OBJECT_KLASS_OFFSET = 0x00
CLASS_NAME_POINTER_OFFSET = 0x10


def read_class_name(memory: ProcessMemory, object_ptr: int) -> str | None:
    if not object_ptr or object_ptr < 0x10000:
        return None
    try:
        class_ptr = memory.read_ptr(object_ptr + OBJECT_KLASS_OFFSET)
        if not class_ptr or class_ptr < 0x10000:
            return None
        name_ptr = memory.read_ptr(class_ptr + CLASS_NAME_POINTER_OFFSET)
        if not name_ptr or name_ptr < 0x10000:
            return None
        return memory.read_ascii_string(name_ptr, max_length=64)
    except Exception:
        return None


def inspect_raw_memory(memory: ProcessMemory, object_ptr: int, scan_bytes: int = 0x120, title: str = "") -> None:
    class_name = read_class_name(memory, object_ptr) or "UnknownClass"
    print("=" * 80)
    print(f"OBJECT DUMP: {title or class_name} at 0x{object_ptr:X} (Class: {class_name})")
    print("=" * 80)
    print(f"{'Offset':<8} {'Hex Value':<18} {'Int32':<12} {'Float':<10} {'Interpretation'}")
    print("-" * 80)

    for offset in range(0, scan_bytes, 8):
        try:
            val_ptr = memory.read_ptr(object_ptr + offset)
            val_i32_a = memory.read_i32(object_ptr + offset)
            val_i32_b = memory.read_i32(object_ptr + offset + 4)
            val_flt_a = memory.read_float(object_ptr + offset)
        except Exception:
            continue

        details = []

        # Check for item matches
        for i32_val, sub_off in ((val_i32_a, offset), (val_i32_b, offset + 4)):
            if 0 <= i32_val <= 90 and i32_val in ITEM_ENUM_NAMES_BY_ID:
                raw_enum = ITEM_ENUM_NAMES_BY_ID[i32_val]
                display_name = ITEM_DISPLAY_NAME_BY_RAW_VALUE.get(raw_enum, raw_enum)
                details.append(f"[item_id={i32_val}: {display_name}] at +0x{sub_off:02X}")

        # Check if val_ptr points to an object
        if val_ptr > 0x10000:
            target_class = read_class_name(memory, val_ptr)
            if target_class:
                details.append(f"-> {target_class}")
                try:
                    length = memory.read_i32(val_ptr + 0x18)
                    if 0 < length <= 32:
                        details.append(f"(len={length})")
                        for idx in range(min(length, 6)):
                            elem_ptr = memory.read_ptr(val_ptr + 0x20 + (idx * 8))
                            elem_i32 = memory.read_i32(val_ptr + 0x20 + (idx * 8))
                            elem_cls = read_class_name(memory, elem_ptr)
                            if elem_cls:
                                details.append(f"[{idx}]->{elem_cls}")
                            elif elem_i32 in ITEM_ENUM_NAMES_BY_ID:
                                iname = ITEM_ENUM_NAMES_BY_ID[elem_i32]
                                details.append(f"[{idx}]={iname}")
                except Exception:
                    pass
            else:
                mono_str = memory.read_mono_string(val_ptr, max_length=48)
                if mono_str:
                    details.append(f'-> "{mono_str}"')

        flt_str = f"{val_flt_a:.2f}" if abs(val_flt_a) < 1e5 else "---"
        details_str = "; ".join(details)
        print(f"+0x{offset:02X}:    0x{val_ptr:016X}  {val_i32_a:<12} {flt_str:<10} {details_str}")

    print("=" * 80)
    print()


def inspect_global_interactables(memory: ProcessMemory, module_base: int) -> dict[str, int]:
    """Inspect the game's global interactables dictionary."""
    found_containers = {}
    try:
        type_info_address = module_base + INTERACTABLES_DICT_TYPE_INFO_OFFSET
        class_ptr = memory.read_ptr(type_info_address)
        if not class_ptr:
            return found_containers
        static_fields = memory.read_ptr(class_ptr + CLASS_STATIC_FIELDS_OFFSET)
        if not static_fields:
            return found_containers
        dict_ptr = memory.read_ptr(static_fields + 0x0)
        if not dict_ptr:
            return found_containers

        entries = memory.read_ptr(dict_ptr + 0x18)
        count = memory.read_i32(dict_ptr + 0x20)
        if count <= 0 or count > 1024 or not entries:
            return found_containers

        for i in range(count):
            entry = entries + 0x20 + (i * 0x18)
            key_ptr = memory.read_ptr(entry + 0x8)
            val_ptr = memory.read_ptr(entry + 0x10)
            if not key_ptr or not val_ptr:
                continue
            label = memory.read_mono_string(key_ptr)
            if label:
                found_containers[label] = val_ptr

    except Exception:
        pass
    return found_containers


def main():
    print(f"[*] Attaching to {PROCESS_NAME}...")
    try:
        memory = ProcessMemory(PROCESS_NAME)
    except Exception as exc:
        print(f"[-] Could not attach to {PROCESS_NAME}: {exc}")
        print("    Please launch Megabonk and make sure you are in a match.")
        return

    module_base = memory.module_base_address(MODULE_NAME)
    print(f"[+] Connected to Megabonk! GameAssembly.dll: 0x{module_base:X}\n")

    last_player = 0
    last_current_interactable = 0
    inspected_containers = set()
    heartbeat_time = 0

    print("[*] Diagnostic monitor running...")
    print("    Checking both the Global Interactables Dictionary and Player Proximity Sensor.")
    print("    Press Ctrl+C to exit.\n")

    while True:
        time.sleep(0.2)
        now = time.time()

        # 1. Check Global Interactables Dictionary
        containers = inspect_global_interactables(memory, module_base)
        if containers:
            for target_name in ("Moais", "Shady Guy"):
                if target_name in containers and target_name not in inspected_containers:
                    inspected_containers.add(target_name)
                    c_ptr = containers[target_name]
                    c_class = read_class_name(memory, c_ptr) or "Container"
                    print(f"\n[!] Found global container for '{target_name}': 0x{c_ptr:X} ({c_class})")
                    inspect_raw_memory(memory, c_ptr, scan_bytes=0x80, title=f"Global Container: {target_name}")

        # 2. Check Player Detector
        player = 0
        detector = 0
        current_interactable = 0
        debug_status = ""

        try:
            type_info = memory.read_ptr(module_base + MY_PLAYER_TYPE_INFO_OFFSET)
            if not type_info:
                debug_status = "MyPlayer_TypeInfo is null"
            else:
                static_fields = memory.read_ptr(type_info + CLASS_STATIC_FIELDS_OFFSET)
                if not static_fields:
                    debug_status = "MyPlayer static fields null"
                else:
                    player = memory.read_ptr(static_fields + MY_PLAYER_INSTANCE_OFFSET)
                    if not player:
                        debug_status = "MyPlayer.Instance is null (are you in a match?)"
                    else:
                        player_input = memory.read_ptr(player + PLAYER_INPUT_OFFSET)
                        if not player_input:
                            debug_status = "PlayerInput is null"
                        else:
                            detector = memory.read_ptr(player_input + DETECT_INTERACTABLES_OFFSET)
                            if not detector:
                                debug_status = "DetectInteractables is null"
                            else:
                                current_interactable = memory.read_ptr(detector + CURRENT_INTERACTABLE_OFFSET)
        except Exception as e:
            debug_status = f"Read error: {e}"

        if player != last_player:
            last_player = player
            if player:
                print(f"[+] Player resolved at 0x{player:X}, detector at 0x{detector:X}")
            else:
                print(f"[-] Player lost: {debug_status}")

        if current_interactable and current_interactable != last_current_interactable:
            last_current_interactable = current_interactable
            class_name = read_class_name(memory, current_interactable) or "Interactable"
            print(f"\n[TARGET] PLAYER PROXIMITY DETECTED: {class_name} at 0x{current_interactable:X}")
            inspect_raw_memory(memory, current_interactable, scan_bytes=0x140, title=class_name)
        elif not current_interactable and last_current_interactable:
            last_current_interactable = 0
            print("[*] Stepped away from interactable.")

        # Heartbeat every 4 seconds if idle
        if now - heartbeat_time > 4.0:
            heartbeat_time = now
            if not player:
                print(f"[*] Waiting for player... ({debug_status})")
            elif not current_interactable:
                print(f"[*] Player at 0x{player:X} | Detector: 0x{detector:X} | Walk near a Moai or Shady Guy...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[*] Exiting.")
