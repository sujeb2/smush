import os
import random
import time

from PIL import Image

from game.rules import (
    CI_CREDITS_SECONDS,
    CI_NOTICE_SECONDS,
    CI_WARNING_SECONDS,
    EVENT_TRACK_COUNT,
    JUDGEMENT_WEIGHT,
    calculate_catch_score,
    calculate_accuracy,
    calculate_score,
    event_result_destination,
    group_charts_by_song,
    is_clear,
    rank_for_accuracy,
)
from game.persistence import save_progress


class MinigameFlowMixin:
    def _insert_coin(self):
        if self.coins_per_credit <= 0:
            return
        self.coin_count += 1
        self._play_sfx("coin.wav")
        if self.coin_count >= self.coins_per_credit:
            earned, self.coin_count = divmod(self.coin_count, self.coins_per_credit)
            self.credit_count += earned
            self._play_sfx("credit.wav")
        self._refresh_credit_status()
        self._print(f"coin accepted: {self._credit_status_text()}")

    def _handle_key(self, event):
        if event.keysym in ("F8", "f8"):
            self._toggle_debug_autoplay()
            return
        if event.keysym in ("minus", "KP_Subtract", "-"):
            self._open_debug_test_mode()
            return
        if self.scene == "game" and self.game_mode == "4k":
            lane_keys = {
                "d": 0, "D": 0, "Left": 0,
                "f": 1, "F": 1, "Down": 1,
                "j": 2, "J": 2, "Up": 2,
                "k": 3, "K": 3, "Right": 3,
            }
            lane = lane_keys.get(event.keysym)
            if lane is not None:
                self.press_button(lane)
            return
        if event.keysym in ("Left", "a", "A", "space"):
            self.press_button(0)
        elif event.keysym in ("Right", "d", "D", "Return", "KP_Enter"):
            self.press_button(1)

    def _open_debug_test_mode(self):
        if not self.running or self.test_mode_callback is None:
            return
        self._print("debug key received, opening original test mode UI")
        self.test_mode_callback()

    def _toggle_debug_autoplay(self):
        self.debug_autoplay = not self.debug_autoplay
        status = "enabled" if self.debug_autoplay else "disabled"
        self._print(f"debug autoplay {status}")

    def press_button(self, lane):
        if (
            not self.running
            or self.transition_phase is not None
            or self.loading_phase is not None
            or self.entry_title_fade_started is not None
            or self.title_entry_morph_started is not None
            or self.mode_morph_in_started is not None
        ):
            return
        if self.scene == "title":
            self._play_sfx("start.wav")
            self._play_sfx("ok.wav")
            self._start_title_entry_morph()
        elif self.scene == "entry":
            if self.entry_choice is not None:
                return
            if lane == 0:
                self._show_entry_choice("guest")
            else:
                self._show_entry_choice("cancel")
        elif self.scene == "mode_select":
            if lane == 0:
                self._cycle_mode()
            else:
                self._confirm_mode()
        elif self.scene == "select":
            if (
                self.select_fade_in_started is not None
                or self.select_morph_in_started is not None
                or self.selection_scroll_started is not None
            ):
                return
            if lane == 0:
                self._cycle_selection()
            elif self.selection_phase == "song":
                self._confirm_song()
            else:
                self._play_sfx("ok.wav")
                self.show_next()
        elif self.scene == "game":
            if self.game_mode == "catch":
                self._move_catcher(lane)
            else:
                self._trigger_lane_help(lane)
                self._judge(lane)
        elif self.scene == "demonstration":
            if self.coins_per_credit == 0 or self.credit_count > 0:
                self._start_demonstration_entry()
        elif self.scene == "result":
            self.start_result_transition()
        elif self.scene == "total_result" and lane == 1:
            self.start_total_result_transition()

    def _reset_selection(self):
        self.song_index = 0
        self.difficulty_index = 0
        self.selection_phase = "song"
        self.track = self.song_groups[0][0]

    def _apply_game_mode(self, mode):
        charts = self.charts_by_mode[mode]
        if not charts:
            return False
        self.game_mode = mode
        self.charts = charts
        self.song_groups = group_charts_by_song(charts)
        self._reset_selection()
        return True

    def _cycle_mode(self):
        if self.mode_icon_animation_started is not None:
            return
        self._play_sfx("cursor_select.wav")
        previous_index = self.mode_index
        mode_names = ("2k", "4k", "catch")
        self.mode_index = (self.mode_index + 1) % len(mode_names)
        previous_source = self.sources[f"mode_{mode_names[previous_index]}"]
        source = self.sources[f"mode_{mode_names[self.mode_index]}"]
        frames = []
        for index in range(24):
            progress = index / 23
            eased = progress * progress * (3 - 2 * progress)
            if progress < 0.72:
                scale = 0.62 + 0.45 * (1 - pow(1 - progress / 0.72, 3))
            else:
                scale = 1.07 + (1.0 - 1.07) * ((progress - 0.72) / 0.28)
            width = max(1, round(source.width * scale))
            height = max(1, round(source.height * scale))
            next_frame = source.resize((width, height), Image.Resampling.LANCZOS)
            next_opacity = min(1.0, max(0.0, (progress - 0.08) / 0.48))
            next_alpha = next_frame.getchannel("A").point(
                lambda value, factor=next_opacity: round(value * factor)
            )
            next_frame.putalpha(next_alpha)
            old_scale = 1.0 - 0.18 * eased
            old_width = max(1, round(previous_source.width * old_scale))
            old_height = max(1, round(previous_source.height * old_scale))
            old_frame = previous_source.resize((old_width, old_height), Image.Resampling.LANCZOS)
            old_opacity = max(0.0, 1.0 - progress / 0.62)
            old_alpha = old_frame.getchannel("A").point(
                lambda value, factor=old_opacity: round(value * factor)
            )
            old_frame.putalpha(old_alpha)
            frame = Image.new("RGBA", (680, 300), (0, 0, 0, 0))
            frame.alpha_composite(old_frame, ((frame.width - old_width) // 2, (frame.height - old_height) // 2))
            frame.alpha_composite(next_frame, ((frame.width - width) // 2, (frame.height - height) // 2))
            frames.append(self._photo(frame))
        self.mode_icon_frames = tuple(frames)
        self.mode_icon_frame_shown = 0
        self.mode_icon_animation_started = time.monotonic()
        self.canvas.itemconfigure(self.mode_icon_item, image=self.mode_icon_frames[0])
        self._update_mode_description()
        self._print(f"mode selected: {mode_names[self.mode_index].upper()}")

    def _confirm_mode(self):
        if self.mode_icon_animation_started is not None:
            return
        mode = ("2k", "4k", "catch")[self.mode_index]
        if not self._apply_game_mode(mode):
            self._play_sfx("cursor_select.wav")
            self.mode_select_deadline = time.monotonic() + 5.0
            self._print(f"[ChartManager] no compatible {mode} chart was found")
            return
        self._play_sfx("ok.wav")
        self._start_loading("select", self._show_initial_select)

    def _show_initial_select(self):
        if self.track_index == 0:
            self.track_scores = [0] * EVENT_TRACK_COUNT
            self.track_names = [""] * EVENT_TRACK_COUNT
            try:
                save_progress(
                    self.progress_path, self.track_index, EVENT_TRACK_COUNT, self.track_scores, self.track_names,
                )
            except OSError as error:
                self._print(f"progress save failed: {error}")
        self._reset_selection()
        self.show_select()

    def _start_warning_select_morph(self):
        if self.scene != "warning":
            return
        self._show_initial_select()
        self.select_morph_in_started = time.monotonic()
        self.select_morph_in_offset = 150.0
        self.canvas.move("select", 0, self.select_morph_in_offset * self.scale)
        self.warning_frames = tuple(self._photo(frame) for frame in self._warning_select_sources())
        self.warning_frame_shown = 0
        self.warning_item = self.canvas.create_image(
            self._x(540), self._y(1120), image=self.warning_frames[0], anchor="center", tags=("warning_select_morph",),
        )
        self.canvas.tag_raise(self.warning_item)
        self._print("warning to music select morph started")

    def _start_warning_mode_morph(self):
        if self.scene != "warning":
            return
        self.show_mode_select()
        self.mode_morph_in_started = time.monotonic()
        self.mode_morph_in_offset = 120.0
        self.mode_select_deadline += 0.82
        self.canvas.move("mode_select", 0, self.mode_morph_in_offset * self.scale)
        self.warning_frames = tuple(self._photo(frame) for frame in self._warning_mode_sources())
        self.warning_frame_shown = 0
        self.warning_item = self.canvas.create_image(
            self._x(540), self._y(1120), image=self.warning_frames[0], anchor="center", tags=("warning_mode_morph",),
        )
        self.canvas.tag_raise(self.warning_item)
        self._print("[AnimationManager] warning to mode select morph started")

    def _cycle_selection(self):
        self._play_sfx("cursor_select.wav")
        previous_preview = self._track_preview_key(self.track)
        if self.selection_phase == "song":
            self.song_index = (self.song_index + 1) % len(self.song_groups)
            self.difficulty_index = 0
            self.track = self.song_groups[self.song_index][0]
            self._print(f"[ChartManager] song selected: {self.track.artist} - {self.track.title}")
        else:
            difficulties = self.song_groups[self.song_index]
            self.difficulty_index = (self.difficulty_index + 1) % len(difficulties)
            self.track = difficulties[self.difficulty_index]
            self._print(f"[ChartManager] difficulty selected: {self.track.difficulty}")
        self._refresh_selection_list()
        if self._track_preview_key(self.track) != previous_preview:
            self._schedule_select_preview(1.0)

    def _confirm_song(self):
        self._play_sfx("ok.wav")
        self.selection_phase = "difficulty"
        self.difficulty_index = 0
        self.track = self.song_groups[self.song_index][0]
        if self.selection_heading_item is not None:
            self.canvas.itemconfigure(self.selection_heading_item, image=self._text("DIFFICULTY SELECT", 54))
        self.canvas.delete("select_shell")
        self._build_selection_shell(("select", "select_shell"))
        self._refresh_selection_list()
        self._print(f"difficulty select visible, song: {self.track.title}")

    def _refresh_selection_list(self):
        self.canvas.delete("select_list")
        if self.selection_sweep_item is not None:
            self.canvas.delete(self.selection_sweep_item)
            self.selection_sweep_item = None
        self.selection_scroll_started = None
        self._build_selection_list(("select", "select_list", "select_dynamic"))

    def _start_selection_scroll(self):
        self.canvas.addtag_withtag("select_old", "select_list")
        self.canvas.dtag("select_old", "select_list")

    def _finish_selection_scroll_setup(self):
        self._build_selection_list(("select", "select_list", "select_dynamic", "select_new"))
        self.selection_scroll_started = time.monotonic()
        self.selection_old_offset = 0.0
        self.selection_new_offset = 180.0
        self.selection_old_x = 0.0
        self.selection_new_x = 250.0
        self.selection_scroll_swapped = False
        self.canvas.move(
            "select_new", self.selection_new_x * self.scale, self.selection_new_offset * self.scale,
        )
        self.canvas.itemconfigure("select_new", state="hidden")
        self._create_selection_sweep()

    def show_title(self, fade_in=False):
        self.scene = "title"
        self.title_audio_started = False
        self.title_audio_deadline = time.monotonic() + 68.5
        self.entry_choice = None
        self.fade_started = None
        self.title_fade_started = None
        self.entry_title_fade_started = None
        self.result_fade_started = None
        self.ending_fade_in_started = None
        self.select_fade_in_started = None
        self.transition_phase = None
        self._build_scene()
        self.scene_started = time.monotonic()
        self.title_audio_deadline = self.scene_started + 68.5
        if fade_in:
            self._create_fade_overlay(1.0)
            self.title_fade_started = self.scene_started
        self.root.after(80, self._play_title_audio)
        self._print(f"[AnimationManager] title visible, mode: {self.settings['mode']}, track: {self._track_key()}")

    def _play_title_audio(self):
        if not self.running or self.scene != "title":
            return
        self.title_audio_started = True
        self.title_audio_deadline = time.monotonic() + 68.5
        self.audio.play(os.path.join(self.bgm_root, "title.mp3"), fade_ms=500)

    def show_ci(self, fade_in=False):
        if not self.preload_complete:
            self.show_preload(lambda: self.show_ci(fade_in=fade_in))
            return
        self.scene = "ci"
        self.entry_title_fade_started = None
        self.title_fade_started = None
        self._build_scene()
        self.scene_started = time.monotonic()
        self.ci_deadline = self.scene_started + CI_WARNING_SECONDS + CI_NOTICE_SECONDS + CI_CREDITS_SECONDS
        if fade_in:
            self._create_fade_overlay(1.0)
            self.title_fade_started = self.scene_started
        credits_delay = round((CI_WARNING_SECONDS + CI_NOTICE_SECONDS) * 1000) + 80
        self.root.after(credits_delay, lambda: self._play_sfx("ci.wav") if self.scene == "ci" else None)
        self._print("title intermission visible, sequence duration: 8 seconds")

    def show_entry(self):
        self.scene = "entry"
        self.entry_choice = None
        self.entry_choice_started = 0.0
        self.entry_choice_deadline = 0.0
        self.entry_title_fade_started = None
        self.entry_deadline = time.monotonic() + 20.0
        self._build_scene()
        self.scene_started = time.monotonic()
        self.entry_deadline = self.scene_started + 20.0
        self.root.after(80, self._play_entry_audio)
        self.root.after(140, lambda: self._play_sfx("card_show.wav") if self.scene == "entry" else None)
        self._print("[AnimationManager] entry visible, guest play only")

    def _start_title_entry_morph(self):
        if self.scene != "title" or self.title_entry_morph_started is not None:
            return
        self.show_entry()
        source = self.sources["title_logo"]
        frames = []
        for index in range(32):
            progress = index / 31
            eased = progress * progress * (3 - 2 * progress)
            scale = 1.0 + 0.72 * eased
            width = max(1, round(source.width * scale))
            height = max(1, round(source.height * scale))
            frame = source.resize((width, height), Image.Resampling.BICUBIC)
            opacity = max(0.0, 1.0 - eased)
            alpha = frame.getchannel("A").point(lambda value, factor=opacity: round(value * factor))
            frame.putalpha(alpha)
            frames.append(self._photo(frame))
        self.title_entry_logo_frames = tuple(frames)
        self.title_entry_logo_frame_shown = 0
        self.title_entry_logo_item = self.canvas.create_image(
            self._x(540), self._y(1000), image=self.title_entry_logo_frames[0],
            anchor="center", tags=("title_entry_morph",),
        )
        self.title_entry_morph_started = time.monotonic()
        self.canvas.tag_raise(self.title_entry_logo_item)
        self._print("[AnimationManager] title to entry logo morph started")

    def _show_entry_choice(self, choice):
        if self.scene != "entry" or self.entry_choice is not None:
            return
        now = time.monotonic()
        self.entry_choice = choice
        self.entry_choice_started = now
        self.entry_choice_deadline = now + 3.0
        sources = self._entry_card_sources("entry_guest") if choice == "guest" else self._entry_cancel_sources()
        self.entry_card_frames = tuple(self._photo(frame) for frame in sources)
        self.entry_card_frame_shown = 0
        self.canvas.itemconfigure(self.entry_card_item, image=self.entry_card_frames[0])
        self.canvas.itemconfigure("entry_time", state="hidden")
        self.canvas.tag_raise(self.entry_card_item)
        self._play_sfx("ok.wav")
        self._play_sfx("card_show.wav")
        self._print(f"[AnimationManager] entry {choice} selected, confirmation: 3 seconds")

    def _play_entry_audio(self):
        if self.running and self.scene in ("entry", "warning"):
            self.audio.play(os.path.join(self.bgm_root, "entry.mp3"), loop=True, fade_ms=320)

    def _start_entry_title_transition(self):
        if self.scene != "entry" or self.entry_title_fade_started is not None:
            return
        self.entry_title_fade_started = time.monotonic()
        self.audio.stop(650)
        self._create_fade_overlay(0.0)
        self._print("[AnimationManager] entry to title intermission fade started")

    def show_warning(self):
        if self.scene != "entry":
            return
        self.scene = "warning"
        self._build_scene()
        self.scene_started = time.monotonic()
        self.warning_deadline = self.scene_started + 3.0
        self.root.after(120, lambda: self._play_sfx("card_show.wav") if self.scene == "warning" else None)
        self._print("[AnimationManager] warning visible, duration: 3 seconds")

    def show_mode_select(self):
        self.scene = "mode_select"
        self.mode_index = 0
        self.mode_icon_animation_started = None
        self.mode_select_deadline = time.monotonic() + 20.0
        self._build_scene()
        self.scene_started = time.monotonic()
        self.mode_select_deadline = self.scene_started + 20.0
        self._print("mode select visible, default: 2K")

    def show_select(self):
        self.scene = "select"
        self.result_fade_started = None
        self.result_select_morph_started = None
        self.result_transition_target = None
        self.select_morph_in_started = None
        self.select_morph_in_offset = 0.0
        self.select_deadline = time.monotonic() + self.settings["select_seconds"]
        self.select_fade_in_started = None
        self.audio.stop(250)
        self._build_scene()
        self.scene_started = time.monotonic()
        self.select_deadline = self.scene_started + self.settings["select_seconds"]
        self._schedule_select_preview(1.0)
        self.root.after(140, lambda: self._play_sfx("card_show.wav") if self.scene == "select" else None)
        self._print(f"music select visible, songs: {len(self.song_groups)}, track: {self._track_key()}")

    def start_title_select_morph(self):
        if self.scene != "title":
            return
        self.audio.stop(420)
        self._reset_selection()
        self.scene = "title_select"
        self.select_deadline = time.monotonic() + self.settings["select_seconds"]
        self._build_scene()
        self.scene_started = time.monotonic()
        self._print("[AnimationManager] title to music select morph started")

    def show_next(self):
        self.scene = "next"
        self.next_audio_started = False
        self.next_audio_channel = None
        self._build_scene()
        self.scene_started = time.monotonic()
        self.next_audio_deadline = self.scene_started + 5.1
        self.root.after(80, self._play_next_audio)
        self.root.after(180, lambda: self._play_sfx("card_show.wav") if self.scene == "next" else None)
        self._print(f"next music visible, chart: {os.path.basename(self.track.path)}")

    def _play_next_audio(self):
        if not self.running or self.scene != "next" or self.transition_phase is not None:
            return
        self.next_audio_started = True
        self.next_audio_deadline = time.monotonic() + 4.7
        if self.audio.current_path == self.track.audio_path and self.audio.is_playing():
            self.audio.set_music_volume(0.58)
        else:
            self.audio.play(
                self.track.audio_path, fade_ms=220,
                start_seconds=self._preview_start_seconds(self.track), volume=0.58,
            )
        self.next_audio_channel = self.audio.play_sfx(
            os.path.join(self.bgm_root, "next.mp3"), volume=0.34,
        )

    def _play_scene_audio(self, scene, filename, loop=False, fade_ms=0):
        if self.running and self.scene == scene and not (scene == "result" and self.result_fade_started is not None):
            self.audio.play(os.path.join(self.bgm_root, filename), loop=loop, fade_ms=fade_ms)


    def _play_sfx(self, filename, volume=1.0):
        return self.audio.play_sfx(os.path.join(self.sfx_root, filename), volume=volume)

    def _play_rank_voice(self):
        return self.audio.play_sfx(
            os.path.join(self.voice_root, f"rank_{self.rank.lower()}.mp3"), volume=0.9,
        )

    def _play_ending_voice(self):
        return self.audio.play_sfx(
            os.path.join(self.voice_root, "see_you.mp3"), volume=0.9,
        )

    def _stop_result_rank_audio(self):
        for attribute in ("result_rank_sfx_channel", "result_rank_voice_channel"):
            channel = getattr(self, attribute)
            if channel is not None:
                channel.stop()
                setattr(self, attribute, None)

    def _update_timer(self, item, remaining, shown_attribute, size=52):
        shown = getattr(self, shown_attribute)
        if item is not None and remaining != shown:
            self.canvas.itemconfigure(item, image=self._text(str(remaining), size))
            setattr(self, shown_attribute, remaining)
            if 0 < remaining <= 10 and remaining != self.timer_sfx_value:
                self.timer_sfx_value = remaining
                self._play_sfx("timer_count.wav")

    def _start_loading(self, target, action):
        if self.loading_phase is not None or self.entry_title_fade_started is not None:
            return
        self.loading_target = target
        self.loading_action = action
        self.loading_phase = "fading_out"
        self.loading_started = time.monotonic()
        self._create_fade_overlay(0.0)
        self._print(f"[AnimationManager] fade transition started: {self.scene} to {target}")

    def _animate_loading_transition(self, now):
        if self.loading_phase == "fading_out":
            progress = min(1.0, (now - self.loading_started) / 0.48)
            eased = progress * progress * (3 - 2 * progress)
            self._set_fade_opacity(eased)
            if progress >= 1.0:
                action = self.loading_action
                self.loading_action = None
                action()
                self._create_fade_overlay(1.0)
                self.loading_phase = "fading_in"
                self.loading_started = now
            return
        if self.loading_phase == "fading_in":
            progress = min(1.0, (now - self.loading_started) / 0.52)
            eased = progress * progress * (3 - 2 * progress)
            self._set_fade_opacity(1.0 - eased)
            if progress >= 1.0:
                self.canvas.delete(self.fade_item)
                self.fade_item = None
                self.loading_phase = None
                self.loading_target = None

    def _begin_game_transition(self):
        if self.loading_phase is not None or self.scene != "next":
            return
        self._start_loading("game", self._start_game_scene)
        self._print("music selected transition started")

    def _start_game_scene(self):
        if self.next_audio_channel is not None:
            self.next_audio_channel.stop()
            self.next_audio_channel = None
        pre_roll = 2.0 + self.track.audio_lead_in / 1000.0
        self._open_gameplay_scene("game", pre_roll, 0.0)
        self._print(f"game loaded, notes: {len(self.track.notes)}, format: v{self.track.format_version}")

    def _open_gameplay_scene(self, scene, pre_roll, audio_offset):
        self.audio.stop()
        self.scene = scene
        self.scene_started = time.monotonic()
        self.game_started = self.scene_started + pre_roll
        self.game_audio_started = False
        self.game_audio_offset = audio_offset
        self.resolved_notes = set()
        self.judgements = []
        self.counts = {key: 0 for key in (("catch", "miss") if self.game_mode == "catch" else JUDGEMENT_WEIGHT)}
        self.health = 100.0
        self.display_health = 100.0
        self.score = 0
        self.combo = 0
        self.max_combo = 0
        self.active_holds = {}
        self.catcher_x = 540.0
        self.catcher_velocity = 0.0
        self.catcher_last_update = self.scene_started
        self.catch_bursts = []
        self.combo_animation_started = None
        self.combo_frame_shown = -1
        self.health_animation_started = None
        self.health_animation_from = 100.0
        self.health_pulse_started = None
        self.health_change_direction = 0
        self.health_dynamic_photo = None
        self.health_visible_state = None
        self.feedback_until = 0.0
        self.last_feedback = ""
        self.feedback_visible = False
        self.game_finishing = False
        self.note_items = {}
        self.lane_help_started = {}
        self.lane_help_frame_shown = {}
        self._prepare_game_media(self.track)
        self._build_scene()
        delay = round(pre_roll * 1000)
        self.game_audio_job = self.root.after(delay, self._start_chart_audio)

    def _demonstration_candidates(self, mode=None):
        excluded = {"testchart", "sample-chart"}
        modes = (mode,) if mode is not None else ("2k", "4k", "catch")
        return tuple(
            chart
            for candidate_mode in modes
            for chart in self.charts_by_mode.get(candidate_mode, ())
            if os.path.basename(chart.folder).casefold() not in excluded
        )

    def show_demonstration(self):
        self.demonstration_queue = [
            (mode, random.choice(candidates))
            for mode in ("2k", "4k", "catch")
            if (candidates := self._demonstration_candidates(mode))
        ]
        if not self.demonstration_queue:
            self.show_ci()
            return
        self.demonstration_restore_state = self.game_mode, self.track
        self._show_next_demonstration()

    def _show_next_demonstration(self):
        self.game_mode, self.track = self.demonstration_queue.pop(0)
        first_note_time = self.track.notes[0].time if self.track.notes else 0.0
        start_time = max(0.0, first_note_time - 1.5)
        self.demonstration_end_time = min(self.track.duration + 0.8, start_time + 18.0)
        self._open_gameplay_scene("demonstration", 1.0, start_time)
        self._print(
            f"{self.game_mode.upper()} demonstration visible, chart: {os.path.basename(self.track.path)}, "
            f"start: {start_time:.2f}s"
        )

    def _restore_demonstration_state(self):
        if self.demonstration_restore_state is None:
            return
        self.game_mode, self.track = self.demonstration_restore_state
        self.demonstration_restore_state = None
        self.demonstration_queue = []

    def _complete_demonstration(self):
        if self.game_audio_job is not None:
            self.root.after_cancel(self.game_audio_job)
            self.game_audio_job = None
        self.audio.stop(180)
        if self.demonstration_queue:
            self._show_next_demonstration()
            return
        self._restore_demonstration_state()
        self.show_ci()

    def _start_demonstration_entry(self):
        if self.scene != "demonstration" or self.loading_phase is not None:
            return
        self.game_finishing = True
        if self.game_audio_job is not None:
            self.root.after_cancel(self.game_audio_job)
            self.game_audio_job = None
        self.audio.stop(180)
        self._play_sfx("start.wav")
        self._play_sfx("ok.wav")

        def show_entry():
            self._restore_demonstration_state()
            self.show_entry()

        self._start_loading("entry", show_entry)

    def _start_chart_audio(self):
        self.game_audio_job = None
        if not self.running or self.scene not in ("game", "demonstration"):
            return
        self.audio.play(self.track.audio_path, start_seconds=self.game_audio_offset)
        self.game_started = time.monotonic()
        self.game_audio_started = True
        self.game_video_next_frame = self.game_started
        self._print(f"chart started: {os.path.basename(self.track.path)}")

    def _game_elapsed(self):
        audio_offset = getattr(self, "game_audio_offset", 0.0)
        if self.game_audio_started:
            position = self.audio.position_seconds()
            if position is not None:
                return audio_offset + position
        return audio_offset + time.monotonic() - self.game_started

    def show_result(self):
        if self.scene != "game":
            return
        for index in range(len(self.track.notes)):
            if index not in self.resolved_notes:
                if self.game_mode == "catch":
                    self._resolve_catch(index, False)
                else:
                    self._resolve_note(index, "miss")
        self.audio.stop(250)
        self.scene = "result"
        self.result_fade_started = None
        self.score = (
            calculate_catch_score(self.counts["catch"], len(self.track.notes))
            if self.game_mode == "catch"
            else calculate_score(self.judgements, len(self.track.notes))
        )
        self.track_scores[self.track_index] = self.score
        self.track_names[self.track_index] = self.track.title
        self.result_final_counts = dict(self.counts)
        self.accuracy = calculate_accuracy(
            self.judgements, len(self.track.notes), catch_mode=self.game_mode == "catch",
        )
        self.rank = rank_for_accuracy(self.accuracy)
        self.result_rank_voice_played = False
        self.result_rank_sfx_channel = None
        self.result_rank_voice_channel = None
        self.result_transition_target = None
        now = time.monotonic()
        self.result_unlock_at = now + 3.0
        duration = self.settings["result_seconds"] if is_clear(self.health) else 3.0
        self.result_deadline = now + duration
        self._build_scene()
        self.scene_started = time.monotonic()
        self.result_unlock_at = self.scene_started + 3.0
        duration = self.settings["result_seconds"] if is_clear(self.health) else 3.0
        self.result_deadline = self.scene_started + duration
        self._print(
            f"result loaded, score: {self.score}, accuracy: {self.accuracy:.2f}%, "
            f"rank: {self.rank}, health: {self.health:.1f}"
        )
        result_bgm = "result.mp3"
        self.root.after(180, lambda: self._play_scene_audio("result", result_bgm, fade_ms=350))
        self.root.after(220, lambda: self._play_sfx("card_show.wav") if self.scene == "result" else None)

    def start_result_transition(self):
        if (
            self.scene != "result"
            or self.loading_phase is not None
            or time.monotonic() < self.result_unlock_at
        ):
            return
        self._stop_result_rank_audio()
        self.result_transition_target, next_track = event_result_destination(self.track_index, is_clear(self.health))
        self.track_index = next_track
        try:
            save_progress(
                self.progress_path, self.track_index, EVENT_TRACK_COUNT, self.track_scores, self.track_names,
            )
        except OSError as error:
            self._print(f"progress save failed: {error}")
        self._play_sfx("ok.wav")
        if self.result_transition_target == "select":
            def show_next_select():
                self._reset_selection()
                self.show_select()

            self._start_loading("select", show_next_select)
            return
        if self.result_transition_target == "total_result":
            self._start_loading("total_result", self.show_total_result)
            return
        self._start_loading("ending", self.show_ending)

    def _finish_result_transition(self):
        if self.result_transition_target == "select":
            self._reset_selection()
            self.show_select()
            return
        if self.result_transition_target == "total_result":
            self.show_total_result()
            return
        self._reset_selection()
        self.show_ending()

    def show_total_result(self):
        self.scene = "total_result"
        self.total_result_count_started = False
        self.total_result_count_finished = False
        self.total_result_count_channel = None
        self.total_result_deadline = time.monotonic() + 20.0
        self._build_scene()
        self.scene_started = time.monotonic()
        self.total_result_deadline = self.scene_started + 20.0
        self.root.after(80, lambda: self._play_scene_audio("total_result", "total_result.mp3", loop=True, fade_ms=300))
        self.root.after(180, lambda: self._play_sfx("card_show.wav") if self.scene == "total_result" else None)
        self._print(f"total result visible, total score: {sum(self.track_scores)}")

    def start_total_result_transition(self):
        if self.scene != "total_result" or self.loading_phase is not None:
            return
        if self.total_result_count_channel is not None:
            self.total_result_count_channel.stop()
            self.total_result_count_channel = None
        self._play_sfx("ok.wav")
        self._start_loading("ending", self.show_ending)

    def show_ending(self, fade_in=False):
        if self.scene == "ending":
            return
        self.scene = "ending"
        self.ending_audio_deadline = time.monotonic() + 9.8
        self.ending_audio_started = False
        self.ending_voice_played = False
        self.ending_voice_channel = None
        self.fade_started = None
        self.result_fade_started = None
        self.ending_fade_in_started = None
        self._build_scene()
        self.scene_started = time.monotonic()
        self.ending_audio_deadline = self.scene_started + 9.8
        self.root.after(80, self._play_ending_audio)
        self._print("ending visible")

    def _play_ending_audio(self):
        if not self.running or self.scene != "ending":
            return
        self.ending_audio_started = True
        self.audio.play(os.path.join(self.bgm_root, "game_over.mp3"), fade_ms=300)

    def _track_position(self):
        return self.track_index + 1

    def _track_key(self):
        position = self._track_position()
        if position == EVENT_TRACK_COUNT:
            return "FINAL"
        return str(position)
