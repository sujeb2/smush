import unittest
from types import SimpleNamespace

from game.rules import MAX_SCORE
from game.session import GameSession


def note(time=1.0, lane=0, end_time=None):
    return SimpleNamespace(time=time, lane=lane, end_time=end_time)


class GameSessionTests(unittest.TestCase):
    def test_judgement_selects_nearest_unresolved_note_in_lane(self):
        session = GameSession()
        notes = [note(1.0), note(1.08), note(1.09, lane=1)]
        self.assertEqual(session.judge(notes, 0, 1.09), (1, "perfect"))
        session.resolve_note(1, notes[1], "perfect", len(notes), 1.09)
        self.assertEqual(session.judge(notes, 0, 1.09), (0, "good"))
        self.assertIsNone(session.judge(notes, 0, 2.0))

    def test_judgement_windows(self):
        session = GameSession()
        for elapsed, expected in ((0, "perfect"), (.04, "perfect"), (.1, "good"),
                                  (.2, "bad"), (.3, "bad")):
            self.assertEqual(session.judge([note(0)], 0, elapsed), (0, expected))
        self.assertIsNone(session.judge([note(0)], 0, .301))

    def test_duplicate_note_has_no_effect_and_miss_breaks_combo(self):
        session = GameSession()
        session.resolve_note(0, note(), "perfect", 2, 1)
        self.assertIsNone(session.resolve_note(0, note(), "miss", 2, 2))
        self.assertEqual((session.score, session.combo, session.health), (MAX_SCORE // 2, 1, 100))
        session.resolve_note(1, note(), "miss", 2, 2)
        self.assertEqual((session.combo, session.max_combo, session.health), (0, 1, 93))
        self.assertEqual(session.judgements, ["perfect", "miss"])

    def test_catch_rules_work_without_a_view(self):
        session = GameSession.for_mode("catch")
        session.health = 50
        session.resolve_catch(0, True, 2)
        session.resolve_catch(1, False, 2)
        self.assertEqual(session.counts, {"catch": 1, "miss": 1})
        self.assertAlmostEqual(session.health, 43.55)
        self.assertEqual((session.score, session.combo, session.max_combo), (MAX_SCORE // 2, 0, 1))
        self.assertIsNone(session.resolve_catch(1, True, 2))

    def test_hold_ticks_catch_up_once_and_expire(self):
        session = GameSession()
        session.resolve_note(0, note(0, end_time=1), "good", 1, .3)
        self.assertEqual(list(session.advance_holds(.49)), [])
        self.assertEqual(len(list(session.advance_holds(.8))), 2)
        self.assertEqual(list(session.advance_holds(.8)), [])
        self.assertEqual(len(list(session.advance_holds(1.3))), 1)
        self.assertFalse(session.active_holds)
        self.assertEqual(session.combo, 4)
        self.assertEqual(session.counts["good"], 1)
        self.assertEqual(session.score, round(MAX_SCORE * .65))

    def test_sessions_do_not_share_collections(self):
        first, second = GameSession(), GameSession()
        first.resolve_note(0, note(), "perfect", 1, 1)
        self.assertFalse(second.resolved_notes)
        self.assertFalse(second.judgements)
        self.assertEqual(second.counts["perfect"], 0)

    def test_health_is_clamped_and_misses_do_not_start_holds(self):
        session = GameSession()
        session.health = 1
        session.resolve_note(0, note(0, end_time=10), "miss", 2, 0)
        self.assertEqual(session.health, 0)
        self.assertFalse(session.active_holds)
        session.health = 99.9
        session.resolve_note(1, note(), "perfect", 2, 1)
        self.assertEqual(session.health, 100)
