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

    def test_target_items_off_thresholds_pass_fox_no_anvil(self) -> None:
        """When Target Items are OFF, Fox strictly requires Anvil at all times (fails if missing)."""
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
            target_items_found=False,
            has_white_micro=False,
            is_fox=True,
            has_anvil=False,
            require_target_items=False,
            anvil_required=True,
        )
        self.assertFalse(thresholds_matched, "Fox must not match thresholds when Anvil is missing")
        self.assertFalse(all_matched, "all_matched must be False for Fox without Anvil")
        self.assertFalse(target_only_matched)
        self.assertEqual(match_reason, "FOX_MISSING_ANVIL_THRESHOLDS_PASS")

    def test_fox_anvil_required_flag_false_allows_thresholds_match_without_anvil(self) -> None:
        """When anvil_required flag is False, Fox does NOT require Anvil and matches thresholds normally."""
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
            target_items_found=False,
            has_white_micro=False,
            is_fox=True,
            has_anvil=False,
            require_target_items=False,
            anvil_required=False,
        )
        self.assertTrue(thresholds_matched, "When anvil_required=False, Fox matches thresholds without Anvil")
        self.assertTrue(all_matched, "all_matched must be True when thresholds are satisfied and flag is False")
        self.assertFalse(target_only_matched)
        self.assertEqual(match_reason, "THRESHOLDS_MATCH")

    def test_anvil_required_flag_true_non_fox_missing_anvil_fails(self) -> None:
        """When anvil_required is True, non-Fox character requires Anvil and fails if missing."""
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
            target_items_found=False,
            has_white_micro=False,
            is_fox=False,
            has_anvil=False,
            require_target_items=False,
            anvil_required=True,
        )
        self.assertFalse(thresholds_matched, "Non-Fox must not match thresholds when anvil_required=True and Anvil is missing")
        self.assertFalse(all_matched, "all_matched must be False when anvil_required=True without Anvil")
        self.assertEqual(match_reason, "MISSING_ANVIL_THRESHOLDS_PASS")

    def test_anvil_required_flag_true_non_fox_with_anvil_passes(self) -> None:
        """When anvil_required is True, non-Fox character with Anvil and thresholds met results in PERFECT_MATCH_ALL."""
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            has_anvil=True,
            require_target_items=False,
            anvil_required=True,
        )
        self.assertTrue(thresholds_matched)
        self.assertTrue(all_matched)
        self.assertTrue(target_items_pass)
        self.assertEqual(match_reason, "PERFECT_MATCH_ALL")

    def test_anvil_required_flag_false_non_fox_allows_thresholds_match_without_anvil(self) -> None:
        """When anvil_required is False, non-Fox matches thresholds without Anvil."""
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
            target_items_found=False,
            has_white_micro=False,
            is_fox=False,
            has_anvil=False,
            require_target_items=False,
            anvil_required=False,
        )
        self.assertTrue(thresholds_matched)
        self.assertTrue(all_matched)
        self.assertEqual(match_reason, "THRESHOLDS_MATCH")

    def test_target_items_off_thresholds_pass_fox_with_anvil(self) -> None:
        """When Target Items are OFF, Fox with Anvil and thresholds met results in PERFECT_MATCH_ALL."""
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=True,
            has_anvil=True,
            require_target_items=False,
            anvil_required=True,
        )
        self.assertTrue(thresholds_matched, "Fox with Anvil and thresholds satisfied must match")
        self.assertTrue(all_matched, "all_matched must be True for Fox with Anvil")
        self.assertTrue(target_items_pass)
        self.assertEqual(match_reason, "PERFECT_MATCH_ALL")

    def test_fox_with_anvil_missing_white_micro_fails(self) -> None:
        """For Fox, Anvil without required White Microwave fails match."""
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
            target_items_found=False,
            has_white_micro=False,
            is_fox=True,
            has_anvil=True,
            require_target_items=False,
            anvil_required=True,
            target_items_require_white_micro=True,
        )
        self.assertFalse(all_matched)
        self.assertEqual(match_reason, "TARGET_ITEMS_NO_WHITE_MICROWAVE")

    def test_soul_harvester_required_flag_missing_fails(self) -> None:
        """When soul_harvester_required is True, missing Soul Harvester fails match even if thresholds pass."""
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            has_anvil=False,
            require_target_items=False,
            anvil_required=False,
            soul_harvester_required=True,
            has_soul_harvester=False,
        )
        self.assertFalse(thresholds_matched)
        self.assertFalse(all_matched)
        self.assertFalse(target_items_pass)
        self.assertEqual(match_reason, "MISSING_SOUL_HARVESTER_THRESHOLDS_PASS")

    def test_soul_harvester_required_flag_present_passes(self) -> None:
        """When soul_harvester_required is True and Soul Harvester is present, thresholds pass results in PERFECT_MATCH_ALL."""
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            has_anvil=False,
            require_target_items=False,
            anvil_required=False,
            soul_harvester_required=True,
            has_soul_harvester=True,
        )
        self.assertTrue(thresholds_matched)
        self.assertTrue(all_matched)
        self.assertTrue(target_items_pass)
        self.assertEqual(match_reason, "PERFECT_MATCH_ALL")

    def test_soul_harvester_required_present_thresholds_fail(self) -> None:
        """When soul_harvester_required is True and present, but thresholds fail, reason is SOUL_HARVESTER_FOUND_CRITERIA_FAILED."""
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            has_anvil=False,
            require_target_items=False,
            anvil_required=False,
            soul_harvester_required=True,
            has_soul_harvester=True,
        )
        self.assertFalse(thresholds_matched)
        self.assertFalse(all_matched)
        self.assertTrue(target_items_pass)
        self.assertEqual(match_reason, "SOUL_HARVESTER_FOUND_CRITERIA_FAILED")

    def test_anvil_and_soul_harvester_both_required_missing_both(self) -> None:
        """When both Anvil and Soul Harvester are required, missing both reports MISSING_ANVIL_AND_SOUL_HARVESTER_THRESHOLDS_PASS."""
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            has_anvil=False,
            require_target_items=False,
            anvil_required=True,
            soul_harvester_required=True,
            has_soul_harvester=False,
        )
        self.assertFalse(thresholds_matched)
        self.assertFalse(all_matched)
        self.assertEqual(match_reason, "MISSING_ANVIL_AND_SOUL_HARVESTER_THRESHOLDS_PASS")

    def test_anvil_and_soul_harvester_both_required_missing_one(self) -> None:
        """When both are required, having Anvil but missing Soul Harvester reports MISSING_SOUL_HARVESTER_THRESHOLDS_PASS."""
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            has_anvil=True,
            require_target_items=False,
            anvil_required=True,
            soul_harvester_required=True,
            has_soul_harvester=False,
        )
        self.assertFalse(thresholds_matched)
        self.assertFalse(all_matched)
        self.assertEqual(match_reason, "MISSING_SOUL_HARVESTER_THRESHOLDS_PASS")

        # Vice-versa: having Soul Harvester but missing Anvil
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            has_anvil=False,
            require_target_items=False,
            anvil_required=True,
            soul_harvester_required=True,
            has_soul_harvester=True,
        )
        self.assertFalse(thresholds_matched2)
        self.assertFalse(all_matched2)
        self.assertEqual(match_reason2, "MISSING_ANVIL_THRESHOLDS_PASS")

    def test_anvil_and_soul_harvester_both_required_has_both(self) -> None:
        """When both are required and both are present with thresholds passing, results in PERFECT_MATCH_ALL."""
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            has_anvil=True,
            require_target_items=False,
            anvil_required=True,
            soul_harvester_required=True,
            has_soul_harvester=True,
        )
        self.assertTrue(thresholds_matched)
        self.assertTrue(all_matched)
        self.assertTrue(target_items_pass)
        self.assertEqual(match_reason, "PERFECT_MATCH_ALL")

    def test_anvil_and_soul_harvester_both_present_thresholds_fail(self) -> None:
        """When both are required and present, but shrine counts fail, reason is ANVIL_AND_SOUL_HARVESTER_FOUND_CRITERIA_FAILED."""
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            has_anvil=True,
            require_target_items=False,
            anvil_required=True,
            soul_harvester_required=True,
            has_soul_harvester=True,
        )
        self.assertFalse(thresholds_matched)
        self.assertFalse(all_matched)
        self.assertTrue(target_items_pass)
        self.assertEqual(match_reason, "ANVIL_AND_SOUL_HARVESTER_FOUND_CRITERIA_FAILED")

    def test_anvil_or_soul_harvester_required_missing_both_fails(self) -> None:
        """When either Anvil OR Soul Harvester is required, missing both fails criteria."""
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            has_anvil=False,
            require_target_items=False,
            anvil_or_soul_harvester_required=True,
            has_soul_harvester=False,
        )
        self.assertFalse(thresholds_matched)
        self.assertFalse(all_matched)
        self.assertFalse(target_items_pass)
        self.assertEqual(match_reason, "MISSING_ANVIL_OR_SOUL_HARVESTER_THRESHOLDS_PASS")

    def test_anvil_or_soul_harvester_required_has_anvil_passes(self) -> None:
        """When either Anvil OR Soul Harvester is required, having only Anvil passes."""
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            has_anvil=True,
            require_target_items=False,
            anvil_or_soul_harvester_required=True,
            has_soul_harvester=False,
        )
        self.assertTrue(thresholds_matched)
        self.assertTrue(all_matched)
        self.assertTrue(target_items_pass)
        self.assertEqual(match_reason, "PERFECT_MATCH_ALL")

    def test_anvil_or_soul_harvester_required_has_soul_harvester_passes(self) -> None:
        """When either Anvil OR Soul Harvester is required, having only Soul Harvester passes."""
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            has_anvil=False,
            require_target_items=False,
            anvil_or_soul_harvester_required=True,
            has_soul_harvester=True,
        )
        self.assertTrue(thresholds_matched)
        self.assertTrue(all_matched)
        self.assertTrue(target_items_pass)
        self.assertEqual(match_reason, "PERFECT_MATCH_ALL")

    def test_anvil_or_soul_harvester_required_has_both_passes(self) -> None:
        """When either Anvil OR Soul Harvester is required, having both passes."""
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            has_anvil=True,
            require_target_items=False,
            anvil_or_soul_harvester_required=True,
            has_soul_harvester=True,
        )
        self.assertTrue(thresholds_matched)
        self.assertTrue(all_matched)
        self.assertTrue(target_items_pass)
        self.assertEqual(match_reason, "PERFECT_MATCH_ALL")

    def test_anvil_or_soul_harvester_required_has_anvil_thresholds_fail(self) -> None:
        """When either is required, having Anvil but failing thresholds reports ANVIL_FOUND_CRITERIA_FAILED."""
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            has_anvil=True,
            require_target_items=False,
            anvil_or_soul_harvester_required=True,
            has_soul_harvester=False,
        )
        self.assertFalse(thresholds_matched)
        self.assertFalse(all_matched)
        self.assertTrue(target_items_pass)
        self.assertEqual(match_reason, "ANVIL_FOUND_CRITERIA_FAILED")

    def test_anvil_or_soul_harvester_required_has_soul_harvester_thresholds_fail(self) -> None:
        """When either is required, having Soul Harvester but failing thresholds reports SOUL_HARVESTER_FOUND_CRITERIA_FAILED."""
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            has_anvil=False,
            require_target_items=False,
            anvil_or_soul_harvester_required=True,
            has_soul_harvester=True,
        )
        self.assertFalse(thresholds_matched)
        self.assertFalse(all_matched)
        self.assertTrue(target_items_pass)
        self.assertEqual(match_reason, "SOUL_HARVESTER_FOUND_CRITERIA_FAILED")

    def test_target_items_off_thresholds_pass_no_white_micro(self) -> None:
        """When Target Items are OFF, missing a White Microwave does not fail a threshold match."""
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
            target_items_found=True,
            has_white_micro=False,
            is_fox=False,
            has_anvil=False,
            require_target_items=False,
            target_items_require_white_micro=True,
        )
        self.assertTrue(thresholds_matched)
        self.assertTrue(all_matched)
        self.assertEqual(match_reason, "THRESHOLDS_MATCH")

    def test_target_items_off_thresholds_pass_perfect_match(self) -> None:
        """When Target Items are OFF and both thresholds and target items are met, result is PERFECT_MATCH_ALL."""
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
            target_items_found=True,
            has_white_micro=True,
            is_fox=False,
            has_anvil=False,
            require_target_items=False,
            target_items_require_white_micro=True,
        )
        self.assertTrue(thresholds_matched)
        self.assertTrue(all_matched)
        self.assertTrue(target_items_pass)
        self.assertEqual(match_reason, "PERFECT_MATCH_ALL")

    def test_target_items_off_thresholds_fail_target_only_match(self) -> None:
        """When thresholds fail but target items match and pause_on_target_items=True, seed matches on target items."""
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
            target_items_found=True,
            has_white_micro=True,
            is_fox=False,
            has_anvil=False,
            require_target_items=False,
            pause_on_target_items=True,
            target_items_require_white_micro=True,
        )
        self.assertFalse(thresholds_matched)
        self.assertTrue(target_only_matched)
        self.assertTrue(all_matched)
        self.assertEqual(match_reason, "TARGET_ITEMS_MATCH")

    def test_target_items_off_all_fail(self) -> None:
        """When thresholds fail and target items are not found, all_matched is False."""
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
            target_items_found=False,
            has_white_micro=False,
            is_fox=False,
            has_anvil=False,
            require_target_items=False,
        )
        self.assertFalse(thresholds_matched)
        self.assertFalse(all_matched)
        self.assertEqual(match_reason, "CRITERIA_NOT_MET")

    def test_target_items_on_fox_missing_anvil_fails(self) -> None:
        """When REQUIRE_TARGET_ITEMS is True, Fox missing Anvil strictly fails."""
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=True,
            has_anvil=False,
            require_target_items=True,
            anvil_required=True,
        )
        self.assertFalse(all_matched)
        self.assertEqual(match_reason, "FOX_MISSING_ANVIL_THRESHOLDS_PASS")

    def test_target_items_on_missing_white_micro_fails(self) -> None:
        """When REQUIRE_TARGET_ITEMS is True, target items without White Microwave fails."""
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
            target_items_found=True,
            has_white_micro=False,
            is_fox=False,
            has_anvil=False,
            require_target_items=True,
            target_items_require_white_micro=True,
        )
        self.assertFalse(all_matched)
        self.assertEqual(match_reason, "TARGET_ITEMS_NO_WHITE_MICROWAVE")

    def test_scan_stage1_seed_filter_fast_eval_fox_flag(self) -> None:
        """Test scan_stage1_seed_filter respects anvil_required flag during fast_eval."""
        mock_mem = unittest.mock.MagicMock()
        with patch.object(il, "get_stage_index", return_value=0), \
             patch.object(il, "get_map_interactable_counts", return_value={
                 "shady": 0, "moai": 10, "microwaves": 2, "boss_curses": 1, "magnets": 2,
             }):
            # When anvil_required=True and shady=0: skips heap and reports missing anvil
            res_true = il.scan_stage1_seed_filter(
                mock_mem, 0x1000, fast_eval=True, character=(0, "Fox"), anvil_required=True
            )
            self.assertTrue(res_true.get("shady_skipped"))
            self.assertFalse(res_true.get("all_matched"))
            self.assertEqual(res_true.get("match_reason"), "FOX_MISSING_ANVIL_THRESHOLDS_PASS")
            self.assertTrue(res_true.get("anvil_required"))

            # When anvil_required=False and shady=0: does NOT skip heap due to fox anvil
            # but rather evaluates normal criteria
            with patch.object(il, "scan_heap_interactables", return_value=([], [], [], [])):
                res_false = il.scan_stage1_seed_filter(
                    mock_mem, 0x1000, fast_eval=True, character=(0, "Fox"), anvil_required=False
                )
                self.assertFalse(res_false.get("anvil_required"))
                self.assertTrue(res_false.get("all_matched"))
                self.assertEqual(res_false.get("match_reason"), "THRESHOLDS_MATCH")


class TestStage1ReportTableDisplay(unittest.TestCase):
    """Test print_stage1_report prints Shady items tables when thresholds match and Target Items are off."""

    def setUp(self) -> None:
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
            "has_anvil": True,
            "anvil_count": 1,
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
            "rule_matches": [],
            "target_matches": [],
        }

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
            # Verify Table objects were printed
            table_titles = [
                getattr(call.args[0], "title", None)
                for call in mock_print.call_args_list
                if call.args and hasattr(call.args[0], "title")
            ]
            self.assertTrue(
                any("All Shady Items Ranked by Distance" in str(t) for t in table_titles),
                f"Expected All Shady Items Ranked table, got: {table_titles}",
            )
            self.assertTrue(
                any("Shady Guy Inventories" in str(t) for t in table_titles),
                f"Expected Shady Guy Inventories table, got: {table_titles}",
            )

    def test_fox_missing_anvil_plain_text_report(self) -> None:
        """When Fox is missing Anvil (criteria not met), plain text report prints status only and NO tables."""
        res = dict(self.mock_result)
        res["has_anvil"] = False
        res["anvil_count"] = 0
        res["target_items_pass"] = False
        res["thresholds_matched"] = False
        res["all_matched"] = False
        res["match_reason"] = "FOX_MISSING_ANVIL_THRESHOLDS_PASS"
        buf = io.StringIO()
        with patch.object(il, "console", None):
            with patch("sys.stdout", buf):
                il.print_stage1_report(res)
        output = buf.getvalue()
        self.assertIn("Status: [-] CRITERIA NOT MET", output)
        self.assertIn("Fox requires >= 1 Anvil on map", output)
        self.assertNotIn("Target Items", output)
        self.assertNotIn("ALL SHADY ITEMS RANKED BY DISTANCE", output)
        self.assertNotIn("SHADY GUY INVENTORIES", output)

    def test_fox_missing_anvil_rich_table_report(self) -> None:
        """When Rich console is available and Fox is missing Anvil, only status Panel is printed (NO tables)."""
        if il.console is None:
            self.skipTest("Rich console not installed")
        res = dict(self.mock_result)
        res["has_anvil"] = False
        res["anvil_count"] = 0
        res["target_items_pass"] = False
        res["thresholds_matched"] = False
        res["all_matched"] = False
        res["match_reason"] = "FOX_MISSING_ANVIL_THRESHOLDS_PASS"
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

    def test_fox_anvil_required_flag_false_plain_text_report(self) -> None:
        """When Fox has anvil_required=False, report shows Target Items (Opt) without Anvil fail."""
        res = dict(self.mock_result)
        res["has_anvil"] = False
        res["anvil_count"] = 0
        res["anvil_required"] = False
        res["target_items_pass"] = False
        res["thresholds_matched"] = True
        res["all_matched"] = True
        res["match_reason"] = "THRESHOLDS_MATCH"
        buf = io.StringIO()
        with patch.object(il, "console", None):
            with patch("sys.stdout", buf):
                il.print_stage1_report(res)
        output = buf.getvalue()
        self.assertNotIn("Target Items (Fox)", output)
        self.assertNotIn("Anvil Req", output)
        self.assertIn("Target Items (Opt):", output)

    def test_fox_anvil_required_flag_false_rich_table_report(self) -> None:
        """When Fox has anvil_required=False, Rich table shows Target Items (Opt) rather than Fox Anvil."""
        if il.console is None:
            self.skipTest("Rich console not installed")
        res = dict(self.mock_result)
        res["has_anvil"] = False
        res["anvil_count"] = 0
        res["anvil_required"] = False
        res["target_items_pass"] = False
        res["thresholds_matched"] = True
        res["all_matched"] = True
        res["match_reason"] = "THRESHOLDS_MATCH"
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
            self.assertFalse(any("Target Items (Fox)" in text for text in row_texts))
            self.assertTrue(any("Target Items (Opt)" in text for text in row_texts))

    def test_anvil_required_true_non_fox_rich_table_report(self) -> None:
        """When non-Fox has anvil_required=True, Rich table shows Target Items ({character}) with Anvil status."""
        if il.console is None:
            self.skipTest("Rich console not installed")
        res = dict(self.mock_result)
        res["character"] = "Megachad"
        res["is_fox"] = False
        res["has_anvil"] = True
        res["anvil_count"] = 1
        res["anvil_required"] = True
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
            self.assertTrue(any("Target Items (Megachad)" in text for text in row_texts))
            self.assertTrue(any("1 / 1 Anvil" in text for text in row_texts))

    def test_soul_harvester_required_rich_table_report(self) -> None:
        """When soul_harvester_required is True, checklist table includes Soul Harvester row."""
        if il.console is None:
            self.skipTest("Rich console not installed")
        res = dict(self.mock_result)
        res["soul_harvester_required"] = True
        res["has_soul_harvester"] = True
        res["soul_harvester_count"] = 1
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
            self.assertTrue(any("Target Items (Soul Harvester)" in text for text in row_texts))
            self.assertTrue(any("1 / 1 Soul Harvester" in text for text in row_texts))

    def test_soul_harvester_required_plain_text_report(self) -> None:
        """When soul_harvester_required is True, plain text report prints Soul Harvester requirement row."""
        res = dict(self.mock_result)
        res["soul_harvester_required"] = True
        res["has_soul_harvester"] = True
        res["soul_harvester_count"] = 1
        res["target_items_pass"] = True
        res["thresholds_matched"] = True
        res["all_matched"] = True
        res["match_reason"] = "PERFECT_MATCH_ALL"
        buf = io.StringIO()
        with patch.object(il, "console", None):
            with patch("sys.stdout", buf):
                il.print_stage1_report(res)
        output = buf.getvalue()
        self.assertIn("Target Items (Soul Harvester):", output)
        self.assertIn("MATCHED (1 Soul Harvester found on map)", output)

    def test_anvil_or_soul_harvester_required_rich_table_report(self) -> None:
        """When anvil_or_soul_harvester_required is True, checklist table includes Target Items (Anvil / SH) row."""
        if il.console is None:
            self.skipTest("Rich console not installed")
        res = dict(self.mock_result)
        res["anvil_or_soul_harvester_required"] = True
        res["has_anvil"] = True
        res["anvil_count"] = 1
        res["has_soul_harvester"] = False
        res["soul_harvester_count"] = 0
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
            self.assertTrue(any("Target Items (Anvil / SH)" in text for text in row_texts))
            self.assertTrue(any("1 / 1 Anvil" in text for text in row_texts))

    def test_anvil_or_soul_harvester_required_plain_text_report(self) -> None:
        """When anvil_or_soul_harvester_required is True, plain text report prints Anvil / SH requirement row."""
        res = dict(self.mock_result)
        res["anvil_or_soul_harvester_required"] = True
        res["has_anvil"] = False
        res["anvil_count"] = 0
        res["has_soul_harvester"] = True
        res["soul_harvester_count"] = 1
        res["target_items_pass"] = True
        res["thresholds_matched"] = True
        res["all_matched"] = True
        res["match_reason"] = "PERFECT_MATCH_ALL"
        buf = io.StringIO()
        with patch.object(il, "console", None):
            with patch("sys.stdout", buf):
                il.print_stage1_report(res)
        output = buf.getvalue()
        self.assertIn("Target Items (Anvil / SH):", output)
        self.assertIn("MATCHED (1 Soul Harvester found on map)", output)

    def test_required_item_ids_rich_table_report(self) -> None:
        """When required_item_ids has custom items, checklist table shows item name rows."""
        if il.console is None:
            self.skipTest("Rich console not installed")
        res = dict(self.mock_result)
        res["required_item_ids"] = [22]  # Dragonfire
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
            self.assertTrue(any("Target Items (Dragonfire)" in text for text in row_texts))
            self.assertTrue(any("1 / 1 Dragonfire" in text for text in row_texts))

    def test_required_item_ids_plain_text_report(self) -> None:
        """When required_item_ids has custom items, plain text report prints row with matching counts."""
        res = dict(self.mock_result)
        res["required_item_ids"] = [22]
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
        self.assertIn("Target Items (Dragonfire):", output)
        self.assertIn("MATCHED (1 Dragonfire found on map)", output)

    def test_required_item_ids_plain_text_failed_report(self) -> None:
        """When required item is missing, plain text report shows CRITERIA NOT MET and skips tables."""
        res = dict(self.mock_result)
        res["required_item_ids"] = [22]
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
        self.assertIn("requires >= 1 Dragonfire on map", output)


class TestRequiredItemIdsEvaluation(unittest.TestCase):
    """Test evaluate_stage1_criteria using required_item_ids and required_items_mode."""

    def test_empty_required_item_ids_passes_thresholds_normally(self) -> None:
        """When required_item_ids is empty, evaluation passes on thresholds alone."""
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
            target_items_found=False,
            has_white_micro=False,
            is_fox=False,
            require_target_items=False,
            required_item_ids=[],
        )
        self.assertTrue(thresholds_matched)
        self.assertTrue(all_matched)
        self.assertEqual(match_reason, "THRESHOLDS_MATCH")

    def test_single_required_item_id_missing_fails(self) -> None:
        """Single required item ID (Anvil 41) missing causes failure."""
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
            target_items_found=False,
            has_white_micro=False,
            is_fox=False,
            require_target_items=False,
            required_item_ids=[41],
            offered_item_ids=[],
        )
        self.assertFalse(thresholds_matched)
        self.assertFalse(all_matched)
        self.assertEqual(match_reason, "MISSING_ANVIL_THRESHOLDS_PASS")

    def test_single_required_item_id_present_passes(self) -> None:
        """Single required item ID present satisfies criteria."""
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            require_target_items=False,
            required_item_ids=[41],
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            require_target_items=False,
            required_item_ids=[22],
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            require_target_items=False,
            required_item_ids=[22],
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            require_target_items=False,
            required_item_ids=[41, 47],
            required_items_mode="any",
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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            require_target_items=False,
            required_item_ids=[41, 47],
            required_items_mode="any",
            offered_item_ids=[10, 20],
        )
        self.assertFalse(all_matched_fail)
        self.assertEqual(match_reason_fail, "MISSING_ANVIL_OR_SOUL_HARVESTER_THRESHOLDS_PASS")

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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            require_target_items=False,
            required_item_ids=[41, 47],
            required_items_mode="all",
            offered_item_ids=[41],
        )
        self.assertFalse(all_matched_partial)
        self.assertEqual(match_reason_partial, "MISSING_SOUL_HARVESTER_THRESHOLDS_PASS")

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
            target_items_found=False,
            has_white_micro=True,
            is_fox=False,
            require_target_items=False,
            required_item_ids=[41, 47],
            required_items_mode="all",
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


if __name__ == "__main__":
    unittest.main()

