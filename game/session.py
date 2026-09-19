"""Gameplay rules and session data, independent of rendering, audio and hardware."""

from dataclasses import dataclass, field

from game.rules import (
    BAD_WINDOW, GOOD_WINDOW, HEALTH_CHANGE, HIT_WINDOW, JUDGEMENT_WEIGHT,
    PERFECT_WINDOW, calculate_catch_score, calculate_score, hold_tick_times,
)


@dataclass
class GameSession:
    resolved_notes: set = field(default_factory=set)
    judgements: list = field(default_factory=list)
    counts: dict = field(default_factory=lambda: dict.fromkeys(JUDGEMENT_WEIGHT, 0))
    health: float = 100.0
    score: int = 0
    combo: int = 0
    max_combo: int = 0
    active_holds: dict = field(default_factory=dict)
    health_enabled: bool = True

    @classmethod
    def for_mode(cls, mode):
        session = cls()
        if mode == "catch":
            session.counts = {"catch": 0, "miss": 0}
        return session

    def judge(self, notes, lane, elapsed):
        candidates = (
            (abs(note.time - elapsed), index)
            for index, note in enumerate(notes)
            if index not in self.resolved_notes and note.lane == lane
            and abs(note.time - elapsed) <= HIT_WINDOW
        )
        closest = min(candidates, default=None)
        if closest is None:
            return None
        difference, index = closest
        judgement = "perfect" if difference <= PERFECT_WINDOW else (
            "good" if difference <= GOOD_WINDOW else "bad"
        )
        return index, judgement

    def _record(self, index, judgement, health_change):
        previous_health = self.health
        self.resolved_notes.add(index)
        self.judgements.append(judgement)
        self.counts[judgement] += 1
        if self.health_enabled:
            self.health = min(100.0, max(0.0, self.health + health_change))
        if judgement == "miss":
            self.combo = 0
        else:
            self._advance_combo()
        return previous_health

    def _advance_combo(self):
        self.combo += 1
        self.max_combo = max(self.max_combo, self.combo)

    def resolve_note(self, index, note, judgement, note_count, elapsed):
        if index in self.resolved_notes:
            return None
        previous_health = self._record(index, judgement, HEALTH_CHANGE[judgement])
        self.score = calculate_score(self.judgements, note_count)
        if judgement != "miss":
            ticks = tuple(t for t in hold_tick_times(note.time, note.end_time) if t > elapsed)
            if ticks:
                self.active_holds[index] = {"ticks": ticks, "next": 0, "end_time": note.end_time}
        return previous_health

    def resolve_catch(self, index, caught, note_count):
        if index in self.resolved_notes:
            return None
        previous_health = self._record(index, "catch" if caught else "miss", .55 if caught else -7.0)
        self.score = calculate_catch_score(self.counts["catch"], note_count)
        return previous_health

    def advance_holds(self, elapsed):
        """Yield the old health for each tick, applying each tick exactly once."""
        for index, state in tuple(self.active_holds.items()):
            ticks = state["ticks"]
            while state["next"] < len(ticks) and elapsed >= ticks[state["next"]]:
                state["next"] += 1
                previous_health = self.health
                if self.health_enabled:
                    self.health = min(100.0, self.health + .08)
                self._advance_combo()
                yield previous_health
            if elapsed > state["end_time"] + BAD_WINDOW:
                self.active_holds.pop(index, None)


def session_field(name):
    """Temporary view adapter while scenes migrate to explicit session access.

    There is only one copy of each value; legacy scene attributes delegate to it.
    """
    return property(
        lambda view: getattr(view.gameplay, name),
        lambda view, value: setattr(view.gameplay, name, value),
    )
