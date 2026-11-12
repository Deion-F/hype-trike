"""Replay browser: the live (not yet archived) race recordings, newest first.
Pick one to watch it re-simulated from its recorded inputs (replay.py)."""
import pygame

import config as C
import replay as rp
from race import fmt_time
from ui import hud
from ui.menus import BackdropScene, button

PAGE = 8


def describe(d):
    """(left, right) one-line summary of a recording."""
    ctx = d.get("context", {})
    kind = ctx.get("kind", "race")
    if kind == "run":
        what = f"Run heat {ctx.get('heat', 0) + 1}"
    else:
        what = {"quick": "Quick race", "trial": "Time trial", "practice": "Practice",
                "exhibition": "Exhibition", "editor": "Playtest"}.get(kind, kind.title())
    s = d.get("summary", {})
    when = d.get("created", "")[5:16].replace("T", " ")
    left = f"{when}  {what}: {d['track'].get('n', '?')}"
    if s.get("forfeit"):
        res = "quit"
    elif not s.get("finished"):
        res = "DNF"
    else:
        res = fmt_time(s.get("time", 0))
        if s.get("field", 1) > 1:
            res = f"P{s.get('position')}/{s.get('field')}  " + res
    crashes = sum((s.get("crashes") or {}).values()) + s.get("explodes", 0)
    right = res + (f"  {crashes} crash" + ("es" if crashes != 1 else "") if crashes else "")
    return left, right


class ReplayListScene(BackdropScene):
    def __init__(self, app):
        super().__init__(app)
        self.items = rp.list_recordings()
        self.sel = 0
        self.top = 0

    def _rows(self):
        W = self.app.view.width
        return [pygame.Rect(16, 70 + i * 30, W - 32, 27) for i in range(PAGE)]

    def _back_rect(self):
        return pygame.Rect(self.app.view.width // 2 - 70, C.VIEW_H - 40, 140, 30)

    def back(self):
        from ui.menus import TitleScene
        self.app.set_scene(TitleScene(self.app))

    def watch(self, i):
        from ui.scene import RaceScene
        data = self.items[i][1]
        try:
            track, stats, kw, _, livery, _ = rp.rebuild(data)
        except (KeyError, ValueError, TypeError):
            return
        me = self
        self.app.set_scene(RaceScene(self.app, track, stats, livery, title=f"Replay: {track.name}",
                                     replay=data, on_done=lambda _r: me.app.set_scene(me), **kw))

    def frame(self, inp):
        n = len(self.items)
        for k in inp.keys_down:
            if k in (pygame.K_ESCAPE, pygame.K_AC_BACK):
                self.back()
                return
            if n and k in (pygame.K_UP, pygame.K_w):
                self.sel = (self.sel - 1) % n
            elif n and k in (pygame.K_DOWN, pygame.K_s):
                self.sel = (self.sel + 1) % n
            elif n and k in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_z):
                self.watch(self.sel)
                return
        for kind, _, x, y in inp.pointer_events:
            if kind == "wheel" and n:
                self.sel = max(0, min(n - 1, self.sel - int(x)))
        self.top = max(0, min(self.sel, max(0, n - PAGE), max(self.top, self.sel - PAGE + 1)))
        if self.sel < self.top:
            self.top = self.sel
        for x, y in inp.taps():
            if self._back_rect().collidepoint(x, y):
                self.back()
                return
            for i, r in enumerate(self._rows()):
                j = self.top + i
                if j < n and r.collidepoint(x, y):
                    if self.sel == j:
                        self.watch(j)
                        return
                    self.sel = j

    def draw(self, surf):
        W = self.app.view.width
        self.draw_bg(surf)
        hud.text(surf, "REPLAYS", (W // 2, 26), 36, C.ACCENT, anchor="center")
        hud.text(surf, f"{len(self.items)} recorded races not yet used for tuning"
                 if self.items else "No recordings yet - race with recordings on (Settings)",
                 (W // 2, 52), 16, (200, 196, 220), anchor="center")
        for i, r in enumerate(self._rows()):
            j = self.top + i
            if j >= len(self.items):
                break
            on = j == self.sel
            pygame.draw.rect(surf, (78, 70, 110) if on else (46, 42, 66), r, border_radius=6)
            if on:
                pygame.draw.rect(surf, C.ACCENT, r, 2, border_radius=6)
            left, right = describe(self.items[j][1])
            hud.text(surf, right, (r.right - 10, r.centery), 17, C.ACCENT, anchor="midright")
            room = r.w - 30 - hud.font(17).size(right)[0]
            while left and hud.font(17).size(left)[0] > room:
                left = left[:-1]
            hud.text(surf, left, (r.x + 10, r.centery), 17, anchor="midleft")
        if len(self.items) > PAGE:
            hud.text(surf, f"{self.sel + 1}/{len(self.items)}", (W - 16, 52), 14, (170, 166, 190),
                     anchor="midright")
        button(surf, self._back_rect(), "BACK", size=20)
