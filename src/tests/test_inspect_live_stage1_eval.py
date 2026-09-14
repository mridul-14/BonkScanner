"""Tests for Stage 1 evaluation and Shady Guy table population when Target Items are off."""

from __future__ import annotations

import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

# Ensure tools/inspect_live is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INSPECT_LIVE_DIR = PROJECT_ROOT / "tools" / "inspect_live"
if str(INSPECT_LIVE_DIR) not in sys.path:
    sys.path.insert(0, str(INSPECT_LIVE_DIR))
DEPS_DIR = INSPECT_LIVE_DIR / "dependencies"
if str(DEPS_DIR) not in sys.path:
    sys.path.insert(0, str(DEPS_DIR))

import inspect_live as il


class TestStage1Evaluation(unittest.TestCase):
    """Test evaluate_stage1_criteria under various configuration states."""

    def setUp(self) -> None:
        self._orig_required_all_item_ids = list(il.REQUIRED_ALL_ITEM_IDS)
        self._orig_required_any_item_ids = list(il.REQUIRED_ANY_ITEM_IDS)
        self._orig_required_item_ids = list(il.REQUIRED_ITEM_IDS)
        self._orig_required_items_mode = il.REQUIRED_ITEMS_MODE
        il.REQUIRED_ALL_ITEM_IDS = []
        il.REQUIRED_ANY_ITEM_IDS = []
        il.REQUIRED_ITEM_IDS = []
        il.REQUIRED_ITEMS_MODE = "any"

    def tearDown(self) -> None:
        il.REQUIRED_ALL_ITEM_IDS = self._orig_required_all_item_ids
        il.REQUIRED_ANY_ITEM_IDS = self._orig_required_any_item_ids
        il.REQUIRED_ITEM_IDS = self._orig_required_item_ids
        il.REQUIRED_ITEMS_MODE = self._orig_required_items_mode

    def test_thresholds_pass_no_required_items(self) -> None:
        """When no items are required and shrine thresholds are met, seed passes with THRESHOLDS_MATCH."""
        (
            target_items_pass,
            thresholds_matched,
            target_only_matched,
            all_matched,
            match_reason,
        ) = il.evaluate_stage1_criteria(
            sm_pass=True,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_item_ids=[],
        )
        self.assertTrue(thresholds_matched)
        self.assertTrue(all_matched)
        self.assertFalse(target_only_matched)
        self.assertEqual(match_reason, "THRESHOLDS_MATCH")

    def test_thresholds_fail_no_required_items(self) -> None:
        """When no items are required and shrine thresholds fail, criteria fails with CRITERIA_NOT_MET."""
        (
            target_items_pass,
            thresholds_matched,
            target_only_matched,
            all_matched,
            match_reason,
        ) = il.evaluate_stage1_criteria(
            sm_pass=False,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_item_ids=[],
        )
        self.assertFalse(thresholds_matched)
        self.assertFalse(all_matched)
        self.assertEqual(match_reason, "CRITERIA_NOT_MET")

    def test_required_item_missing_thresholds_pass(self) -> None:
        """When required item is missing and thresholds pass, reason is MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS."""
        (
            target_items_pass,
            thresholds_matched,
            target_only_matched,
            all_matched,
            match_reason,
        ) = il.evaluate_stage1_criteria(
            sm_pass=True,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_all_item_ids=[41],
            offered_item_ids=[],
        )
        self.assertFalse(thresholds_matched)
        self.assertFalse(all_matched)
        self.assertFalse(target_items_pass)
        self.assertEqual(match_reason, "MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS")

    def test_required_item_present_thresholds_pass(self) -> None:
        """When required item is present and thresholds pass, reason is PERFECT_MATCH_ALL."""
        (
            target_items_pass,
            thresholds_matched,
            target_only_matched,
            all_matched,
            match_reason,
        ) = il.evaluate_stage1_criteria(
            sm_pass=True,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_all_item_ids=[41],
            offered_item_ids=[41],
        )
        self.assertTrue(thresholds_matched)
        self.assertTrue(all_matched)
        self.assertTrue(target_items_pass)
        self.assertEqual(match_reason, "PERFECT_MATCH_ALL")

    def test_required_item_present_thresholds_fail(self) -> None:
        """When required item is present but thresholds fail, reason is REQUIRED_ITEMS_FOUND_CRITERIA_FAILED."""
        (
            target_items_pass,
            thresholds_matched,
            target_only_matched,
            all_matched,
            match_reason,
        ) = il.evaluate_stage1_criteria(
            sm_pass=False,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_all_item_ids=[41],
            offered_item_ids=[41],
        )
        self.assertFalse(thresholds_matched)
        self.assertFalse(all_matched)
        self.assertTrue(target_items_pass)
        self.assertEqual(match_reason, "REQUIRED_ITEMS_FOUND_CRITERIA_FAILED")

    def test_required_any_items_missing_both(self) -> None:
        """When required_any_item_ids has 2 items and neither is offered, fails criteria."""
        (
            target_items_pass,
            thresholds_matched,
            target_only_matched,
            all_matched,
            match_reason,
        ) = il.evaluate_stage1_criteria(
            sm_pass=True,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_any_item_ids=[41, 47],
            offered_item_ids=[],
        )
        self.assertFalse(thresholds_matched)
        self.assertFalse(all_matched)
        self.assertFalse(target_items_pass)
        self.assertEqual(match_reason, "MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS")

    def test_required_any_items_has_one(self) -> None:
        """When required_any_item_ids has 2 items and at least one is offered, passes criteria."""
        (
            target_items_pass,
            thresholds_matched,
            target_only_matched,
            all_matched,
            match_reason,
        ) = il.evaluate_stage1_criteria(
            sm_pass=True,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_any_item_ids=[41, 47],
            offered_item_ids=[47],
        )
        self.assertTrue(thresholds_matched)
        self.assertTrue(all_matched)
        self.assertTrue(target_items_pass)
        self.assertEqual(match_reason, "PERFECT_MATCH_ALL")

    def test_required_all_items_missing_one(self) -> None:
        """When required_all_item_ids has 2 items and only one is offered, fails criteria."""
        (
            target_items_pass,
            thresholds_matched,
            target_only_matched,
            all_matched,
            match_reason,
        ) = il.evaluate_stage1_criteria(
            sm_pass=True,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_all_item_ids=[41, 47],
            offered_item_ids=[41],
        )
        self.assertFalse(thresholds_matched)
        self.assertFalse(all_matched)
        self.assertEqual(match_reason, "MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS")

    def test_required_all_items_both_present(self) -> None:
        """When required_all_item_ids has 2 items and all are offered, passes criteria."""
        (
            target_items_pass,
            thresholds_matched,
            target_only_matched,
            all_matched,
            match_reason,
        ) = il.evaluate_stage1_criteria(
            sm_pass=True,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_all_item_ids=[41, 47],
            offered_item_ids=[41, 47],
        )
        self.assertTrue(thresholds_matched)
        self.assertTrue(all_matched)
        self.assertTrue(target_items_pass)
        self.assertEqual(match_reason, "PERFECT_MATCH_ALL")

    def test_combined_all_and_any_items(self) -> None:
        """Combined ALL and ANY lists: requires ALL of AND-list plus at least ONE of OR-list."""
        # Must have 45 (Plug) AND 57 (Kevin), plus either 41 (Anvil) OR 47 (Soul Harvester)
        req_all = [45, 57]
        req_any = [41, 47]

        # Case 1: Missing one from ALL list (only 45 and 41 present) -> Fail
        (_, _, _, all_m1, r1) = il.evaluate_stage1_criteria(
            sm_pass=True, micro_pass=True, boss_pass=True, magnet_pass=True, shady_pass=True,
            required_all_item_ids=req_all, required_any_item_ids=req_any,
            offered_item_ids=[45, 41],
        )
        self.assertFalse(all_m1)
        self.assertEqual(r1, "MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS")

        # Case 2: ALL list satisfied (45, 57), but missing ANY list -> Fail
        (_, _, _, all_m2, r2) = il.evaluate_stage1_criteria(
            sm_pass=True, micro_pass=True, boss_pass=True, magnet_pass=True, shady_pass=True,
            required_all_item_ids=req_all, required_any_item_ids=req_any,
            offered_item_ids=[45, 57],
        )
        self.assertFalse(all_m2)
        self.assertEqual(r2, "MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS")

        # Case 3: ALL list satisfied (45, 57) + one from ANY list (47) -> Pass
        (t_pass3, _, _, all_m3, r3) = il.evaluate_stage1_criteria(
            sm_pass=True, micro_pass=True, boss_pass=True, magnet_pass=True, shady_pass=True,
            required_all_item_ids=req_all, required_any_item_ids=req_any,
            offered_item_ids=[45, 57, 47],
        )
        self.assertTrue(t_pass3)
        self.assertTrue(all_m3)
        self.assertEqual(r3, "PERFECT_MATCH_ALL")

    def test_scan_stage1_seed_filter_fast_eval_required_items(self) -> None:
        """Test scan_stage1_seed_filter fast_eval skips heap when required items are active but 0 Shady Guys."""
        mock_mem = unittest.mock.MagicMock()
        with patch.object(il, "get_stage_index", return_value=0), \
             patch.object(il, "get_map_interactable_counts", return_value={
                 "shady": 0, "moai": 10, "microwaves": 2, "boss_curses": 1, "magnets": 2,
             }):
            # When required_all_item_ids=[41] and shady=0: fast_eval skips heap and reports missing required items
            res_req = il.scan_stage1_seed_filter(
                mock_mem, 0x1000, fast_eval=True, character=(0, "Fox"), required_all_item_ids=[41]
            )
            self.assertTrue(res_req.get("shady_skipped"))
            self.assertFalse(res_req.get("all_matched"))
            self.assertEqual(res_req.get("match_reason"), "MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS")
            self.assertEqual(res_req.get("required_all_item_ids"), [41])

            # When required_all_item_ids=[] and required_any_item_ids=[] and shady=0: does not skip heap due to items
            with patch.object(il, "scan_heap_interactables", return_value=([], [], [], [])):
                res_no_req = il.scan_stage1_seed_filter(
                    mock_mem, 0x1000, fast_eval=True, character=(0, "Fox"),
                    required_all_item_ids=[], required_any_item_ids=[],
                )
                self.assertEqual(res_no_req.get("required_all_item_ids"), [])
                self.assertTrue(res_no_req.get("all_matched"))
                self.assertEqual(res_no_req.get("match_reason"), "THRESHOLDS_MATCH")


class TestStage1ReportTableDisplay(unittest.TestCase):
    """Test print_stage1_report prints Shady items tables when thresholds match."""

    def setUp(self) -> None:
        self._orig_required_all_item_ids = list(il.REQUIRED_ALL_ITEM_IDS)
        self._orig_required_any_item_ids = list(il.REQUIRED_ANY_ITEM_IDS)
        self._orig_required_item_ids = list(il.REQUIRED_ITEM_IDS)
        self._orig_required_items_mode = il.REQUIRED_ITEMS_MODE
        il.REQUIRED_ALL_ITEM_IDS = []
        il.REQUIRED_ANY_ITEM_IDS = []
        il.REQUIRED_ITEM_IDS = []
        il.REQUIRED_ITEMS_MODE = "any"
        self.mock_shady_guys = [
            {
                "ptr": 0x12345678,
                "rarity": "COMMON",
                "done": False,
                "items": [
                    {"item_id": 1, "item_name": "Apple"},
                    {"item_id": 2, "item_name": "Banana"},
                    {"item_id": 3, "item_name": "Orange"},
                ],
                "gold_prices": [10, 20, 30],
                "multipliers": [1.0, 1.2, 1.5],
                "pos": (10.0, 20.0),
                "dist": 22.4,
                "map_sector": "North-East",
                "rel_dir": ("NE", 45, 22),
            }
        ]
        self.mock_result = {
            "is_stage_1": True,
            "stage_index": 0,
            "elapsed_s": 0.42,
            "character": "Fox",
            "character_id": 0,
            "is_fox": True,
            "map_counts": {"shady": 1, "moai": 8, "microwaves": 2, "boss_curses": 1, "magnets": 2},
            "sm_total": 9,
            "sm_pass": True,
            "micro_pass": True,
            "boss_pass": True,
            "magnet_pass": True,
            "target_items_found": False,
            "target_items_pass": True,
            "thresholds_matched": True,
            "target_only_matched": False,
            "all_matched": True,
            "match_reason": "PERFECT_MATCH_ALL",
            "shady_count": 1,
            "shady_resolved": True,
            "target_shady": 1,
            "shady_guys": self.mock_shady_guys,
            "microwaves": [{"color": "Blue", "map_sector": "Center"}],
            "moais": [],
            "boss_curses": [],
            "target_matches": [],
            "required_all_item_ids": [],
            "required_any_item_ids": [],
            "required_item_ids": [],
            "required_items_mode": "any",
            "offered_item_counts": {},
        }

    def tearDown(self) -> None:
        il.REQUIRED_ALL_ITEM_IDS = self._orig_required_all_item_ids
        il.REQUIRED_ANY_ITEM_IDS = self._orig_required_any_item_ids
        il.REQUIRED_ITEM_IDS = self._orig_required_item_ids
        il.REQUIRED_ITEMS_MODE = self._orig_required_items_mode

    def test_shady_tables_printed_in_plain_text_during_reroll(self) -> None:
        """When reroll_num is an integer (auto-restart active) and all_matched=True, Shady tables are printed."""
        buf = io.StringIO()
        with patch.object(il, "console", None):
            with patch("sys.stdout", buf):
                il.print_stage1_report(self.mock_result, reroll_num=3)
        output = buf.getvalue()
        self.assertIn("ALL SHADY ITEMS RANKED BY DISTANCE", output)
        self.assertIn("Apple", output)
        self.assertIn("Banana", output)
        self.assertIn("Orange", output)

    def test_shady_tables_printed_in_rich_console(self) -> None:
        """When rich console is available and all_matched=True, ranked items are rendered."""
        if il.console is None:
            self.skipTest("Rich console not installed")
        with patch.object(il.console, "print") as mock_print:
            il.print_stage1_report(self.mock_result, reroll_num=1)
            table_titles = [
                getattr(call.args[0], "title", None)
                for call in mock_print.call_args_list
                if call.args and hasattr(call.args[0], "title")
            ]
            self.assertTrue(
                any("all shady items ranked" in str(t).lower() for t in table_titles),
                f"Expected All Shady Items Ranked table, got: {table_titles}",
            )
            self.assertTrue(
                any("shady guy inventories" in str(t).lower() for t in table_titles),
                f"Expected Shady Guy Inventories table, got: {table_titles}",
            )

    def test_missing_required_items_plain_text_report(self) -> None:
        """When required item is missing (criteria not met), plain text report prints status only and NO tables."""
        res = dict(self.mock_result)
        res["required_all_item_ids"] = [41]
        res["required_any_item_ids"] = []
        res["offered_item_counts"] = {}
        res["target_items_pass"] = False
        res["thresholds_matched"] = False
        res["all_matched"] = False
        res["match_reason"] = "MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS"
        buf = io.StringIO()
        with patch.object(il, "console", None):
            with patch("sys.stdout", buf):
                il.print_stage1_report(res)
        output = buf.getvalue()
        self.assertIn("Status: [-] CRITERIA NOT MET", output)
        self.assertIn("Anvil", output)
        self.assertNotIn("ALL SHADY ITEMS RANKED BY DISTANCE", output)
        self.assertNotIn("SHADY GUY INVENTORIES", output)

    def test_missing_required_items_rich_table_report(self) -> None:
        """When Rich console is available and required item is missing, only status Panel is printed (NO tables)."""
        if il.console is None:
            self.skipTest("Rich console not installed")
        res = dict(self.mock_result)
        res["required_all_item_ids"] = [41]
        res["required_any_item_ids"] = []
        res["offered_item_counts"] = {}
        res["target_items_pass"] = False
        res["thresholds_matched"] = False
        res["all_matched"] = False
        res["match_reason"] = "MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS"
        with patch.object(il.console, "print") as mock_print:
            il.print_stage1_report(res)
            table_calls = [
                call.args[0] for call in mock_print.call_args_list
                if call.args and isinstance(call.args[0], il.Table)
            ]
            self.assertEqual(len(table_calls), 0, f"Expected 0 tables on failure, got: {table_calls}")
            panels = [
                call.args[0] for call in mock_print.call_args_list
                if call.args and isinstance(call.args[0], il.Panel)
            ]
            self.assertEqual(len(panels), 1, "Expected 1 status panel")

    def test_criteria_not_met_prints_no_tables_plain_text(self) -> None:
        """When all_matched is False, plain text report prints status only and skips all tables."""
        res = dict(self.mock_result)
        res["sm_pass"] = False
        res["all_matched"] = False
        res["match_reason"] = None
        buf = io.StringIO()
        with patch.object(il, "console", None):
            with patch("sys.stdout", buf):
                il.print_stage1_report(res, reroll_num=5)
        output = buf.getvalue()
        self.assertIn("Status: [-] CRITERIA NOT MET", output)
        self.assertNotIn("Stage 1 Requirements", output)
        self.assertNotIn("ALL SHADY ITEMS RANKED BY DISTANCE", output)
        self.assertNotIn("SHADY GUY INVENTORIES", output)
        self.assertNotIn("MICROWAVES ON MAP", output)

    def test_criteria_not_met_prints_no_tables_rich(self) -> None:
        """When all_matched is False, Rich console prints status Panel only and zero Table objects."""
        if il.console is None:
            self.skipTest("Rich console not installed")
        res = dict(self.mock_result)
        res["sm_pass"] = False
        res["all_matched"] = False
        res["match_reason"] = None
        with patch.object(il.console, "print") as mock_print:
            il.print_stage1_report(res, reroll_num=5)
            table_calls = [
                call.args[0] for call in mock_print.call_args_list
                if call.args and isinstance(call.args[0], il.Table)
            ]
            self.assertEqual(len(table_calls), 0, f"Expected 0 tables on failure, got: {table_calls}")
            panels = [
                call.args[0] for call in mock_print.call_args_list
                if call.args and isinstance(call.args[0], il.Panel)
            ]
            self.assertEqual(len(panels), 1, "Expected 1 status panel")

    def test_required_item_ids_rich_table_report(self) -> None:
        """When required items are set, checklist table shows item name rows."""
        if il.console is None:
            self.skipTest("Rich console not installed")
        res = dict(self.mock_result)
        res["required_all_item_ids"] = [22]  # Dragonfire
        res["required_any_item_ids"] = []
        res["offered_item_counts"] = {22: 1}
        res["target_items_pass"] = True
        res["thresholds_matched"] = True
        res["all_matched"] = True
        res["match_reason"] = "PERFECT_MATCH_ALL"
        with patch.object(il.console, "print") as mock_print:
            il.print_stage1_report(res)
            req_table = next(
                (call.args[0] for call in mock_print.call_args_list if call.args and getattr(call.args[0], "title", None) == "Stage 1 Requirements"),
                None,
            )
            self.assertIsNotNone(req_table)
            row_texts = []
            for col in req_table.columns:
                for cell in col._cells:
                    row_texts.append(str(cell))
            self.assertTrue(any("Dragonfire" in text for text in row_texts))
            self.assertTrue(any("1 / 1" in text for text in row_texts))

    def test_required_item_ids_plain_text_report(self) -> None:
        """When required items are set, plain text report prints row with matching counts."""
        res = dict(self.mock_result)
        res["required_all_item_ids"] = [22]
        res["required_any_item_ids"] = []
        res["offered_item_counts"] = {22: 1}
        res["target_items_pass"] = True
        res["thresholds_matched"] = True
        res["all_matched"] = True
        res["match_reason"] = "PERFECT_MATCH_ALL"
        buf = io.StringIO()
        with patch.object(il, "console", None):
            with patch("sys.stdout", buf):
                il.print_stage1_report(res)
        output = buf.getvalue()
        self.assertIn("Dragonfire", output)
        self.assertIn("MATCHED", output)

    def test_required_item_ids_plain_text_failed_report(self) -> None:
        """When required item is missing, plain text report shows CRITERIA NOT MET and skips tables."""
        res = dict(self.mock_result)
        res["required_all_item_ids"] = [22]
        res["required_any_item_ids"] = []
        res["offered_item_counts"] = {}
        res["target_items_pass"] = False
        res["thresholds_matched"] = False
        res["all_matched"] = False
        res["match_reason"] = "MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS"
        buf = io.StringIO()
        with patch.object(il, "console", None):
            with patch("sys.stdout", buf):
                il.print_stage1_report(res)
        output = buf.getvalue()
        self.assertIn("CRITERIA NOT MET", output)
        self.assertIn("Dragonfire", output)


class TestRequiredItemIdsEvaluation(unittest.TestCase):
    """Test evaluate_stage1_criteria using required_all_item_ids and required_any_item_ids."""

    def setUp(self) -> None:
        self._orig_required_all_item_ids = list(il.REQUIRED_ALL_ITEM_IDS)
        self._orig_required_any_item_ids = list(il.REQUIRED_ANY_ITEM_IDS)
        self._orig_required_item_ids = list(il.REQUIRED_ITEM_IDS)
        self._orig_required_items_mode = il.REQUIRED_ITEMS_MODE
        il.REQUIRED_ALL_ITEM_IDS = []
        il.REQUIRED_ANY_ITEM_IDS = []
        il.REQUIRED_ITEM_IDS = []
        il.REQUIRED_ITEMS_MODE = "any"

    def tearDown(self) -> None:
        il.REQUIRED_ALL_ITEM_IDS = self._orig_required_all_item_ids
        il.REQUIRED_ANY_ITEM_IDS = self._orig_required_any_item_ids
        il.REQUIRED_ITEM_IDS = self._orig_required_item_ids
        il.REQUIRED_ITEMS_MODE = self._orig_required_items_mode

    def test_empty_required_item_ids_passes_thresholds_normally(self) -> None:
        """When required item lists are empty, evaluation passes on thresholds alone."""
        (
            target_items_pass,
            thresholds_matched,
            target_only_matched,
            all_matched,
            match_reason,
        ) = il.evaluate_stage1_criteria(
            sm_pass=True,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_all_item_ids=[],
            required_any_item_ids=[],
        )
        self.assertTrue(thresholds_matched)
        self.assertTrue(all_matched)
        self.assertEqual(match_reason, "THRESHOLDS_MATCH")

    def test_single_required_all_item_missing_fails(self) -> None:
        """Single required ALL item ID (Anvil 41) missing causes failure."""
        (
            _,
            thresholds_matched,
            _,
            all_matched,
            match_reason,
        ) = il.evaluate_stage1_criteria(
            sm_pass=True,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_all_item_ids=[41],
            offered_item_ids=[],
        )
        self.assertFalse(thresholds_matched)
        self.assertFalse(all_matched)
        self.assertEqual(match_reason, "MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS")

    def test_single_required_all_item_present_passes(self) -> None:
        """Single required ALL item ID present satisfies criteria."""
        (
            target_items_pass,
            thresholds_matched,
            _,
            all_matched,
            match_reason,
        ) = il.evaluate_stage1_criteria(
            sm_pass=True,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_all_item_ids=[41],
            offered_item_ids=[41],
        )
        self.assertTrue(target_items_pass)
        self.assertTrue(thresholds_matched)
        self.assertTrue(all_matched)
        self.assertEqual(match_reason, "PERFECT_MATCH_ALL")

    def test_custom_item_id_dragonfire(self) -> None:
        """Arbitrary item ID (e.g. Dragonfire 22) works as required item."""
        # Missing
        (
            _,
            thresholds_matched,
            _,
            all_matched,
            match_reason,
        ) = il.evaluate_stage1_criteria(
            sm_pass=True,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_all_item_ids=[22],
            offered_item_ids=[1, 2, 3],
        )
        self.assertFalse(all_matched)
        self.assertEqual(match_reason, "MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS")

        # Present
        (
            _,
            thresholds_matched2,
            _,
            all_matched2,
            match_reason2,
        ) = il.evaluate_stage1_criteria(
            sm_pass=True,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_all_item_ids=[22],
            offered_item_ids=[22],
        )
        self.assertTrue(all_matched2)
        self.assertEqual(match_reason2, "PERFECT_MATCH_ALL")

    def test_any_mode_passes_when_at_least_one_present(self) -> None:
        """Mode 'any' passes if any of the required items is offered."""
        # Anvil 41 or Soul Harvester 47
        (
            _,
            _,
            _,
            all_matched,
            match_reason,
        ) = il.evaluate_stage1_criteria(
            sm_pass=True,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_any_item_ids=[41, 47],
            offered_item_ids=[47],
        )
        self.assertTrue(all_matched)
        self.assertEqual(match_reason, "PERFECT_MATCH_ALL")

        # Neither offered
        (
            _,
            _,
            _,
            all_matched_fail,
            match_reason_fail,
        ) = il.evaluate_stage1_criteria(
            sm_pass=True,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_any_item_ids=[41, 47],
            offered_item_ids=[10, 20],
        )
        self.assertFalse(all_matched_fail)
        self.assertEqual(match_reason_fail, "MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS")

    def test_all_mode_requires_every_item(self) -> None:
        """Mode 'all' requires all listed items to be present."""
        # Only Anvil present, Soul Harvester missing
        (
            _,
            _,
            _,
            all_matched_partial,
            match_reason_partial,
        ) = il.evaluate_stage1_criteria(
            sm_pass=True,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_all_item_ids=[41, 47],
            offered_item_ids=[41],
        )
        self.assertFalse(all_matched_partial)
        self.assertEqual(match_reason_partial, "MISSING_REQUIRED_ITEMS_THRESHOLDS_PASS")

        # Both present
        (
            _,
            _,
            _,
            all_matched_both,
            match_reason_both,
        ) = il.evaluate_stage1_criteria(
            sm_pass=True,
            micro_pass=True,
            boss_pass=True,
            magnet_pass=True,
            shady_pass=True,
            required_all_item_ids=[41, 47],
            offered_item_ids=[41, 47],
        )
        self.assertTrue(all_matched_both)
        self.assertEqual(match_reason_both, "PERFECT_MATCH_ALL")


class FakeProcessMemory:
    """Mock memory reader for testing lifecycle and done tracking."""

    def __init__(self) -> None:
        self.ptrs: dict[int, int] = {}
        self.u8s: dict[int, int] = {}
        self.i32s: dict[int, int] = {}

    def read_ptr(self, addr: int) -> int:
        return self.ptrs.get(addr, 0)

    def read_u8(self, addr: int) -> int:
        return self.u8s.get(addr, 0)

    def read_i32(self, addr: int) -> int:
        return self.i32s.get(addr, 0)


class TestShadyGuyDoneTracking(unittest.TestCase):
    """Test is_shady_guy_done under various memory states."""

    def setUp(self) -> None:
        self.memory = FakeProcessMemory()
        self.ptr = 0x20000
        self.items_ptr = 0x30000
        # Valid native component
        self.memory.ptrs[self.ptr + il.NATIVE_COMP_OFFSET] = 0x50000
        # Done flag not set
        self.memory.u8s[self.ptr + il.SHADY_DONE_OFFSET] = 0
        # Items list ptr
        self.memory.ptrs[self.ptr + il.SHADY_ITEMS_LIST_OFFSET] = self.items_ptr
        # 3 items in memory
        self.memory.i32s[self.items_ptr + 0x18] = 3
        # Off-target byte at 0x68 is non-zero (must NOT affect Shady Guy!)
        self.memory.u8s[self.ptr + 0x68] = 1

    def test_fresh_vendor_not_done(self) -> None:
        """A fresh vendor with 3 items and done=0 must return False even if byte 0x68 is non-zero."""
        sg = {
            "ptr": self.ptr,
            "done": False,
            "items": [{"item_id": 1}, {"item_id": 2}, {"item_id": 3}],
        }
        self.assertFalse(il.is_shady_guy_done(self.memory, self.ptr, sg_dict=sg))

    def test_item_purchased_decreases_count_triggers_done(self) -> None:
        """When an item is purchased, memory item_count drops from 3 to 2, marking the vendor done."""
        sg = {
            "ptr": self.ptr,
            "done": False,
            "items": [{"item_id": 1}, {"item_id": 2}, {"item_id": 3}],
        }
        self.memory.i32s[self.items_ptr + 0x18] = 2
        self.assertTrue(il.is_shady_guy_done(self.memory, self.ptr, sg_dict=sg))

    def test_all_items_cleared_triggers_done(self) -> None:
        """When all items are cleared (item_count=0), vendor with initial items is marked done."""
        sg = {
            "ptr": self.ptr,
            "done": False,
            "items": [{"item_id": 1}, {"item_id": 2}, {"item_id": 3}],
        }
        self.memory.i32s[self.items_ptr + 0x18] = 0
        self.assertTrue(il.is_shady_guy_done(self.memory, self.ptr, sg_dict=sg))

    def test_uninitialized_zero_items_does_not_falsely_trigger_done(self) -> None:
        """If a vendor was captured before items loaded (0 items), item_count=0 must NOT mark done."""
        sg = {
            "ptr": self.ptr,
            "done": False,
            "items": [],
        }
        self.memory.i32s[self.items_ptr + 0x18] = 0
        self.assertFalse(il.is_shady_guy_done(self.memory, self.ptr, sg_dict=sg))

    def test_done_flag_at_0xb0_triggers_done(self) -> None:
        """InteractableShadyGuy.done at offset 0xB0 triggers done."""
        sg = {
            "ptr": self.ptr,
            "done": False,
            "items": [{"item_id": 1}, {"item_id": 2}, {"item_id": 3}],
        }
        self.memory.u8s[self.ptr + il.SHADY_DONE_OFFSET] = 1
        self.assertTrue(il.is_shady_guy_done(self.memory, self.ptr, sg_dict=sg))

    def test_destroyed_native_component_triggers_done(self) -> None:
        """When native component is null/destroyed, returns True."""
        sg = {
            "ptr": self.ptr,
            "done": False,
            "items": [{"item_id": 1}, {"item_id": 2}, {"item_id": 3}],
        }
        self.memory.ptrs[self.ptr + il.NATIVE_COMP_OFFSET] = 0
        self.assertTrue(il.is_shady_guy_done(self.memory, self.ptr, sg_dict=sg))


class TestShadyGuyRankedItems(unittest.TestCase):
    """Test get_all_shady_items_ranked ordering and done status."""

    def test_ranked_by_distance_and_done_propagation(self) -> None:
        """Items are ranked by distance, and individual items reflect vendor done status."""
        shady_guys = [
            {
                "shady_num": 1,
                "dist": 150.0,
                "done": False,
                "rarity": "COMMON",
                "items": [{"item_id": 10, "item_name": "ItemA"}],
                "gold_prices": [50],
                "multipliers": [1.0],
                "map_sector": "North",
                "rel_dir": ("N", 0, 150),
            },
            {
                "shady_num": 2,
                "dist": 50.0,
                "done": True,
                "rarity": "EPIC",
                "items": [{"item_id": 20, "item_name": "ItemB"}],
                "gold_prices": [100],
                "multipliers": [1.5],
                "map_sector": "South",
                "rel_dir": ("S", 180, 50),
            },
        ]
        ranked = il.get_all_shady_items_ranked(shady_guys)
        self.assertEqual(len(ranked), 2)
        # Closest item first (50m, from Shady #2)
        self.assertEqual(ranked[0]["item_name"], "ItemB")
        self.assertEqual(ranked[0]["dist"], 50.0)
        self.assertEqual(ranked[0]["shady_num"], 2)
        self.assertTrue(ranked[0]["shady_done"], "Item from completed Shady Guy must have shady_done=True")

        # Second item (150m, from Shady #1)
        self.assertEqual(ranked[1]["item_name"], "ItemA")
        self.assertEqual(ranked[1]["dist"], 150.0)
        self.assertEqual(ranked[1]["shady_num"], 1)
        self.assertFalse(ranked[1]["shady_done"], "Item from active Shady Guy must have shady_done=False")


class TestRequiredItemsColorScheme(unittest.TestCase):
    """Test that REQUIRED_ALL_ITEM_IDS and REQUIRED_ANY_ITEM_IDS inherit the target item color scheme and formatting."""

    def setUp(self) -> None:
        self._orig_required_all_item_ids = list(il.REQUIRED_ALL_ITEM_IDS)
        self._orig_required_any_item_ids = list(il.REQUIRED_ANY_ITEM_IDS)
        self._orig_required_item_ids = list(il.REQUIRED_ITEM_IDS)
        il.REQUIRED_ALL_ITEM_IDS = [58]  # Borgar (Common item 58)
        il.REQUIRED_ANY_ITEM_IDS = [7]   # Battery (Common item 7)
        il.REQUIRED_ITEM_IDS = []

    def tearDown(self) -> None:
        il.REQUIRED_ALL_ITEM_IDS = self._orig_required_all_item_ids
        il.REQUIRED_ANY_ITEM_IDS = self._orig_required_any_item_ids
        il.REQUIRED_ITEM_IDS = self._orig_required_item_ids

    def test_required_all_item_is_treated_as_target_item(self) -> None:
        """Items in REQUIRED_ALL_ITEM_IDS must return True for is_target_item."""
        self.assertTrue(il.is_target_item(58))
        self.assertTrue(il.is_target_item(None, "Borgar"))

    def test_required_any_item_is_treated_as_target_item(self) -> None:
        """Items in REQUIRED_ANY_ITEM_IDS must return True for is_target_item."""
        self.assertTrue(il.is_target_item(7))
        self.assertTrue(il.is_target_item(None, "Battery"))

    def test_required_items_use_target_item_color(self) -> None:
        """Items in required lists must be styled with TARGET_ITEM_COLOR in format_item_display."""
        disp_rich_all = il.format_item_display(58, "Borgar", use_rich=True)
        self.assertIn(il.TARGET_ITEM_COLOR, disp_rich_all)
        self.assertIn("*", disp_rich_all)

        disp_rich_any = il.format_item_display(7, "Battery", use_rich=True)
        self.assertIn(il.TARGET_ITEM_COLOR, disp_rich_any)
        self.assertIn("*", disp_rich_any)

        disp_plain = il.format_item_display(58, "Borgar", use_rich=False)
        self.assertEqual(disp_plain, "Borgar*")


if __name__ == "__main__":
    unittest.main()
