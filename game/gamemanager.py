import math
import time

from PIL import Image, ImageDraw

from game.rules import (
    BAD_WINDOW,
    GOOD_WINDOW,
    HEALTH_CHANGE,
    HIT_WINDOW,
    PERFECT_WINDOW,
    calculate_catch_score,
    calculate_score,
    combo_after_judgement,
    hold_tick_times,
)


class MinigameGameplayMixin:
    def _autoplay_active(self):
        return self.scene == "demonstration" or getattr(self, "debug_autoplay", False)

    def _autoplay_mania_notes(self, elapsed):
        if not self._autoplay_active():
            return
        for index, note in enumerate(self.track.notes):
            if index not in self.resolved_notes and elapsed >= note.time:
                self._trigger_lane_help(note.lane)
                self._resolve_note(index, "perfect")

    def _update_autoplay_catcher(self, now):
        if not self._autoplay_active():
            self._animate_catcher(now)
            return
        next_note = next(
            (note for index, note in enumerate(self.track.notes) if index not in self.resolved_notes),
            None,
        )
        if next_note is not None:
            self.catcher_x = 90.0 + next_note.x / 512.0 * 900.0
        self.catcher_velocity = 0.0
        self.catcher_last_update = now
        if self.catcher_item is not None:
            self.canvas.coords(self.catcher_item, self._x(self.catcher_x), self._y(1725))

    def _mania_note_positions(self, note, elapsed, lead_time, start_y, hit_y, active_hold):
        head_y = hit_y if active_hold else min(
            hit_y,
            max(start_y, hit_y - (note.time - elapsed) / lead_time * (hit_y - start_y)),
        )
        tail_time = note.end_time if note.end_time is not None else note.time
        tail_y = min(hit_y, hit_y - (tail_time - elapsed) / lead_time * (hit_y - start_y))
        body_top_y = max(start_y, tail_y + 22)
        return head_y, tail_y, body_top_y, tail_y >= start_y

    def _scroll_lead_time(self, base_seconds):
        return base_seconds / self.settings.get("scroll_speed", 1.30)

    def _move_catcher(self, lane):
        now = time.monotonic()
        self._animate_catcher(now)
        direction = -1 if lane == 0 else 1
        self.catcher_velocity = min(920.0, max(-920.0, self.catcher_velocity + direction * 520.0))

    def _animate_catcher(self, now):
        if self.catcher_last_update is None:
            self.catcher_last_update = now
            return
        delta = min(0.05, max(0.0, now - self.catcher_last_update))
        self.catcher_last_update = now
        decay = math.exp(-5.2 * delta)
        self.catcher_x += self.catcher_velocity * (1.0 - decay) / 5.2
        self.catcher_velocity *= decay
        if self.catcher_x <= 180.0:
            self.catcher_x = 180.0
            self.catcher_velocity = max(0.0, self.catcher_velocity)
        elif self.catcher_x >= 900.0:
            self.catcher_x = 900.0
            self.catcher_velocity = min(0.0, self.catcher_velocity)
        if abs(self.catcher_velocity) < 2.0:
            self.catcher_velocity = 0.0
        if self.catcher_item is not None:
            self.canvas.coords(self.catcher_item, self._x(self.catcher_x), self._y(1725))

    def _catch_burst_sources(self):
        if self.catch_burst_source_frames:
            return self.catch_burst_source_frames
        colors = ((255, 226, 145), (255, 157, 116), (255, 246, 218), (242, 126, 169))
        frames = []
        for frame_index in range(20):
            progress = frame_index / 19
            image = Image.new("RGBA", (180, 180), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            alpha = round(175 * pow(1.0 - progress, 1.35))
            distance = 12.0 + 54.0 * (1.0 - pow(1.0 - progress, 2))
            radius = max(2, round(7.0 * (1.0 - progress)))
            for index in range(8):
                angle = math.tau * index / 8 + 0.18
                x = 90 + math.cos(angle) * distance
                y = 90 + math.sin(angle) * distance + 12 * progress * progress
                color = (*colors[index % len(colors)], alpha)
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
            ring_radius = 10 + 30 * progress
            draw.ellipse(
                (90 - ring_radius, 90 - ring_radius, 90 + ring_radius, 90 + ring_radius),
                outline=(255, 235, 190, round(alpha * 0.7)), width=3,
            )
            frames.append(image)
        self.catch_burst_source_frames = tuple(frames)
        return self.catch_burst_source_frames

    def _start_catch_burst(self, x, y):
        if not self.catch_burst_frames:
            return
        item = self.canvas.create_image(
            self._x(x), self._y(y), image=self.catch_burst_frames[0], anchor="center", tags=("catch_burst",),
        )
        self.catch_bursts.append({"item": item, "started": time.monotonic(), "frame": 0})

    def _animate_catch_bursts(self, now):
        for burst in tuple(self.catch_bursts):
            progress = min(1.0, max(0.0, (now - burst["started"]) / 0.42))
            frame = min(len(self.catch_burst_frames) - 1, round(progress * (len(self.catch_burst_frames) - 1)))
            if frame != burst["frame"]:
                self.canvas.itemconfigure(burst["item"], image=self.catch_burst_frames[frame])
                burst["frame"] = frame
            if progress >= 1.0:
                self.canvas.delete(burst["item"])
                self.catch_bursts.remove(burst)

    def _resolve_catch(self, index, caught):
        if index in self.resolved_notes:
            return
        self.resolved_notes.add(index)
        judgement = "catch" if caught else "miss"
        self.judgements.append(judgement)
        self.counts[judgement] += 1
        previous_health = self.health
        if caught:
            self._play_sfx("hitsound.wav", volume=0.45)
            self.health = min(100.0, self.health + 0.55)
            self._advance_combo()
            if self.counts["catch"] % 5 == 0:
                note = self.track.notes[index]
                self._start_catch_burst(90.0 + note.x / 512.0 * 900.0, 1625.0)
        else:
            self.health = max(0.0, self.health - 7.0)
            self._break_combo()
        self.score = calculate_catch_score(self.counts["catch"], len(self.track.notes))
        item = self.note_items.pop(index, None)
        if item is not None:
            self.canvas.delete(item)
        if self.score_item is not None:
            self.canvas.itemconfigure(self.score_item, image=self._text(str(self.score), 58))
        if self.catch_score_item is not None:
            self.canvas.itemconfigure(self.catch_score_item, image=self._text(str(self.score), 70))
        self._start_health_animation(previous_health, self.health)

    def _judge(self, lane):
        if self.game_started is None:
            return
        elapsed = self._game_elapsed()
        candidates = [
            (abs(note.time - elapsed), index)
            for index, note in enumerate(self.track.notes)
            if index not in self.resolved_notes and note.lane == lane and abs(note.time - elapsed) <= HIT_WINDOW
        ]
        if not candidates:
            return
        difference, index = min(candidates)
        if difference <= PERFECT_WINDOW:
            judgement = "perfect"
        elif difference <= GOOD_WINDOW:
            judgement = "good"
        else:
            judgement = "bad"
        self._resolve_note(index, judgement)

    def _resolve_note(self, index, judgement):
        if index in self.resolved_notes:
            return
        self.resolved_notes.add(index)
        self.judgements.append(judgement)
        self.counts[judgement] += 1
        previous_health = self.health
        self.health = min(100.0, max(0.0, self.health + HEALTH_CHANGE[judgement]))
        self.score = calculate_score(self.judgements, len(self.track.notes))
        if judgement == "miss":
            self._break_combo()
        else:
            self._play_sfx("hitsound.wav", volume=0.45)
            self._advance_combo()
            note = self.track.notes[index]
            ticks = tuple(tick for tick in hold_tick_times(note.time, note.end_time) if tick > self._game_elapsed())
            if ticks:
                self.active_holds[index] = {"ticks": ticks, "next": 0, "end_time": note.end_time}
        self.last_feedback = judgement
        self.feedback_started = time.monotonic()
        self.feedback_until = self.feedback_started + 0.58
        self.feedback_frame_shown = 0
        if self.score_item is not None:
            self.canvas.itemconfigure(self.score_item, image=self._text(str(self.score), 58))
        self._start_health_animation(previous_health, self.health)
        if self.judgement_item is not None:
            self.canvas.itemconfigure(self.judgement_item, image=self.judgement_frames[self.last_feedback][0])
            self.feedback_visible = True

    def _advance_combo(self):
        self.combo = combo_after_judgement(self.combo, "perfect")
        self.max_combo = max(self.max_combo, self.combo)
        self.combo_animation_started = time.monotonic()
        self.combo_frame_shown = -1
        self.combo_photo_cache.clear()
        if self.game_mode == "catch" and self.catch_combo_item is not None:
            self.canvas.itemconfigure(self.catch_combo_item, image=self._text(f"x{self.combo}", 80))
        elif self.combo_item is not None:
            self.canvas.itemconfigure(self.combo_item, image=self._combo_photo(self.combo, 70))

    def _break_combo(self):
        self.combo = 0
        self.combo_animation_started = None
        self.combo_frame_shown = -1
        self.combo_photo_cache.clear()
        if self.game_mode == "catch" and self.catch_combo_item is not None:
            self.canvas.itemconfigure(self.catch_combo_item, image="")
        elif self.combo_item is not None:
            self.canvas.itemconfigure(self.combo_item, image="")

    def _animate_catch_combo(self, now):
        if self.catch_combo_item is None or self.combo <= 0:
            return
        if self.combo_animation_started is None:
            size = 80
            y = 1725.0
        else:
            progress = min(1.0, (now - self.combo_animation_started) / 0.28)
            bounce = math.sin(progress * math.pi) * 22
            size = round(80 + math.sin(progress * math.pi) * 12)
            y = 1725.0 - bounce
            if progress >= 1.0:
                self.combo_animation_started = None
        state = size, round(y, 1), self.combo
        if state == self.combo_frame_shown:
            return
        self.canvas.itemconfigure(self.catch_combo_item, image=self._text(f"x{self.combo}", size))
        self.canvas.coords(self.catch_combo_item, self._x(90), self._y(y))
        self.combo_frame_shown = state

    def _animate_combo(self, now):
        if self.combo_item is None or self.combo <= 0:
            return
        if self.combo_animation_started is None:
            size = 78
            y = 790.0
        else:
            progress = min(1.0, (now - self.combo_animation_started) / 0.24)
            if progress < 0.34:
                part = progress / 0.34
                eased = part * part * (3 - 2 * part)
                size = round(70 + 14 * eased)
                y = 798 - 14 * eased
            elif progress < 0.7:
                part = (progress - 0.34) / 0.36
                eased = part * part * (3 - 2 * part)
                size = round(84 - 7 * eased)
                y = 784 + 7 * eased
            else:
                part = (progress - 0.7) / 0.3
                eased = part * part * (3 - 2 * part)
                size = round(77 + eased)
                y = 791 - eased
            if progress >= 1.0:
                self.combo_animation_started = None
        state = size, round(y, 1)
        if state == self.combo_frame_shown:
            return
        self.canvas.itemconfigure(self.combo_item, image=self._combo_photo(self.combo, size))
        self.canvas.coords(self.combo_item, self._x(540), self._y(y))
        self.combo_frame_shown = state

    def _start_health_animation(self, previous, current):
        self.health_animation_from = self.display_health
        self.health_animation_started = time.monotonic()
        self.health_pulse_started = self.health_animation_started
        self.health_change_direction = 1 if current > previous else -1 if current < previous else 0

    def _animate_health(self, now):
        if self.health_fill_item is None:
            return
        if self.health_animation_started is not None:
            progress = min(1.0, (now - self.health_animation_started) / 0.28)
            eased = progress * progress * (3 - 2 * progress)
            self.display_health = self.health_animation_from + (self.health - self.health_animation_from) * eased
            if progress >= 1.0:
                self.display_health = self.health
                self.health_animation_started = None
        pulse_progress = 1.0
        if self.health_pulse_started is not None:
            pulse_progress = min(1.0, (now - self.health_pulse_started) / 0.34)
            if pulse_progress >= 1.0:
                self.health_pulse_started = None
        pulse = math.sin(pulse_progress * math.pi) * (0.08 if self.health_change_direction >= 0 else 0.13)
        shake = 0.0
        if self.health_change_direction < 0 and pulse_progress < 1.0:
            shake = math.sin(pulse_progress * math.pi * 6) * 4 * (1 - pulse_progress)
        self._update_health_image(self.display_health, 1.0 + pulse, shake)

    def _update_health_image(self, value=None, width_scale=1.0, shake=0.0):
        if self.health_fill_item is None:
            return
        value = self.health if value is None else value
        state = round(value, 1), round(width_scale, 2)
        self.canvas.coords(
            self.health_fill_item,
            self._x(self.health_fill_x + shake),
            self._y(self.health_fill_y),
        )
        if state == self.health_visible_state:
            return
        self.health_visible_state = state
        source_name = (
            "catch_health"
            if self.game_mode == "catch"
            else "health_4k"
            if self.game_mode == "4k"
            else "health"
        )
        source = self.sources[source_name]
        if value <= 0:
            self.canvas.itemconfigure(self.health_fill_item, image="")
            return
        if self.game_mode == "catch":
            visible_width = max(1, round(source.width * value / 100.0))
            crop = source.crop((0, 0, visible_width, source.height))
        else:
            visible_height = max(1, round(source.height * value / 100.0))
            crop = source.crop((0, source.height - visible_height, source.width, source.height))
        width = max(1, round(crop.width * width_scale))
        if width != crop.width:
            crop = crop.resize((width, crop.height), Image.Resampling.LANCZOS)
        self.health_dynamic_photo = self._scaled_photo(crop)
        self.canvas.itemconfigure(self.health_fill_item, image=self.health_dynamic_photo)

    def _update_hold_ticks(self, elapsed):
        for index, state in tuple(self.active_holds.items()):
            ticks = state["ticks"]
            while state["next"] < len(ticks) and elapsed >= ticks[state["next"]]:
                state["next"] += 1
                self._play_sfx("hitsound.wav", volume=0.45)
                previous_health = self.health
                self.health = min(100.0, self.health + 0.08)
                self._advance_combo()
                self._start_health_animation(previous_health, self.health)
            if elapsed > state["end_time"] + BAD_WINDOW:
                self.active_holds.pop(index, None)

    def _update_feedback_image(self):
        if self.judgement_item is None or not self.feedback_visible:
            return
        now = time.monotonic()
        if now >= self.feedback_until:
            self.canvas.itemconfigure(self.judgement_item, image="")
            self.feedback_visible = False
            return
        frames = self.judgement_frames[self.last_feedback]
        progress = max(0.0, (now - self.feedback_started) / 0.58)
        frame = min(len(frames) - 1, int(progress * len(frames)))
        if frame != self.feedback_frame_shown:
            self.canvas.itemconfigure(self.judgement_item, image=frames[frame])
            self.feedback_frame_shown = frame

    def _trigger_lane_help(self, lane):
        if lane < 0 or lane >= len(self.lane_help_items):
            return
        self.lane_help_started[lane] = time.monotonic()
        self.lane_help_frame_shown[lane] = -1

    def _animate_lane_help(self, now):
        for lane, started in tuple(self.lane_help_started.items()):
            item, frames = self.lane_help_items[lane]
            progress = min(1.0, max(0.0, (now - started) / 0.3))
            frame = min(len(frames) - 1, round(progress * (len(frames) - 1)))
            if frame != self.lane_help_frame_shown.get(lane):
                self.canvas.itemconfigure(item, image=frames[frame])
                self.lane_help_frame_shown[lane] = frame
            if progress >= 1.0:
                self.lane_help_started.pop(lane, None)
                self.lane_help_frame_shown.pop(lane, None)

    def _update_catch_game_frame(self, now):
        if self.scene not in ("game", "demonstration") or self.game_started is None:
            return
        elapsed = self._game_elapsed()
        self._update_autoplay_catcher(now)
        autoplay = self._autoplay_active()
        lead_time = self._scroll_lead_time(1.65)
        start_y = 520.0
        catch_y = 1625.0
        catcher_half_width = max(88.0, 132.0 - (self.track.circle_size - 5.0) * 10.0)
        for index, note in enumerate(self.track.notes):
            if index in self.resolved_notes:
                continue
            target_x = 90.0 + note.x / 512.0 * 900.0
            time_until = note.time - elapsed
            if time_until <= 0:
                caught = autoplay or abs(target_x - self.catcher_x) <= catcher_half_width
                self._resolve_catch(index, caught)
                continue
            if time_until <= lead_time:
                y = catch_y - time_until / lead_time * (catch_y - start_y)
                if index not in self.note_items:
                    self.note_items[index] = self.canvas.create_image(
                        self._x(target_x), self._y(y), image=self._asset_photo("catch_object"),
                        anchor="center", tags=("catch_note",),
                    )
                else:
                    self.canvas.coords(self.note_items[index], self._x(target_x), self._y(y))
        self.canvas.tag_raise("catch_note")
        self.canvas.tag_raise("catch_burst")
        self.canvas.tag_raise("catch_catcher")
        self.canvas.tag_raise("catch_hud")
        self.canvas.tag_raise("game_health")
        self._animate_catch_combo(now)
        self._animate_catch_bursts(now)
        self._animate_health(now)
        demonstration_finished = self.scene == "demonstration" and elapsed >= self.demonstration_end_time
        gameplay_finished = self.scene == "game" and (self.health <= 0 or elapsed >= self.track.duration + 1.2)
        if not self.game_finishing and (demonstration_finished or gameplay_finished):
            self.game_finishing = True
            self.audio.stop(180)
            if self.scene == "demonstration":
                target = "demonstration" if self.demonstration_queue else "ci"
                self._start_loading(target, self._complete_demonstration)
            else:
                self._start_loading("result", self.show_result)

    def _update_game_frame(self, now):
        if self.scene not in ("game", "demonstration") or self.game_started is None:
            return
        if self.game_mode == "catch":
            self._update_catch_game_frame(now)
            return
        elapsed = self._game_elapsed()
        self._update_hold_ticks(elapsed)
        self._autoplay_mania_notes(elapsed)
        if not self._autoplay_active():
            for index, note in enumerate(self.track.notes):
                if index not in self.resolved_notes and elapsed > note.time + BAD_WINDOW:
                    self._resolve_note(index, "miss")
        lead_time = self._scroll_lead_time(2.0)
        start_y = 520.0
        hit_y = self.judgement_line_y
        visible_notes = set()
        for index, note in enumerate(self.track.notes):
            active_hold = index in self.active_holds
            if index in self.resolved_notes and not active_hold:
                continue
            time_until = note.time - elapsed
            tail_until = (note.end_time if note.end_time is not None else note.time) - elapsed
            if tail_until >= -BAD_WINDOW and time_until <= lead_time:
                visible_notes.add(index)
                y, tail_y, body_top_y, tail_visible = self._mania_note_positions(
                    note, elapsed, lead_time, start_y, hit_y, active_hold,
                )
                x = self.lane_origin_x + note.lane * self.lane_width
                if index not in self.note_items:
                    body = None
                    tail = None
                    if note.end_time is not None and note.end_time > note.time:
                        body = self.canvas.create_rectangle(
                            self._x(x + self.lane_width * 0.112), self._y(body_top_y),
                            self._x(x + self.lane_width * 0.888), self._y(y + 22),
                            fill="#145fda" if note.lane % 2 == 0 else "#d7d7dc", outline="", tags=("game_note",),
                        )
                        if tail_visible:
                            tail = self.canvas.create_image(
                                self._x(x), self._y(tail_y), image=self.note_photos[note.lane],
                                anchor="nw", tags=("game_note",),
                            )
                    head = self.canvas.create_image(
                        self._x(x), self._y(y), image=self.note_photos[note.lane], anchor="nw", tags=("game_note",),
                    )
                    self.note_items[index] = {"body": body, "tail": tail, "head": head}
                else:
                    items = self.note_items[index]
                    self.canvas.coords(items["head"], self._x(x), self._y(y))
                    if items["body"] is not None:
                        self.canvas.coords(
                            items["body"], self._x(x + self.lane_width * 0.112), self._y(body_top_y),
                            self._x(x + self.lane_width * 0.888), self._y(y + 22),
                        )
                        if tail_visible and items["tail"] is None:
                            items["tail"] = self.canvas.create_image(
                                self._x(x), self._y(tail_y), image=self.note_photos[note.lane],
                                anchor="nw", tags=("game_note",),
                            )
                        elif tail_visible:
                            self.canvas.coords(items["tail"], self._x(x), self._y(tail_y))
                        elif items["tail"] is not None:
                            self.canvas.delete(items["tail"])
                            items["tail"] = None
        for index in tuple(self.note_items):
            if index not in visible_notes:
                for item in self.note_items.pop(index).values():
                    if item is not None:
                        self.canvas.delete(item)
        self.canvas.tag_raise("game_line")
        self.canvas.tag_raise("lane_help")
        self.canvas.tag_raise("game_note")
        self.canvas.tag_raise("game_combo")
        self.canvas.tag_raise("game_feedback")
        self.canvas.tag_raise("game_health")
        self._animate_combo(now)
        self._animate_health(now)
        self._animate_lane_help(now)
        self._update_feedback_image()
        demonstration_finished = self.scene == "demonstration" and elapsed >= self.demonstration_end_time
        gameplay_finished = self.scene == "game" and (self.health <= 0 or elapsed >= self.track.duration + 1.6)
        if not self.game_finishing and (demonstration_finished or gameplay_finished):
            self.game_finishing = True
            self.audio.stop(180)
            if self.scene == "demonstration":
                target = "demonstration" if self.demonstration_queue else "ci"
                self._start_loading(target, self._complete_demonstration)
            else:
                self._start_loading("result", self.show_result)
