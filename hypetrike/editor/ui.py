"""Touch-first track editor (spec §7).

Layout (logical px, height 360):
  top bar      : back, name, laps, theme, undo, check, test, menu
  grid         : terrain row (shape), 4 lane rows (surfaces), ground row
  minimap      : whole track; tap/drag to scroll
  palette      : big tile buttons + zoom
Touch: one finger paints (drag-to-paint), two fingers pan and pinch-zoom.
Mouse: left paints, right-drag or wheel scrolls. Keys: 1-0 tools, arrows
scroll, +/- zoom, Ctrl+Z undo, Ctrl+S save, P playtest, V validate.
"""
import math

import pygame

import config as C
from bike import base_stats
from editor import io as tio
from track.tiles import (FLAT, RAMP_S, RAMP_L, START, GAP, WHOOPS, COOLANT, MUD,
                         DEBRIS, WATER, PAD_S, PAD_L, PAD_BARS, PADS, NONE, DIRT, GRASS, SAND, PROFILES, TILE_NAMES)
from track.validator import validate
from race import fmt_time
from ui import hud, platform_io
from ui.art import THEMES
from ui.menus import button
from ui.scene import Scene, RaceScene

ZOOMS = [18, 28, 42, 60]
GUTTER = 30
TOP_H = 34
TERR_Y, TERR_H = 40, 56
LANE_H = 30
MINI_H = 16

ERASE, HAND, PAD = "erase", "hand", "pad"   # PAD: the pad tool paints the chosen size
PAD_CYCLE = (PAD_S, COOLANT, PAD_L)
PAD_LABEL = {PAD_S: "Pad S", COOLANT: "Pad M", PAD_L: "Pad L"}
TOOLS = [
    ("t", FLAT, "Flat"), ("t", RAMP_S, "Ramp S"), ("t", RAMP_L, "Ramp L"), ("t", GAP, "Gap"),
    ("t", WHOOPS, "Whoops"), ("s", PAD, "Pad"), ("s", MUD, "Mud"), ("s", DEBRIS, "Barrier"),
    ("s", WATER, "Water"),
    ("m", GRASS, "Grass"), ("m", SAND, "Sand"), ("m", DIRT, "Dirt"), ("x", ERASE, "Erase"),
    ("x", HAND, "Move"),
]

MAT_COLORS = {DIRT: (172, 118, 70), GRASS: (96, 170, 70), SAND: (222, 196, 130)}


class EditorScene(Scene):
    def __init__(self, app, track=None):
        super().__init__(app)
        self.track = track or tio.blank_track()
        self.scroll = 0.0
        self.zoom = 2
        self.tool = 1                  # index into TOOLS (Ramp S)
        self.pad_size = COOLANT        # pad tool: size painted (tap the tool again to cycle)
        self.undo_stack = []
        self.dirty = False
        self.saved_name = None
        self.warnings = []             # [(col, reason)]
        self.check_text = ""
        self.check_ok = None
        self.flash = None
        self.popup = None              # None | "menu" | "load" | "confirm_exit" | "code"
        self.entry = None              # TextEntry (desktop)
        self.entry_cb = None
        self.code_text = ""
        self.load_page = 0
        self.t = 0
        self._stroke = None            # pid painting
        self._stroke_snap = None
        self._two = None               # two-finger gesture state
        self._mini_drag = None
        self._rdrag = None
        self._last_cell = None
        self.run_check()

    # ======================================================================
    # geometry
    @property
    def cw(self):
        return ZOOMS[self.zoom]

    def lane_y(self, lane):
        return TERR_Y + TERR_H + lane * LANE_H

    @property
    def mat_y(self):
        return self.lane_y(C.LANES)

    @property
    def mini_y(self):
        return self.mat_y + 33

    @property
    def pal_y(self):
        return self.mini_y + MINI_H + 8

    def visible_cols(self):
        return (self.app.view.width - GUTTER) / self.cw

    def clamp_scroll(self):
        self.scroll = max(0.0, min(self.scroll, max(0.0, self.track.ncols - self.visible_cols() + 1)))

    def cell_at(self, x, y):
        if x < GUTTER or y < TERR_Y or y >= self.mat_y + 16:
            return None
        col = int((x - GUTTER) / self.cw + self.scroll)
        if not (0 <= col < self.track.ncols):
            return None
        if y < TERR_Y + TERR_H:
            row = "t"
        elif y < self.mat_y:
            row = int((y - TERR_Y - TERR_H) // LANE_H)
        else:
            row = "m"
        return col, row

    def tool_rects(self):
        W = self.app.view.width
        n = len(TOOLS) + 2
        bw = min(52, (W - 12) // n)
        x0 = (W - bw * n) // 2
        rs = [pygame.Rect(x0 + i * bw + 1, self.pal_y, bw - 2, C.VIEW_H - self.pal_y - 4) for i in range(n)]
        return rs[: len(TOOLS)], rs[len(TOOLS)], rs[len(TOOLS) + 1]   # tools, zoom-, zoom+

    def top_rects(self):
        W = self.app.view.width
        spec = [("back", 46), ("name", 0), ("laps", 62), ("theme", 70), ("undo", 52),
                ("check", 58), ("test", 62), ("menu", 56)]
        fixed = sum(w for _, w in spec) + 3 * len(spec) + 6
        name_w = max(80, W - fixed)
        rects, x = {}, 4
        for key, w in spec:
            w = w or name_w
            rects[key] = pygame.Rect(x, 4, w, TOP_H - 8)
            x += w + 3
        return rects

    # ======================================================================
    # editing
    def snapshot(self):
        return self.track.to_dict()

    def push_undo(self, snap):
        self.undo_stack.append(snap)
        if len(self.undo_stack) > 60:
            self.undo_stack.pop(0)

    def undo(self):
        if not self.undo_stack:
            self.say("Nothing to undo", (200, 196, 220))
            return
        from track.tiles import Track
        self.track = Track.from_dict(self.undo_stack.pop())
        self.dirty = True
        self.clamp_scroll()
        self.run_check()

    def paint(self, col, row):
        kind, val, _ = TOOLS[self.tool]
        if val == PAD:
            val = self.pad_size
        t = self.track
        if col == 0 and kind in ("t", "s") or (col == 0 and val == ERASE and row == "t"):
            self.say("Section 0 is the start line", (200, 196, 220))
            return False
        changed = False
        if kind == "t":
            if t.terrain[col] != val:
                t.terrain[col] = val
                changed = True
            if val == GAP:
                for l in range(C.LANES):
                    if t.surface[l][col] != NONE:
                        t.surface[l][col] = NONE
                        changed = True
        elif kind == "s":
            if isinstance(row, int) and t.terrain[col] != GAP and t.surface[row][col] != val:
                t.surface[row][col] = val
                changed = True
        elif kind == "m":
            if t.material[col] != val:
                t.material[col] = val
                changed = True
        elif val == ERASE:
            if isinstance(row, int):
                if t.surface[row][col] != NONE:
                    t.surface[row][col] = NONE
                    changed = True
            elif row == "t" and t.terrain[col] != FLAT:
                t.terrain[col] = FLAT
                changed = True
            elif row == "m" and t.material[col] != DIRT:
                t.material[col] = DIRT
                changed = True
        if changed:
            self.dirty = True
            if kind == "t" or val == ERASE:
                t.rebuild()
        return changed

    def resize(self, delta):
        t = self.track
        n = max(tio.MIN_COLS, min(tio.MAX_COLS, t.ncols + delta))
        if n == t.ncols:
            return
        self.push_undo(self.snapshot())
        if n > t.ncols:
            add = n - t.ncols
            t.terrain += [FLAT] * add
            t.material += [DIRT] * add
            for l in range(C.LANES):
                t.surface[l] += [NONE] * add
        else:
            t.terrain = t.terrain[:n]
            t.material = t.material[:n]
            t.surface = [lane[:n] for lane in t.surface]
        t.rebuild()
        self.dirty = True
        self.clamp_scroll()
        self.run_check()
        self.say(f"Track is now {n} sections", C.HUD_FG)

    def run_check(self):
        """Ghost-rider check with the base bike (spec §7.1 validation)."""
        res = validate(self.track, base_stats("dirt"))
        seen = {}
        for reason, col in res["crashes"]:
            seen.setdefault(col, reason)
        self.warnings = sorted(seen.items())
        self.check_ok = res["ok"]
        if res["ok"]:
            self.check_text = f"Ghost rider OK: {fmt_time(res['ticks'])} on the base bike"
        elif self.warnings:
            words = {"pit": "unclearable gap", "debris": "blocked lane", "nose": "bad landing",
                     "loop": "bad landing"}
            parts = [f"#{c} {words.get(r, r)}" for c, r in self.warnings[:3]]
            more = f" +{len(self.warnings) - 3}" if len(self.warnings) > 3 else ""
            self.check_text = "Warning: " + ", ".join(parts) + more
        else:
            self.check_text = "Warning: the ghost rider couldn't finish in time"

    def say(self, text, color=C.HUD_FG, ticks=110):
        self.flash = (text, color, ticks)

    # ======================================================================
    # actions
    def playtest(self):
        sel = self.app.profile.selected
        me = self

        def back(result):
            me.app.set_scene(me)
            if result and result.get("finished"):
                me.say(f"Playtest finished: {fmt_time(result['time'])}", C.GOOD)
        self.app.set_scene(RaceScene(self.app, self.track.copy(), base_stats("dirt"), sel["livery"],
                                     rivals=0, on_done=back, title=f"Playtest: {self.track.name}",
                                     context={"kind": "editor"}))

    def save(self, then=None):
        path = tio.save_track(self.app.profile, self.track)
        self.saved_name = self.track.name
        self.dirty = False
        self.say(f"Saved '{self.track.name}'" + (" (+ JSON file)" if path else ""), C.GOOD)
        if then:
            then()

    def ask_text(self, title, default, cb):
        if platform_io.WEB:
            v = platform_io.web_prompt(title, default)
            if v is not None:
                cb(v)
            return
        self.entry = platform_io.TextEntry(title, default)
        self.entry_cb = cb
        pygame.key.start_text_input()

    def rename(self):
        def done(v):
            self.track.name = tio.clean_name(v)
            self.dirty = True
        self.ask_text("Track name", self.track.name, done)

    def save_as(self):
        def done(v):
            self.track.name = tio.clean_name(v)
            self.save()
        self.ask_text("Save as", self.track.name, done)

    def export_code(self):
        code = tio.encode(self.track)
        self.code_text = code
        copied = platform_io.copy_text(code)
        if platform_io.WEB:
            platform_io.web_prompt("Your track code (copy it and send it to a friend):", code)
        self.popup = "code"
        self.say("Code copied to clipboard" if copied else "Long-press the code to copy it",
                 C.GOOD if copied else C.HUD_FG)

    def import_code(self):
        def load(v):
            try:
                t = tio.decode(v)
            except tio.CodeError as e:
                self.say(f"Import failed: {e}", C.DANGER, 160)
                return
            self.push_undo(self.snapshot())
            self.track = t
            self.scroll = 0
            self.dirty = True
            self.run_check()
            status = "plays fine" if self.check_ok else "has problems (see warning)"
            self.say(f"Imported '{t.name}': {status}", C.GOOD if self.check_ok else C.ACCENT, 180)
        clip = platform_io.paste_text()
        if clip and clip.strip().upper().startswith(tio.PREFIX):
            load(clip)
            return
        self.ask_text("Paste a track code (HT1-...)", "", load)

    def new_track(self):
        self.push_undo(self.snapshot())
        self.track = tio.blank_track()
        self.saved_name = None
        self.dirty = False
        self.scroll = 0
        self.run_check()

    def load_named(self, name):
        try:
            t = tio.load_track(self.app.profile, name)
        except tio.CodeError as e:
            self.say(str(e), C.DANGER)
            return
        self.push_undo(self.snapshot())
        self.track = t
        self.saved_name = name
        self.dirty = False
        self.scroll = 0
        self.popup = None
        self.run_check()
        self.say(f"Loaded '{name}'", C.GOOD)

    def delete_current(self):
        if self.saved_name and self.saved_name in self.app.profile.tracks:
            tio.delete_track(self.app.profile, self.saved_name)
            self.say(f"Deleted '{self.saved_name}'", C.ACCENT)
            self.saved_name = None
            self.dirty = True
        else:
            self.say("This track isn't saved yet", (200, 196, 220))

    def cycle_theme(self):
        names = list(THEMES)
        i = names.index(self.track.theme) if self.track.theme in names else -1
        self.track.theme = names[(i + 1) % len(names)]
        self.dirty = True

    def leave(self):
        from ui.menus import TitleScene
        self.app.set_scene(TitleScene(self.app))

    def menu_items(self):
        return [
            ("New track", self.new_track),
            ("Save", self.save),
            ("Save as / rename", self.save_as),
            ("Load...", lambda: setattr(self, "popup", "load")),
            ("Copy share code", self.export_code),
            ("Import share code", self.import_code),
            ("+10 sections", lambda: self.resize(10)),
            ("-10 sections", lambda: self.resize(-10)),
            ("Delete saved copy", self.delete_current),
        ]

    # ======================================================================
    # input
    def update(self):
        self.t += 1
        if self.flash:
            t, c, n = self.flash
            self.flash = (t, c, n - 1) if n > 1 else None

    def frame(self, inp):
        if self.entry:
            self.entry.feed(inp)
            for x, y in inp.taps():
                pass
            if self.entry.done:
                pygame.key.stop_text_input()
                e, cb = self.entry, self.entry_cb
                self.entry = self.entry_cb = None
                if not e.cancelled and cb:
                    cb(e.value)
            return
        if self.popup:
            self._popup_input(inp)
            return
        self._keys(inp)
        self._pointers(inp)

    def _keys(self, inp):
        mods = pygame.key.get_mods()
        ctrl = mods & (pygame.KMOD_CTRL | pygame.KMOD_META)
        for k in inp.keys_down:
            if ctrl and k == pygame.K_z:
                self.undo()
            elif ctrl and k == pygame.K_s:
                self.save()
            elif k in (pygame.K_ESCAPE, pygame.K_AC_BACK):
                self._back()
            elif k in (pygame.K_LEFT, pygame.K_a):
                self.scroll -= 4
            elif k in (pygame.K_RIGHT, pygame.K_d):
                self.scroll += 4
            elif k in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                self.set_zoom(self.zoom + 1)
            elif k in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self.set_zoom(self.zoom - 1)
            elif k == pygame.K_p or k == pygame.K_RETURN:
                self.playtest()
                return
            elif k == pygame.K_v:
                self.run_check()
            elif pygame.K_1 <= k <= pygame.K_9:
                self.tool = min(len(TOOLS) - 1, k - pygame.K_1)
            elif k == pygame.K_0:
                self.tool = 9
        self.clamp_scroll()

    def set_zoom(self, z, anchor_x=None):
        z = max(0, min(len(ZOOMS) - 1, z))
        if z == self.zoom:
            return
        W = self.app.view.width
        ax = anchor_x if anchor_x is not None else (W + GUTTER) / 2
        col = (ax - GUTTER) / self.cw + self.scroll
        self.zoom = z
        self.scroll = col - (ax - GUTTER) / self.cw
        self.clamp_scroll()

    def _back(self):
        if self.dirty:
            self.popup = "confirm_exit"
        else:
            self.leave()

    def _pointers(self, inp):
        ptrs = self.app.input.pointers
        # --- two-finger pan / pinch ---------------------------------------------------
        fingers = [p for p in ptrs.values() if isinstance(p.pid, tuple)]
        if len(fingers) >= 2:
            a, b = fingers[0], fingers[1]
            cx, dist = (a.x + b.x) / 2, math.hypot(a.x - b.x, a.y - b.y)
            if self._two is None:
                if self._stroke is not None and self._stroke_snap is not None:
                    # second finger landed mid-stroke: cancel that stroke
                    from track.tiles import Track
                    self.track = Track.from_dict(self._stroke_snap)
                self._stroke = None
                self._two = [cx, dist, self.zoom]
            else:
                self.scroll -= (cx - self._two[0]) / self.cw
                self._two[0] = cx
                ratio = dist / max(1.0, self._two[1])
                if ratio > 1.35:
                    self.set_zoom(self.zoom + 1, cx)
                    self._two[1] = dist
                elif ratio < 0.74:
                    self.set_zoom(self.zoom - 1, cx)
                    self._two[1] = dist
            self.clamp_scroll()
            return
        if self._two is not None and not fingers:
            self._two = None
        # --- right-drag / wheel scroll (desktop) ------------------------------------
        for kind, pid, x, y in inp.pointer_events:
            if kind == "wheel":
                if pygame.key.get_mods() & pygame.KMOD_CTRL:
                    self.set_zoom(self.zoom + (1 if x > 0 else -1))
                else:
                    self.scroll -= x * 3 - y * 3
            elif kind == "rdown":
                self._rdrag = x
            elif kind == "rmove" and self._rdrag is not None:
                self.scroll -= (x - self._rdrag) / self.cw
                self._rdrag = x
            elif kind == "rup":
                self._rdrag = None
        # --- single pointer ------------------------------------------------------------------
        tools, zm, zp = self.tool_rects()
        top = self.top_rects()
        W = self.app.view.width
        mini = pygame.Rect(8, self.mini_y, W - 16, MINI_H)
        for kind, pid, x, y in inp.pointer_events:
            if self._two is not None:
                break
            if kind == "down":
                if mini.collidepoint(x, y):
                    self._mini_drag = pid
                    self._mini_scroll(x, mini)
                    continue
                cell = self.cell_at(x, y)
                if cell:
                    if TOOLS[self.tool][1] == HAND:
                        self._stroke = pid
                        self._last_cell = x
                        self._stroke_snap = None
                    else:
                        self._stroke = pid
                        self._stroke_snap = self.snapshot()
                        self._last_cell = cell
                        self.paint(*cell)
            elif kind == "move":
                if pid == self._mini_drag:
                    self._mini_scroll(x, mini)
                elif pid == self._stroke:
                    if TOOLS[self.tool][1] == HAND:
                        self.scroll -= (x - self._last_cell) / self.cw
                        self._last_cell = x
                        self.clamp_scroll()
                    else:
                        cell = self.cell_at(x, y)
                        if cell and cell != self._last_cell:
                            # fill in skipped cells along a fast drag on the same row
                            if self._last_cell and cell[1] == self._last_cell[1]:
                                c0, c1 = self._last_cell[0], cell[0]
                                step = 1 if c1 > c0 else -1
                                for c in range(c0 + step, c1, step):
                                    self.paint(c, cell[1])
                            self.paint(*cell)
                            self._last_cell = cell
            elif kind == "up":
                if pid == self._mini_drag:
                    self._mini_drag = None
                if pid == self._stroke:
                    self._stroke = None
                    if self._stroke_snap is not None and self._stroke_snap != self.snapshot():
                        self.push_undo(self._stroke_snap)
                        self.run_check()
                    self._stroke_snap = None
            elif kind == "tap":
                for i, r in enumerate(tools):
                    if r.collidepoint(x, y):
                        if self.tool == i and TOOLS[i][1] == PAD:     # tap again: next pad size
                            k = PAD_CYCLE.index(self.pad_size)
                            self.pad_size = PAD_CYCLE[(k + 1) % len(PAD_CYCLE)]
                            n = PAD_BARS[self.pad_size]
                            one = self.app.profile.settings.get("throttle_mode", "one") == "one"
                            self.say(f"{TILE_NAMES[self.pad_size]}: "
                                     + (f"+{n} heat bar{'s' if n > 1 else ''}" if one else "cools the engine"),
                                     C.ACCENT)
                        self.tool = i
                if zm.collidepoint(x, y):
                    self.set_zoom(self.zoom - 1)
                if zp.collidepoint(x, y):
                    self.set_zoom(self.zoom + 1)
                for key, r in top.items():
                    if r.collidepoint(x, y):
                        self._top_action(key)
                        return
        self.clamp_scroll()

    def _mini_scroll(self, x, mini):
        k = (x - mini.x) / max(1, mini.w)
        self.scroll = k * self.track.ncols - self.visible_cols() / 2
        self.clamp_scroll()

    def _top_action(self, key):
        if key == "back":
            self._back()
        elif key == "name":
            self.rename()
        elif key == "laps":
            self.track.laps = self.track.laps % 5 + 1
            self.dirty = True
        elif key == "theme":
            self.cycle_theme()
        elif key == "undo":
            self.undo()
        elif key == "check":
            self.run_check()
            self.say(self.check_text, C.GOOD if self.check_ok else C.ACCENT, 160)
        elif key == "test":
            self.playtest()
        elif key == "menu":
            self.popup = "menu"

    # -- popups ------------------------------------------------------------------------------
    def _popup_rects(self, n, w=230, h=26):
        W = self.app.view.width
        top = max(40, C.VIEW_H // 2 - (n * (h + 4)) // 2)
        return [pygame.Rect(W // 2 - w // 2, top + i * (h + 4), w, h) for i in range(n)]

    def _popup_input(self, inp):
        esc = any(k in (pygame.K_ESCAPE, pygame.K_AC_BACK) for k in inp.keys_down)
        taps = inp.taps()
        if self.popup == "menu":
            items = self.menu_items() + [("Close", None)]
            rects = self._popup_rects(len(items))
            if esc:
                self.popup = None
            for x, y in taps:
                hit = False
                for r, (label, fn) in zip(rects, items):
                    if r.collidepoint(x, y):
                        hit = True
                        self.popup = None
                        if fn:
                            fn()
                if not hit:
                    self.popup = None
        elif self.popup == "load":
            names = tio.list_tracks(self.app.profile)
            per = 7
            page = names[self.load_page * per:(self.load_page + 1) * per]
            rows = self._popup_rects(len(page) + 1, w=280)
            if esc:
                self.popup = None
            for x, y in taps:
                for r, name in zip(rows, page):
                    if r.collidepoint(x, y):
                        self.load_named(name)
                        return
                nav = rows[-1]
                if nav.collidepoint(x, y):
                    if x < nav.centerx - 40 and self.load_page > 0:
                        self.load_page -= 1
                    elif x > nav.centerx + 40 and (self.load_page + 1) * per < len(names):
                        self.load_page += 1
                    else:
                        self.popup = None
        elif self.popup == "confirm_exit":
            rects = self._popup_rects(3)
            acts = [lambda: self.save(then=self.leave), self.leave, lambda: None]
            if esc:
                self.popup = None
            for x, y in taps:
                for r, fn in zip(rects, acts):
                    if r.collidepoint(x, y):
                        self.popup = None
                        fn()
                        return
        elif self.popup == "code":
            if esc or taps:
                self.popup = None

    # ======================================================================
    # drawing
    def draw(self, surf):
        W = self.app.view.width
        surf.fill((28, 26, 40))
        self._draw_grid(surf, W)
        self._draw_minimap(surf, W)
        self._draw_palette(surf)
        self._draw_top(surf)
        if self.check_text:
            col = C.GOOD if self.check_ok else C.ACCENT
            hud.text(surf, self.check_text, (GUTTER, self.mat_y + 17), 15, col)
        if self.flash:
            hud.panel(surf, (W // 2 - 220, TERR_Y + 8, 440, 24), 220)
            hud.text(surf, self.flash[0], (W // 2, TERR_Y + 20), 20, self.flash[1], anchor="center")
        if self.popup:
            self._draw_popup(surf, W)
        if self.entry:
            self.entry.draw(surf, hud, W)

    def _draw_top(self, surf):
        r = self.top_rects()
        t = self.track
        name = t.name + ("*" if self.dirty else "")
        button(surf, r["back"], "<", size=22)
        button(surf, r["name"], name, size=20)
        button(surf, r["laps"], f"LAPS {t.laps}", size=17)
        button(surf, r["theme"], THEMES[t.theme]["name"], size=17)
        button(surf, r["undo"], "UNDO", size=17, enabled=bool(self.undo_stack))
        button(surf, r["check"], "CHECK", size=17)
        pygame.draw.rect(surf, (40, 120, 60), r["test"], border_radius=7)
        hud.text(surf, "> TEST", r["test"].center, 18, anchor="center")
        button(surf, r["menu"], "MENU", size=17)

    def _draw_grid(self, surf, W):
        cw = self.cw
        t = self.track
        first = int(self.scroll)
        off = (self.scroll - first) * cw
        ncols_vis = int(self.visible_cols()) + 2
        warn_cols = {c for c, _ in self.warnings}
        # row labels
        hud.text(surf, "TRK", (2, TERR_Y + TERR_H // 2 - 6), 14, (200, 196, 220))
        for l in range(C.LANES):
            hud.text(surf, f"L{l + 1}", (6, self.lane_y(l) + 9), 16, (200, 196, 220))
        hud.text(surf, "GND", (2, self.mat_y + 2), 13, (200, 196, 220))
        clip = surf.get_clip()
        surf.set_clip(pygame.Rect(GUTTER, TERR_Y, W - GUTTER, self.mat_y + 16 - TERR_Y))
        for i in range(ncols_vis):
            col = first + i
            if col >= t.ncols:
                break
            x = GUTTER + i * cw - off
            mat = MAT_COLORS[t.material[col]]
            # terrain row: shape profile scaled into the row
            pygame.draw.rect(surf, (60, 90, 130), (x, TERR_Y, cw, TERR_H))
            base_y = TERR_Y + TERR_H - 14
            prof = PROFILES[t.terrain[col]]
            pts = [(x + px * cw / C.TILE_W, base_y - max(-12, h * 0.55)) for px, h in prof]
            poly = [(x, TERR_Y + TERR_H)] + pts + [(x + cw, TERR_Y + TERR_H)]
            pygame.draw.polygon(surf, (20, 16, 24) if t.terrain[col] == GAP else mat, poly)
            if t.terrain[col] == START:
                for j in range(0, TERR_H, 6):
                    surf.fill((250, 250, 250) if (j // 6) % 2 else (24, 24, 30), (x + cw // 2 - 3, TERR_Y + j, 6, 6))
            # lane cells
            for l in range(C.LANES):
                y = self.lane_y(l)
                if t.terrain[col] == GAP:
                    c = (20, 16, 24)
                else:
                    c = tuple(int(v * (0.92 if (l + col) % 2 else 1.0)) for v in mat)
                pygame.draw.rect(surf, c, (x, y, cw, LANE_H))
                self._draw_surface_icon(surf, t.surface[l][col], x, y, cw)
            pygame.draw.rect(surf, mat, (x, self.mat_y, cw, 14))
            # grid lines + numbers
            pygame.draw.line(surf, (40, 36, 52), (x, TERR_Y), (x, self.mat_y + 14))
            if col % 5 == 0 and cw >= 18:
                hud.text(surf, str(col), (x + 2, TERR_Y + 2), 14, (230, 230, 240))
            if col in warn_cols:
                pygame.draw.rect(surf, C.DANGER, (x + 1, TERR_Y + 1, cw - 2, self.mat_y + 13 - TERR_Y), 2)
                hud.text(surf, "!", (x + cw // 2, TERR_Y + 26), 24, C.DANGER, anchor="center")
        for l in range(C.LANES + 1):
            pygame.draw.line(surf, (40, 36, 52), (GUTTER, self.lane_y(l)), (W, self.lane_y(l)))
        surf.set_clip(clip)
        # end-of-track marker
        end_x = GUTTER + (t.ncols - self.scroll) * cw
        if end_x < W:
            hud.text(surf, "END", (end_x + 6, self.lane_y(1)), 18, (170, 166, 190))

    def _draw_surface_icon(self, surf, s, x, y, cw):
        if s == NONE:
            return
        cx, cy = x + cw // 2, y + LANE_H // 2
        r = max(5, min(12, cw // 3))
        if s == MUD:
            pygame.draw.ellipse(surf, (88, 58, 40), (cx - r - 3, cy - r // 2 - 1, 2 * r + 6, r + 2))
        elif s in PAD_BARS:
            bars = PAD_BARS[s]
            heat = self.app.profile.settings.get("throttle_mode", "one") == "one"
            base, chev = ((150, 46, 20), (255, 200, 60)) if heat else ((30, 90, 140), (90, 220, 255))
            w = 2 * r + 4
            pygame.draw.rect(surf, base, (cx - w // 2, cy - r + 2, w, 2 * r - 4), border_radius=3)
            step = w / (bars + 1)
            for i in range(bars):
                x = cx - w // 2 + step * (i + 1)
                pygame.draw.polygon(surf, chev, [(x - 3, cy - 4), (x + 3, cy), (x - 3, cy + 4)])
        elif s == WATER:
            lava = self.track.theme == C.LAVA_THEME
            pygame.draw.ellipse(surf, (200, 60, 20) if lava else (50, 120, 200),
                                (cx - r - 3, cy - r // 2 - 1, 2 * r + 6, r + 2))
            pygame.draw.ellipse(surf, (255, 190, 60) if lava else (150, 210, 250),
                                (cx - r + 1, cy - r // 2 + 1, r, max(2, r // 3)))
        elif s == DEBRIS:
            pygame.draw.rect(surf, (240, 240, 240), (cx - r, cy - r + 2, 2 * r, 2 * r - 4))
            for i in range(-r, r, 5):
                pygame.draw.line(surf, (232, 59, 59), (cx + i, cy + r - 3), (cx + i + 4, cy - r + 3), 2)

    def _draw_minimap(self, surf, W):
        t = self.track
        mini = pygame.Rect(8, self.mini_y, W - 16, MINI_H)
        pygame.draw.rect(surf, (16, 14, 24), mini)
        k = mini.w / t.ncols
        for c, terr in enumerate(t.terrain):
            col = {GAP: (20, 16, 24), RAMP_S: (230, 170, 90), RAMP_L: (255, 200, 110),
                   WHOOPS: (200, 150, 90), START: (250, 250, 250)}.get(terr, MAT_COLORS[t.material[c]])
            h = {RAMP_S: 9, RAMP_L: 14, WHOOPS: 6, GAP: 0}.get(terr, 4)
            surf.fill(col, (mini.x + c * k, mini.bottom - max(2, h), max(1, math.ceil(k)), max(2, h)))
            if any(t.surface[l][c] == DEBRIS for l in range(C.LANES)):
                surf.fill(C.DANGER, (mini.x + c * k, mini.y, max(1, math.ceil(k)), 3))
            if any(t.surface[l][c] in PADS for l in range(C.LANES)):
                surf.fill(C.COOL, (mini.x + c * k, mini.y + 3, max(1, math.ceil(k)), 2))
        for c, _ in self.warnings:
            pygame.draw.rect(surf, C.DANGER, (mini.x + c * k - 1, mini.y, max(3, k + 2), MINI_H), 1)
        vx = mini.x + self.scroll * k
        vw = self.visible_cols() * k
        pygame.draw.rect(surf, C.ACCENT, (vx, mini.y - 1, min(vw, mini.right - vx), MINI_H + 2), 2)

    def _draw_palette(self, surf):
        tools, zm, zp = self.tool_rects()
        for i, (r, (kind, val, label)) in enumerate(zip(tools, TOOLS)):
            on = i == self.tool
            pygame.draw.rect(surf, (78, 70, 110) if on else (46, 42, 66), r, border_radius=6)
            if on:
                pygame.draw.rect(surf, C.ACCENT, r, 2, border_radius=6)
            icon = pygame.Rect(r.x + 4, r.y + 4, r.w - 8, r.h - 22)
            if val == PAD:
                val, label = self.pad_size, PAD_LABEL[self.pad_size]
            self._tool_icon(surf, kind, val, icon)
            hud.text(surf, label, (r.centerx, r.bottom - 9), 14, anchor="center")
        button(surf, zm, "-", size=28)
        button(surf, zp, "+", size=28)
        hud.text(surf, "zoom", ((zm.x + zp.right) // 2, zm.bottom - 9), 13, (200, 196, 220), anchor="center")

    def _tool_icon(self, surf, kind, val, r):
        if kind == "t" and val == GAP:
            pygame.draw.rect(surf, (60, 90, 130), r)
            pygame.draw.rect(surf, MAT_COLORS[DIRT], (r.x, r.bottom - 10, r.w, 10))
            pygame.draw.rect(surf, (20, 16, 24), (r.x + 6, r.bottom - 10, r.w - 12, 10))
            pygame.draw.rect(surf, (60, 120, 170), (r.x + 6, r.bottom - 3, r.w - 12, 3))
        elif kind == "t":
            pygame.draw.rect(surf, (60, 90, 130), r)
            prof = PROFILES[val]
            pts = [(r.x + px * r.w / C.TILE_W, r.bottom - 6 - max(-6, h * 0.45)) for px, h in prof]
            pygame.draw.polygon(surf, (20, 16, 24) if val == GAP else MAT_COLORS[DIRT],
                                [(r.x, r.bottom)] + pts + [(r.right, r.bottom)])
        elif kind == "s":
            pygame.draw.rect(surf, MAT_COLORS[DIRT], r)
            self._draw_surface_icon(surf, val, r.x + (r.w - 30) // 2, r.y + (r.h - LANE_H) // 2, 30)
        elif kind == "m":
            pygame.draw.rect(surf, MAT_COLORS[val], r)
        elif val == ERASE:
            pygame.draw.rect(surf, (90, 86, 110), r)
            pygame.draw.line(surf, C.DANGER, (r.x + 6, r.y + 4), (r.right - 6, r.bottom - 4), 3)
            pygame.draw.line(surf, C.DANGER, (r.right - 6, r.y + 4), (r.x + 6, r.bottom - 4), 3)
        else:
            pygame.draw.rect(surf, (90, 86, 110), r)
            cx, cy = r.center
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                pygame.draw.line(surf, C.HUD_FG, (cx, cy), (cx + dx * 9, cy + dy * 9), 2)

    def _draw_popup(self, surf, W):
        shade = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 140))
        hud.flush_queued(surf)             # text under the shade is dimmed with it
        surf.blit(shade, (0, 0))
        if self.popup == "menu":
            items = self.menu_items() + [("Close", None)]
            for r, (label, _) in zip(self._popup_rects(len(items)), items):
                button(surf, r, label, size=19)
        elif self.popup == "load":
            names = tio.list_tracks(self.app.profile)
            per = 7
            page = names[self.load_page * per:(self.load_page + 1) * per]
            rows = self._popup_rects(len(page) + 1, w=280)
            hud.text(surf, "LOAD TRACK", (W // 2, rows[0].y - 18), 24, C.ACCENT, anchor="center")
            if not names:
                hud.text(surf, "No saved tracks yet", (W // 2, rows[0].y + 30), 20, anchor="center")
            for r, name in zip(rows, page):
                button(surf, r, name, size=19)
            nav = rows[-1]
            pages = max(1, (len(names) + per - 1) // per)
            button(surf, nav, f"<   page {self.load_page + 1}/{pages}   close   >", size=17)
        elif self.popup == "confirm_exit":
            rects = self._popup_rects(3)
            hud.text(surf, "Unsaved changes", (W // 2, rects[0].y - 18), 24, C.ACCENT, anchor="center")
            for r, label in zip(rects, ("Save and exit", "Discard changes", "Keep editing")):
                button(surf, r, label, size=19)
        elif self.popup == "code":
            hud.panel(surf, (20, 90, W - 40, 170), 240)
            hud.text(surf, "SHARE CODE", (W // 2, 106), 26, C.ACCENT, anchor="center")
            f = hud.font(16)
            line, y = "", 126
            for ch in self.code_text:
                if f.size(line + ch)[0] > W - 70:
                    hud.text(surf, line, (34, y), 16)
                    y += 14
                    line = ""
                line += ch
            hud.text(surf, line, (34, y), 16)
            hud.text(surf, "Friends use MENU > Import share code. Tap to close.", (W // 2, 248), 16,
                     (200, 196, 220), anchor="center")
