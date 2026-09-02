import math
import queue
import time

from game.rules import CI_NOTICE_SECONDS, CI_WARNING_SECONDS, smooth_progress
from ui_framework import DESIGN_WIDTH


class MinigameAnimationMixin:
    def _animate_common(self, now):
        elapsed = now - self.animation_epoch
        if self.particle_item is not None:
            y = self.particle_base_y + 13 * math.sin(elapsed * 0.8)
            self.canvas.coords(self.particle_item, self._x(540), self._y(y))
        if self.scroll_items:
            width = self.sources["scroll"].width
            offset = (elapsed * 72) % width
            for item, index, y in self.scroll_items:
                self.canvas.coords(item, self._x(index * width - offset), self._y(y))

    def _animate_title_select_morph(self, now):
        elapsed = now - self.scene_started
        progress = min(1.0, elapsed / 1.15)
        eased = progress * progress * (3 - 2 * progress)
        frame = min(11, round(progress * 11))
        if self.title_morph_logo_item is not None:
            x = 540 - 250 * eased
            y = 1000 - 245 * eased
            self.canvas.coords(self.title_morph_logo_item, self._x(x), self._y(y))
            self.canvas.itemconfigure(self.title_morph_logo_item, image=self.title_morph_logo_frames[frame])
        if self.title_morph_top_logo_item is not None:
            self.canvas.itemconfigure(self.title_morph_top_logo_item, image=self.title_morph_top_logo_frames[frame])
        if self.title_morph_press_item is not None:
            self.canvas.coords(self.title_morph_press_item, self._x(540), self._y(1735 + 100 * eased))
            self.canvas.itemconfigure(self.title_morph_press_item, image=self.title_morph_press_frames[frame])
        new_offset = 1120 * (1 - eased)
        delta = new_offset - self.title_select_offset
        if abs(delta) > 0.001:
            self.canvas.move("select", delta * self.scale, 0)
            self.title_select_offset = new_offset
        if progress >= 1.0:
            self.show_select()

    def _animate_entry(self, now):
        if self.entry_title_fade_started is not None:
            progress = min(1.0, (now - self.entry_title_fade_started) / 0.65)
            eased = progress * progress * (3 - 2 * progress)
            self._set_fade_opacity(eased)
            if progress >= 1.0:
                self.show_ci(fade_in=True)
            return
        if self.entry_choice is not None:
            elapsed = now - self.entry_choice_started
            if self.entry_choice == "guest":
                progress = min(1.0, elapsed / 0.72)
                frame = min(len(self.entry_card_frames) - 1, round(progress * (len(self.entry_card_frames) - 1)))
            else:
                frame = int(elapsed * 24) % len(self.entry_card_frames)
            if frame != self.entry_card_frame_shown:
                self.canvas.itemconfigure(self.entry_card_item, image=self.entry_card_frames[frame])
                self.entry_card_frame_shown = frame
            if now >= self.entry_choice_deadline:
                if self.entry_choice == "guest":
                    self.show_warning()
                else:
                    self._start_entry_title_transition()
            return
        elapsed = now - self.scene_started
        progress = min(1.0, elapsed / 0.72)
        frame = min(len(self.entry_card_frames) - 1, round(progress * (len(self.entry_card_frames) - 1)))
        if frame != self.entry_card_frame_shown:
            self.canvas.itemconfigure(self.entry_card_item, image=self.entry_card_frames[frame])
            self.entry_card_frame_shown = frame
        remaining = max(0, int(self.entry_deadline - now + 0.999))
        self._update_timer(self.entry_time_item, remaining, "entry_time_shown")
        if now >= self.entry_deadline:
            self._start_entry_title_transition()

    def _animate_warning(self, now):
        elapsed = now - self.scene_started
        progress = min(1.0, elapsed / 0.48)
        frame = min(len(self.warning_frames) - 1, round(progress * (len(self.warning_frames) - 1)))
        if frame != self.warning_frame_shown:
            self.canvas.itemconfigure(self.warning_item, image=self.warning_frames[frame])
            self.warning_frame_shown = frame
        if now >= self.warning_deadline:
            self._start_warning_mode_morph()

    def _animate_mode_select(self, now):
        self._animate_warning_mode_morph(now)
        if self.mode_icon_animation_started is not None:
            progress = min(1.0, (now - self.mode_icon_animation_started) / 0.58)
            frame = min(len(self.mode_icon_frames) - 1, round(progress * (len(self.mode_icon_frames) - 1)))
            if frame != self.mode_icon_frame_shown:
                self.canvas.itemconfigure(self.mode_icon_item, image=self.mode_icon_frames[frame])
                self.mode_icon_frame_shown = frame
            if progress >= 1.0:
                self.mode_icon_animation_started = None
                self.mode_icon_frames = ()
        remaining = max(0, int(self.mode_select_deadline - now + 0.999))
        self._update_timer(self.mode_time_item, remaining, "mode_time_shown")
        if now >= self.mode_select_deadline:
            self._confirm_mode()

    def _animate_warning_mode_morph(self, now):
        if self.mode_morph_in_started is None:
            return
        progress = min(1.0, (now - self.mode_morph_in_started) / 0.82)
        eased = progress * progress * (3 - 2 * progress)
        new_offset = 120.0 * (1.0 - eased)
        delta = new_offset - self.mode_morph_in_offset
        if abs(delta) > 0.001:
            self.canvas.move("mode_select", 0, delta * self.scale)
            self.mode_morph_in_offset = new_offset
        frame = min(len(self.warning_frames) - 1, round(eased * (len(self.warning_frames) - 1)))
        if frame != self.warning_frame_shown:
            self.canvas.itemconfigure(self.warning_item, image=self.warning_frames[frame])
            self.warning_frame_shown = frame
        self.canvas.coords(self.warning_item, self._x(540), self._y(1120 + 32 * eased))
        self.canvas.tag_raise(self.warning_item)
        if progress >= 1.0:
            self.canvas.delete(self.warning_item)
            self.warning_item = None
            self.warning_frames = ()
            self.mode_morph_in_started = None
            self.mode_morph_in_offset = 0.0

    def _animate_warning_select_morph(self, now):
        if self.select_morph_in_started is None:
            return
        progress = min(1.0, (now - self.select_morph_in_started) / 0.82)
        eased = progress * progress * (3 - 2 * progress)
        new_offset = 150.0 * (1 - eased)
        delta = new_offset - self.select_morph_in_offset
        if abs(delta) > 0.001:
            self.canvas.move("select", 0, delta * self.scale)
            self.select_morph_in_offset = new_offset
        frame = min(len(self.warning_frames) - 1, round(eased * (len(self.warning_frames) - 1)))
        if frame != self.warning_frame_shown:
            self.canvas.itemconfigure(self.warning_item, image=self.warning_frames[frame])
            self.warning_frame_shown = frame
        y = 1120 + (1263 - 1120) * eased
        self.canvas.coords(self.warning_item, self._x(540), self._y(y))
        self.canvas.tag_raise(self.warning_item)
        if progress >= 1.0:
            self.canvas.delete(self.warning_item)
            self.warning_item = None
            self.warning_frames = ()
            self.select_morph_in_started = None
            self.select_morph_in_offset = 0.0

    def _animate_next(self, now):
        elapsed = now - self.scene_started
        progress = min(1.0, elapsed / 0.72)
        eased = 1 - pow(1 - progress, 3)
        for item, start, end in self.next_morph_items:
            x = start[0] + (end[0] - start[0]) * eased
            y = start[1] + (end[1] - start[1]) * eased
            self.canvas.coords(item, self._x(x), self._y(y))
        if self.next_arrow_items:
            pulse = (elapsed * 12) % len(self.next_arrow_frames[0])
            frame = int(pulse)
            travel = 10 * math.sin(elapsed * 5.5)
            self.canvas.coords(self.next_arrow_items[0], self._x(365 - travel), self._y(900))
            self.canvas.coords(self.next_arrow_items[1], self._x(715 + travel), self._y(900))
            self.canvas.itemconfigure(self.next_arrow_items[0], image=self.next_arrow_frames[0][frame])
            self.canvas.itemconfigure(self.next_arrow_items[1], image=self.next_arrow_frames[1][frame])
        audio_finished = (
            self.next_audio_started
            and self.next_audio_channel is not None
            and not self.next_audio_channel.get_busy()
        )
        if now >= self.next_audio_deadline or audio_finished:
            self._begin_game_transition()

    def _animate_transition(self, now):
        if self.transition_phase == "closing":
            progress = min(1.0, (now - self.transition_started) / 0.48)
            eased = progress * progress * (3 - 2 * progress)
            self.canvas.coords(self.curtain_items[0], *self._scaled_box((0, 0, DESIGN_WIDTH, 960 * eased)))
            self.canvas.coords(self.curtain_items[1], *self._scaled_box((0, 1920 - 960 * eased, DESIGN_WIDTH, 1920)))
            if progress >= 1.0:
                self._start_game_scene()
        elif self.transition_phase == "opening":
            progress = min(1.0, (now - self.transition_started) / 0.55)
            eased = progress * progress * (3 - 2 * progress)
            self.canvas.coords(self.curtain_items[0], *self._scaled_box((0, 0, DESIGN_WIDTH, 960 * (1 - eased))))
            self.canvas.coords(self.curtain_items[1], *self._scaled_box((0, 960 + 960 * eased, DESIGN_WIDTH, 1920)))
            if progress >= 1.0:
                self.canvas.delete("curtain")
                self.transition_phase = None

    def _animate_result(self, now):
        elapsed = now - self.scene_started
        progress = min(1.0, elapsed / 1.05)
        c1 = 1.70158
        c3 = c1 + 1
        shifted = progress - 1
        eased = 1 + c3 * shifted * shifted * shifted + c1 * shifted * shifted
        rank_progress = min(1.0, max(0.0, (elapsed - 0.62) / 0.72))
        if rank_progress > 0 and not self.result_rank_voice_played:
            self.result_rank_voice_played = True
            self.result_rank_sfx_channel = self._play_sfx("rank_show.mp3", volume=0.68)
            self.result_rank_voice_channel = self._play_rank_voice()
        if self.result_rank_item is not None:
            rank_frame = min(
                len(self.result_rank_frames) - 1,
                round(rank_progress * (len(self.result_rank_frames) - 1)),
            )
            if rank_frame != self.result_rank_frame_shown:
                self.canvas.itemconfigure(self.result_rank_item, image=self.result_rank_frames[rank_frame])
                self.result_rank_frame_shown = rank_frame
        new_offset = 560 * (1 - eased)
        delta = new_offset - self.result_card_offset
        if abs(delta) > 0.001:
            self.canvas.move("result_card", 0, delta * self.scale)
            self.result_card_offset = new_offset
        if self.result_banner_item is not None:
            banner_frame = int(elapsed * 24) % len(self.result_banner_frames)
            if banner_frame != self.result_banner_frame_shown:
                self.canvas.itemconfigure(self.result_banner_item, image=self.result_banner_frames[banner_frame])
                self.result_banner_frame_shown = banner_frame
            banner_y = 840 + 85 * eased + 3 * math.sin(elapsed * 2.4)
            self.canvas.coords(self.result_banner_item, self._x(540), self._y(banner_y))
        count_progress = min(1.0, elapsed / 1.25)
        count_eased = 1 - pow(1 - count_progress, 3)
        final_values = {**self.result_final_counts, "score": self.score}
        for name, final_value in final_values.items():
            value = round(final_value * count_eased)
            if value != self.result_values_shown.get(name):
                size = 63 if name == "score" else 29
                self.canvas.itemconfigure(self.result_value_items[name], image=self._text(str(value), size))
                self.result_values_shown[name] = value
    def _animate_selection_scroll(self, now):
        if self.selection_scroll_started is None:
            return
        progress = min(1.0, (now - self.selection_scroll_started) / 0.52)
        sweep_eased = progress * progress * (3 - 2 * progress)
        if self.selection_sweep_item is not None:
            self.canvas.coords(self.selection_sweep_item, self._x(-150 + 1380 * sweep_eased), self._y(1125))
            self.canvas.tag_raise(self.selection_sweep_item)
        if progress < 0.48:
            part = progress / 0.48
            eased = 1 - pow(1 - part, 3)
            angle = eased * math.pi / 2
            old_x = 250.0 * math.sin(angle)
            old_offset = -180.0 * (1 - math.cos(angle))
            old_x_delta = old_x - self.selection_old_x
            old_delta = old_offset - self.selection_old_offset
            self.canvas.move("select_old", old_x_delta * self.scale, old_delta * self.scale)
            self.selection_old_x = old_x
            self.selection_old_offset = old_offset
            return
        if not self.selection_scroll_swapped:
            self.canvas.delete("select_old")
            self.canvas.itemconfigure("select_new", state="normal")
            self.selection_scroll_swapped = True
        part = (progress - 0.48) / 0.52
        eased = 1 - pow(1 - part, 3)
        angle = (1 - eased) * math.pi / 2
        new_x = 250.0 * math.sin(angle)
        new_offset = 180.0 * (1 - math.cos(angle))
        new_x_delta = new_x - self.selection_new_x
        new_delta = new_offset - self.selection_new_offset
        self.canvas.move("select_new", new_x_delta * self.scale, new_delta * self.scale)
        self.selection_new_x = new_x
        self.selection_new_offset = new_offset
        if progress >= 1.0:
            self.canvas.dtag("select_new", "select_new")
            self.selection_scroll_started = None
            if self.selection_sweep_item is not None:
                self.canvas.delete(self.selection_sweep_item)
                self.selection_sweep_item = None

    def _animate_total_result(self, now):
        elapsed = now - self.scene_started
        progress = min(1.0, elapsed / 1.35)
        eased = 1 - pow(1 - progress, 3)
        if not self.total_result_count_started:
            self.total_result_count_started = True
            self.total_result_count_channel = self._play_sfx("score_count.wav")
        value = round(sum(self.track_scores) * eased)
        if value != self.total_result_value_shown:
            self.canvas.itemconfigure(self.total_result_value_item, image=self._text(f"{value:,}", 76))
            self.total_result_value_shown = value
        if progress >= 1.0 and not self.total_result_count_finished:
            self.total_result_count_finished = True
            if self.total_result_count_channel is not None:
                self.total_result_count_channel.stop()
                self.total_result_count_channel = None
            self._play_sfx("score_added.wav")

    def _animate_ending(self, now):
        elapsed = now - self.scene_started
        logo_progress = smooth_progress((elapsed - 0.18) / 0.92)
        thanks_progress = smooth_progress((elapsed - 0.82) / 0.78)
        if elapsed >= 0.82 and not self.ending_voice_played:
            self.ending_voice_played = True
            self.ending_voice_channel = self._play_ending_voice()
        logo_scale = 0.78 + 0.22 * logo_progress + 0.025 * math.sin(logo_progress * math.pi)
        thanks_scale = 0.94 + 0.06 * thanks_progress
        float_offset = math.sin(max(0.0, elapsed - 1.7) * 1.45) * 3.5 * logo_progress
        logo_y = 1010 - 82 * logo_progress + float_offset
        thanks_y = 1190 - 68 * thanks_progress + float_offset * 0.55
        self._set_motion_item(
            self.ending_logo_item, "title_logo", logo_progress, logo_scale, self.ending_motion_state,
        )
        self._set_motion_item(
            self.ending_thanks_item, "thanksforplaying", thanks_progress, thanks_scale,
            self.ending_motion_state,
        )
        self.canvas.coords(self.ending_logo_item, self._x(540), self._y(logo_y))
        self.canvas.coords(self.ending_thanks_item, self._x(540), self._y(thanks_y))
        #accent_progress = smooth_progress((elapsed - 0.7) / 0.9)
        #accent_half_width = 285 * accent_progress
        #accent_pulse = 0.82 + 0.18 * math.sin(max(0.0, elapsed - 1.6) * 1.7) ** 2
        #self.canvas.coords(
        #    self.ending_accent_item,
        #    self._x(540 - accent_half_width * accent_pulse), self._y(1082 + float_offset * 0.3),
        #    self._x(540 + accent_half_width * accent_pulse), self._y(1090 + float_offset * 0.3),
        #)
        audio_finished = self.ending_audio_started and self.audio.available and not self.audio.is_playing()
        fallback_finished = now >= self.ending_audio_deadline
        if self.loading_phase is None and (audio_finished or fallback_finished):
            self._start_loading("ci", self.show_ci)

    def _animate_title(self, now):
        self._animate_title_fade(now)
        audio_finished = self.title_audio_started and self.audio.available and not self.audio.is_playing()
        fallback_finished = self.title_audio_started and now >= self.title_audio_deadline
        if (
            self.loading_phase is None
            and self.title_entry_morph_started is None
            and self.title_fade_started is None
            and (audio_finished or fallback_finished)
        ):
            self._start_loading("demonstration", self.show_demonstration)

    def _animate_demonstration(self, now):
        self._animate_game_media(now)
        self._update_game_frame(now)
        if self.demonstration_item is None or not self.demonstration_frames:
            return
        name = "demonstration_able" if self.coins_per_credit == 0 or self.credit_count > 0 else "demonstration_coin"
        if name != self.demonstration_overlay_name:
            self.demonstration_overlay_name = name
            self.demonstration_frames = self.preloaded_demonstration_frames[name]
            self.demonstration_frame_shown = -1
        frame = int((now - self.scene_started) * 20) % len(self.demonstration_frames)
        if frame != self.demonstration_frame_shown:
            self.canvas.itemconfigure(self.demonstration_item, image=self.demonstration_frames[frame])
            self.demonstration_frame_shown = frame
        self.canvas.tag_raise("demonstration_overlay")

    def _animate_ci(self, now):
        self._animate_title_fade(now)
        elapsed = now - self.scene_started
        warning_opacity = min(
            smooth_progress(elapsed / 0.36),
            smooth_progress((CI_WARNING_SECONDS - elapsed) / 0.34),
        )
        notice_elapsed = elapsed - CI_WARNING_SECONDS
        notice_opacity = min(
            smooth_progress(notice_elapsed / 0.36),
            smooth_progress((CI_NOTICE_SECONDS - notice_elapsed) / 0.34),
        )
        credits_elapsed = notice_elapsed - CI_NOTICE_SECONDS
        credits_opacity = smooth_progress(credits_elapsed / 0.52)
        opacity_by_name = {
            "epilepsywarning": warning_opacity,
            "notice": notice_opacity,
            "produced": credits_opacity,
            "gameengine": credits_opacity,
        }
        base_y = {
            "epilepsywarning": 1080,
            "notice": 1080,
            "produced": 1035,
            "gameengine": 1305,
        }
        for name, opacity in opacity_by_name.items():
            scale = 0.975 + opacity * 0.025
            self._set_motion_item(self.ci_items[name], name, opacity, scale, self.ci_motion_state)
            rise = (1.0 - opacity) * 18
            self.canvas.coords(self.ci_items[name], self._x(540), self._y(base_y[name] + rise))
        if self.loading_phase is None and self.title_fade_started is None and now >= self.ci_deadline:
            self._start_loading("title", self.show_title)

    def _animate_title_fade(self, now):
        if self.title_fade_started is None or self.fade_item is None:
            return
        progress = min(1.0, (now - self.title_fade_started) / 1.25)
        eased = progress * progress * (3 - 2 * progress)
        self._set_fade_opacity(1.0 - eased)
        if progress >= 1.0:
            self.canvas.delete(self.fade_item)
            self.fade_item = None
            self.title_fade_started = None

    def _animate_title_entry_morph(self, now):
        if self.title_entry_morph_started is None or self.title_entry_logo_item is None:
            return
        progress = min(1.0, (now - self.title_entry_morph_started) / 0.72)
        frame = min(len(self.title_entry_logo_frames) - 1, round(progress * (len(self.title_entry_logo_frames) - 1)))
        if frame != self.title_entry_logo_frame_shown:
            self.canvas.itemconfigure(self.title_entry_logo_item, image=self.title_entry_logo_frames[frame])
            self.title_entry_logo_frame_shown = frame
        self.canvas.tag_raise(self.title_entry_logo_item)
        if progress >= 1.0:
            self.canvas.delete(self.title_entry_logo_item)
            self.title_entry_logo_item = None
            self.title_entry_logo_frames = ()
            self.title_entry_morph_started = None

    def _animate(self):
        if not self.running or self.unrecoverable_error:
            return
        now = time.monotonic()
        self._poll_events()
        if self.unrecoverable_error:
            return
        if self.scene != "game":
            self._animate_common(now)
        if self.loading_phase is not None:
            self._animate_loading_transition(now)
            self.root.after(16, self._animate)
            return
        if self.transition_phase is not None:
            self._animate_transition(now)
        elif self.scene == "preload":
            self._animate_preload(now)
        elif self.scene == "title":
            self._animate_title(now)
        elif self.scene == "ci":
            self._animate_ci(now)
        elif self.scene == "entry":
            self._animate_entry(now)
            self._animate_title_entry_morph(now)
        elif self.scene == "warning":
            self._animate_warning(now)
        elif self.scene == "mode_select":
            self._animate_mode_select(now)
        elif self.scene == "title_select":
            self._animate_title_select_morph(now)
        elif self.scene == "select":
            self._animate_warning_select_morph(now)
            self._animate_selection_scroll(now)
            self._animate_select_preview(now)
            remaining = max(0, int(self.select_deadline - now + 0.999))
            self._update_timer(self.select_time_item, remaining, "select_time_shown")
            if now >= self.select_deadline:
                self.show_next()
        elif self.scene == "next":
            self._animate_next(now)
        elif self.scene == "game":
            self._animate_game_media(now)
            self._update_game_frame(now)
        elif self.scene == "demonstration":
            self._animate_demonstration(now)
        elif self.scene == "result":
            self._animate_result(now)
            remaining = max(0, int(self.result_deadline - now + 0.999))
            self._update_timer(self.result_time_item, remaining, "result_time_shown")
            if (
                now >= self.result_deadline
                and self.loading_phase is None
            ):
                self.start_result_transition()
        elif self.scene == "total_result":
            self._animate_total_result(now)
            remaining = max(0, int(self.total_result_deadline - now + 0.999))
            self._update_timer(self.total_result_time_item, remaining, "total_result_time_shown")
            if now >= self.total_result_deadline:
                self.start_total_result_transition()
        elif self.scene == "ending":
            self._animate_ending(now)
        self.root.after(16, self._animate)

    def _consume_serial(self, message):
        self.serial_buffer += message.lower().replace("\r", "").replace("\n", "")
        self.serial_buffer_updated_at = time.monotonic()
        self._drain_serial_buffer()

    def _drain_serial_buffer(self, force=False):
        entries = tuple(
            (command, action) for command, action in (
                (self.settings["button_1"], 0), (self.settings["button_2"], 1),
                (self.settings["button_3"], 2), (self.settings["button_4"], 3),
                (self.settings["coin_message"], "coin"),
            )
            if command
        )
        commands = tuple(command for command, _ in entries)
        if not entries:
            self.serial_buffer = ""
            return
        while self.serial_buffer:
            matches = [
                (self.serial_buffer.find(command), action, command) for command, action in entries
            ]
            matches = [match for match in matches if match[0] >= 0]
            if not matches:
                self.serial_buffer = self.serial_buffer[-max(len(command) for command in commands):]
                return
            position, action, command = min(matches, key=lambda match: (match[0], -len(match[2])))
            end = position + len(command)
            longer_possible = any(candidate.startswith(command) and len(candidate) > len(command) for candidate in commands)
            if not force and end == len(self.serial_buffer) and longer_possible:
                return
            self.serial_buffer = self.serial_buffer[end:]
            if action == "coin":
                self._insert_coin()
            else:
                self.press_button(action)
        self.serial_buffer = self.serial_buffer[-256:]

    def _poll_events(self):
        if self.unrecoverable_error:
            return
        try:
            while True:
                event = self.event_queue.get_nowait()
                if event[0] == "serial":
                    self.attach_serial(event[1])
                    self.serial_connection_failed = False
                    if self.serial_failure_item is not None:
                        self.canvas.delete(self.serial_failure_item)
                        self.serial_failure_item = None
                    self._print("serial input ready")
                elif event[0] == "status":
                    self._print(event[1])
                elif event[0] == "serial_failure":
                    self._mark_serial_failed(event[1])
                elif event[0] == "preload_status":
                    self._update_preload_status(event[1])
                elif event[0] == "preload_stage":
                    self._set_preload_stage(event[1], event[2], announce=event[2] == "CHECKING")
                elif event[0] == "preload_ready":
                    self._finish_preload()
                elif event[0] == "preload_error":
                    self.show_unrecoverable_error("MINIGAME_PRELOAD_FAILED", event[1])
        except queue.Empty:
            pass

    def _show_serial_failure(self):
        if self.scene != "title" or self.serial_failure_item is not None:
            return
        self.serial_failure_item = self._image(
            "fail_io", 540, 1445, tags=("title", "serial_failure"),
        )

    def _mark_serial_failed(self, detail):
        self.serial_connection_failed = True
        self._print(f"[SerialIO] serial connection failed: {detail}")
        self._show_serial_failure()

    def _poll_serial(self):
        if not self.running:
            return
        if self.serial is not None:
            try:
                while self.serial.in_waiting > 0:
                    message = self.serial.read()
                    if message is not None:
                        self._consume_serial(message)
                if self.serial_buffer and time.monotonic() - self.serial_buffer_updated_at >= 0.05:
                    self._drain_serial_buffer(force=True)
            except Exception as error:
                failed_serial = self.serial
                self.serial = None
                try:
                    failed_serial.close()
                except Exception:
                    pass
                self._mark_serial_failed(error)
        if not self.unrecoverable_error:
            self.root.after(25, self._poll_serial)
