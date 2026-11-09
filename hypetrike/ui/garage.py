"""Garage: meta-shop + loadout (vehicle, livery, starting kit, theme rotation)."""
import pygame

import config as C
from bike import base_stats
from meta import shop
from track.tiles import DIRT, GRASS, SAND
from ui import hud, art
from ui.menus import BackdropScene, button
from ui.input import TAP_SLOP  # noqa: F401

TABS = [("vehicle", "VEHICLES"), ("livery", "PAINT"), ("kit", "START KIT"), ("theme", "THEMES")]


class GarageScene(BackdropScene):
    def __init__(self, app, back=None):
        super().__init__(app)
        self.back = back
        self.tab = 0
        self.sel = 0
        self.flash = None   # (text, color, ticks)
        self.sprites = art.SpriteCache()
        self._focus_selected()

    # -- data ----------------------------------------------------------------
    @property
    def kind(self):
        return TABS[self.tab][0]

    def items(self):
        return shop.catalogue(self.kind)

    def _focus_selected(self):
        for i, it in enumerate(self.items()):
            if shop.is_selected(self.app.profile, self.kind, it["id"]) and self.kind != "theme":
                self.sel = i
                return
        self.sel = 0

    def owned(self, item_id):
        return item_id in self.app.profile.data[shop.KIND_KEY[self.kind]]

    # -- layout --------------------------------------------------------------
    def _tab_rects(self):
        W = self.app.view.width
        tw = 110
        x0 = W // 2 - (tw * len(TABS) + 6 * (len(TABS) - 1)) // 2
        return [pygame.Rect(x0 + i * (tw + 6), 44, tw, 26) for i in range(len(TABS))]

    def _item_rects(self):
        return [pygame.Rect(14, 80 + i * 37, 210, 33) for i in range(len(self.items()))]

    def _action_rect(self):
        W = self.app.view.width
        return pygame.Rect(W - 190, C.VIEW_H - 46, 176, 36)

    def _back_rect(self):
        return pygame.Rect(10, 8, 70, 26)

    # -- input ----------------------------------------------------------------------
    def frame(self, inp):
        n = len(self.items())
        for k in inp.keys_down:
            if k in (pygame.K_ESCAPE, pygame.K_AC_BACK):
                return self._leave()
            if k in (pygame.K_TAB, pygame.K_RIGHT, pygame.K_d):
                self._set_tab((self.tab + 1) % len(TABS))
            elif k in (pygame.K_LEFT, pygame.K_a):
                self._set_tab((self.tab - 1) % len(TABS))
            elif k in (pygame.K_UP, pygame.K_w):
                self.sel = (self.sel - 1) % n
            elif k in (pygame.K_DOWN, pygame.K_s):
                self.sel = (self.sel + 1) % n
            elif k in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_z):
                self.act()
        for x, y in inp.taps():
            if self._back_rect().collidepoint(x, y):
                return self._leave()
            for i, r in enumerate(self._tab_rects()):
                if r.collidepoint(x, y):
                    self._set_tab(i)
            for i, r in enumerate(self._item_rects()):
                if r.collidepoint(x, y):
                    if self.sel == i and self.owned(self.items()[i]["id"]) and self.kind != "theme":
                        self.act()          # second tap on an owned item equips it
                    self.sel = i
            if self._action_rect().collidepoint(x, y):
                self.act()

    def _set_tab(self, i):
        self.tab = i
        self._focus_selected()

    def _leave(self):
        if self.back:
            self.back()
        else:
            from ui.menus import TitleScene
            self.app.set_scene(TitleScene(self.app))

    def act(self):
        p = self.app.profile
        it = self.items()[self.sel]
        if not self.owned(it["id"]):
            if shop.buy(p, self.kind, it["id"]):
                self.app.audio.ui("buy")
                self.flash = (f"Unlocked {it['name']}!", C.GOOD, 70)
                if self.kind != "theme":
                    shop.select(p, self.kind, it["id"])
                else:
                    shop.select(p, self.kind, it["id"]) if not shop.is_selected(p, "theme", it["id"]) else None
            else:
                self.app.audio.ui("deny")
                self.flash = (f"Need {it['price'] - p.currency} more coins", C.DANGER, 60)
            return
        shop.select(p, self.kind, it["id"])
        self.app.audio.ui("click")

    def update(self):
        super().update()
        if self.flash:
            t, c, n = self.flash
            self.flash = (t, c, n - 1) if n > 1 else None

    # -- drawing ----------------------------------------------------------------------
    def draw(self, surf):
        W = self.app.view.width
        p = self.app.profile
        self.draw_bg(surf)
        button(surf, self._back_rect(), "< BACK", size=18)
        hud.text(surf, "GARAGE", (W // 2, 22), 36, C.ACCENT, anchor="center")
        hud.text(surf, f"{p.currency} coins", (W - 12, 12), 24, C.ACCENT, anchor="topright")
        for i, (r, (_, label)) in enumerate(zip(self._tab_rects(), TABS)):
            button(surf, r, label, on=i == self.tab, size=18)
        items = self.items()
        for i, (r, it) in enumerate(zip(self._item_rects(), items)):
            owned = self.owned(it["id"])
            selected = shop.is_selected(p, self.kind, it["id"])
            pygame.draw.rect(surf, (78, 70, 110) if i == self.sel else (46, 42, 66), r, border_radius=6)
            if i == self.sel:
                pygame.draw.rect(surf, C.ACCENT, r, 2, border_radius=6)
            hud.text(surf, it["name"], (r.x + 10, r.centery), 22, C.HUD_FG if owned else (190, 186, 210),
                     anchor="midleft")
            if selected and (owned or it["price"] == 0):
                tag, col = ("ON" if self.kind == "theme" else "EQUIPPED"), C.GOOD
            elif owned:
                tag, col = "OWNED", (200, 196, 220)
            else:
                tag, col = f"{it['price']}c", C.ACCENT if p.currency >= it["price"] else (170, 120, 120)
            hud.text(surf, tag, (r.right - 8, r.centery), 16, col, anchor="midright")
        self._draw_detail(surf, items[self.sel], W)
        if self.flash:
            hud.text(surf, self.flash[0], (W // 2 + 110, C.VIEW_H - 64), 22, self.flash[1], anchor="center")

    def _draw_detail(self, surf, it, W):
        p = self.app.profile
        x0 = 240
        panel_w = W - x0 - 12
        hud.panel(surf, (x0, 80, panel_w, 214), 190)
        hud.text(surf, it["name"], (x0 + 12, 88), 28, C.ACCENT)
        _wrap(surf, it["desc"], x0 + 12, 114, panel_w - 24, 18)
        sel = p.selected
        if self.kind in ("vehicle", "livery"):
            vehicle = it["id"] if self.kind == "vehicle" else sel["vehicle"]
            livery = it["id"] if self.kind == "livery" else sel["livery"]
            frame = (self.t // 6) % 2
            img = self.sprites.vehicle(vehicle, livery, frame)
            big = pygame.transform.scale(img, (img.get_width() * 3, img.get_height() * 3))
            surf.blit(big, (x0 + 4, 140))
            if self.kind == "vehicle":
                self._stat_bars(surf, base_stats(vehicle), x0 + 170, 146, panel_w - 182)
        elif self.kind == "kit":
            hud.text(surf, "Pick one starting upgrade. Tap again to unequip.", (x0 + 12, 160), 18,
                     (200, 196, 220))
            cur = sel.get("start_upgrade")
            from run.upgrades import UPGRADES
            hud.text(surf, f"Equipped: {UPGRADES[cur].name if cur else 'none'}", (x0 + 12, 186), 22)
        else:
            from ui.render import WorldRenderer
            if getattr(self, "_theme_prev", (None,))[0] != it["id"]:
                rd = WorldRenderer(320, it["id"])
                s = pygame.Surface((320, 360))
                rd.draw_backdrop(s, 200)
                rd.draw_track(s, self._bg_track, 200)
                self._theme_prev = (it["id"], pygame.transform.smoothscale(s.subsurface((0, 60, 320, 280)), (176, 154)))
            surf.blit(self._theme_prev[1], (x0 + 12, 134))
            hud.text(surf, "Themes marked ON rotate", (x0 + 196, 150), 16, (200, 196, 220))
            hud.text(surf, "through your heats.", (x0 + 196, 166), 16, (200, 196, 220))
        owned = self.owned(it["id"])
        if not owned:
            label = f"BUY  {it['price']}c"
        elif self.kind == "theme":
            label = "TURN OFF" if shop.is_selected(p, "theme", it["id"]) else "TURN ON"
        elif self.kind == "kit":
            label = "UNEQUIP" if sel.get("start_upgrade") == it["id"] else "EQUIP"
        else:
            label = "EQUIPPED" if shop.is_selected(p, self.kind, it["id"]) else "EQUIP"
        button(surf, self._action_rect(), label, on=True, size=22,
               enabled=owned or p.currency >= it["price"])

    def _stat_bars(self, surf, s, x, y, w):
        rows = [
            ("Top speed", (s.max_speed_a - 38) / 14),
            ("Accel", (1 / s.accel_interval - 0.18) / 0.14),
            ("Cool engine", (0.10 - s.heat_b) / 0.05),
            ("Air control", (s.pitch_rate - 1.3) / 1.6),
            ("Landing", (s.land_tolerance - 8) / 14),
            ("Dirt grip", (s.grip[DIRT] - 0.6) / 0.4),
            ("Grass grip", (s.grip[GRASS] - 0.6) / 0.4),
            ("Sand grip", (s.grip[SAND] - 0.6) / 0.4),
        ]
        for i, (label, k) in enumerate(rows):
            yy = y + i * 17
            hud.text(surf, label, (x, yy), 16)
            bw = max(40, w - 90)
            surf.fill((40, 36, 52), (x + 86, yy + 3, bw, 8))
            k = max(0.05, min(1.0, k))
            col = C.GOOD if k > 0.66 else (C.ACCENT if k > 0.33 else C.DANGER)
            surf.fill(col, (x + 86, yy + 3, int(bw * k), 8))


def _wrap(surf, text, x, y, w, size):
    f = hud.font(size)
    line = ""
    for word in text.split():
        t = (line + " " + word).strip()
        if f.size(t)[0] > w and line:
            hud.text(surf, line, (x, y), size)
            y += size - 3
            line = word
        else:
            line = t
    if line:
        hud.text(surf, line, (x, y), size)
