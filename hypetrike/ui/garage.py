"""Garage: meta-shop + loadout (vehicle, livery) and the levelled Starter Kit. Biomes aren't
bought: a run tours them all, easiest to hardest (run.manager.BIOMES)."""
import pygame

import config as C
from bike import base_stats
from meta import shop
from bike import VEHICLES
from meta.bike_tune import TUNE, price as tune_price
from meta.kit import KIT, MAX_LEVEL
from ui.art import livery_key
from run.upgrades import CATEGORY_COLORS
from track.tiles import DIRT, GRASS, SAND
from ui import hud, art
from ui.menus import BackdropScene, button
from ui.input import TAP_SLOP  # noqa: F401

TABS = [("vehicle", "VEHICLES"), ("tune", "TUNE"), ("livery", "BIKE"), ("rider", "RIDER"),
        ("boost", "BOOST"), ("kit", "STARTER KIT")]
LEVELLED = ("kit", "tune")      # tabs of items bought level by level
TUNE_CAT = {"top_speed": "Engine", "accel": "Engine", "cooling": "Heat", "air": "Air", "landing": "Air"}


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
        if self.kind == "tune":
            return [{"id": t.id, "name": t.name, "category": TUNE_CAT[t.id]} for t in TUNE.values()]
        return shop.catalogue(self.kind, self.app.profile.settings.get("throttle_mode", "one"))

    # levelled items (Starter Kit, bike tuning)
    def _level(self, item_id):
        if self.kind == "tune":
            return self.app.profile.bike_levels().get(item_id, 0)
        return shop.kit_level(self.app.profile, item_id)

    def _price(self, item_id):
        if self.kind == "tune":
            return tune_price(self.app.profile.selected["vehicle"], item_id, self._level(item_id))
        return KIT[item_id].price(self._level(item_id))

    def _describe(self, item_id, level):
        return (TUNE if self.kind == "tune" else KIT)[item_id].describe(level)

    def _focus_selected(self):
        if self.kind in LEVELLED:
            self.sel = min(getattr(self, "sel", 0), len(self.items()) - 1)
            return
        for i, it in enumerate(self.items()):
            if shop.is_selected(self.app.profile, self.kind, it["id"]):
                self.sel = i
                return
        self.sel = 0

    def owned(self, item_id):
        if self.kind in LEVELLED:
            return self._level(item_id) > 0
        return item_id in self.app.profile.data[shop.KIND_KEY[self.kind]]

    # -- layout --------------------------------------------------------------
    def _tab_rects(self):
        W = self.app.view.width
        tw = 98
        x0 = W // 2 - (tw * len(TABS) + 6 * (len(TABS) - 1)) // 2
        return [pygame.Rect(x0 + i * (tw + 6), 44, tw, 26) for i in range(len(TABS))]

    def _item_rects(self):
        step, h = (32, 29) if self.kind in LEVELLED else (37, 33)
        return [pygame.Rect(14, 80 + i * step, 210, h) for i in range(len(self.items()))]

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
                    if self.sel == i and self.owned(self.items()[i]["id"]) and self.kind not in LEVELLED:
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
        if self.kind in LEVELLED:
            level = self._level(it["id"])
            price = self._price(it["id"])
            if self.kind == "tune":
                bought = price is not None and shop.buy_tune_level(p, p.selected["vehicle"], it["id"])
            else:
                bought = price is not None and shop.buy_kit_level(p, it["id"])
            if price is None:
                self.app.audio.ui("deny")
                self.flash = ("Already maxed", (200, 196, 220), 50)
            elif bought:
                self.app.audio.ui("buy")
                self.flash = (f"{it['name']} level {level + 1}!", C.GOOD, 70)
            else:
                self.app.audio.ui("deny")
                self.flash = (f"Need {price - p.currency} more coins", C.DANGER, 60)
            return
        if not self.owned(it["id"]):
            if shop.buy(p, self.kind, it["id"]):
                self.app.audio.ui("buy")
                self.flash = (f"Unlocked {it['name']}!", C.GOOD, 70)
                shop.select(p, self.kind, it["id"])
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
            if self.kind in LEVELLED:
                self._draw_kit_row(surf, r, it, i == self.sel)
                continue
            owned = self.owned(it["id"])
            selected = shop.is_selected(p, self.kind, it["id"])
            pygame.draw.rect(surf, (78, 70, 110) if i == self.sel else (46, 42, 66), r, border_radius=6)
            if i == self.sel:
                pygame.draw.rect(surf, C.ACCENT, r, 2, border_radius=6)
            hud.text(surf, it["name"], (r.x + 10, r.centery), 22, C.HUD_FG if owned else (190, 186, 210),
                     anchor="midleft")
            if selected and (owned or it["price"] == 0):
                tag, col = "EQUIPPED", C.GOOD
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
        if self.kind not in LEVELLED:
            _wrap(surf, it["desc"], x0 + 12, 114, panel_w - 24, 18)
        sel = p.selected
        if self.kind in ("vehicle", "livery", "rider", "boost"):
            vehicle = it["id"] if self.kind == "vehicle" else sel["vehicle"]
            bike = it["id"] if self.kind == "livery" else sel["livery"]
            rider = it["id"] if self.kind == "rider" else sel.get("rider", bike)
            livery = livery_key(bike, rider)
            frame = (self.t // 6) % 2
            img = self.sprites.vehicle(vehicle, livery, frame)
            big = pygame.transform.scale(img, (img.get_width() * 3, img.get_height() * 3))
            if self.kind == "boost":
                self._draw_boost_preview(surf, it["id"], x0 + 4, 140, big, panel_w)
            else:
                surf.blit(big, (x0 + 4, 140))
            if self.kind == "vehicle":
                self._stat_bars(surf, p.player_stats(vehicle), x0 + 170, 146, panel_w - 182,
                                full=base_stats(vehicle))
        else:
            self._draw_kit_detail(surf, it, x0, panel_w)
            return
        owned = self.owned(it["id"])
        if not owned:
            label = f"BUY  {it['price']}c"
        else:
            label = "EQUIPPED" if shop.is_selected(p, self.kind, it["id"]) else "EQUIP"
        button(surf, self._action_rect(), label, on=True, size=22,
               enabled=owned or p.currency >= it["price"])

    def _draw_boost_preview(self, surf, boost, x, y, big, panel_w):
        """The bike with its heat flame at three heats: cold, boost, red window.
        Drawn at sprite scale into a small layer, then doubled."""
        from types import SimpleNamespace
        from ui.render import WorldRenderer
        rd = getattr(self, "_flame_rd", None) or WorldRenderer(320)
        self._flame_rd = rd
        sel = self.app.profile.selected
        sprite = self.sprites.vehicle(sel["vehicle"], self.app.profile.player_livery(), (self.t // 6) % 2)
        cx, cy = 66, 60                                   # contact point inside the layer
        temps = (C.ONE_BOOST_AT * 0.7, (C.ONE_BOOST_AT + C.ONE_SUPER_AT) / 2, C.ONE_SUPER_AT + 3)
        for k, temp in enumerate(temps):
            layer = pygame.Surface((100, 66), pygame.SRCALPHA)
            fake = SimpleNamespace(x=0.0, lane_pos=0.0, angle=0.0, temp=temp,
                                   h=C.lane_y(0) + C.LANE_SPACING // 2 + 2 - cy,
                                   stats=SimpleNamespace(vehicle=sel["vehicle"]))
            rd.draw_heat_flame(layer, fake, C.BIKE_SCREEN_X - cx, self.t, boost)
            layer.blit(sprite, (cx - art.CONTACT[0], cy - art.CONTACT[1]))
            big2 = pygame.transform.scale(layer, (layer.get_width() * 6 // 5, layer.get_height() * 6 // 5))
            bx = x + 4 + k * (panel_w - 16) // 3
            surf.blit(big2, (bx, y + 4))
            hud.text(surf, ("cold", "boost", "overheating")[k], (bx + big2.get_width() * 2 // 3, y + 88), 15,
                     (200, 196, 220), anchor="center")

    # -- Starter Kit ----------------------------------------------------------------------
    def _draw_kit_row(self, surf, r, it, on):
        level = self._level(it["id"])
        pygame.draw.rect(surf, (78, 70, 110) if on else (46, 42, 66), r, border_radius=6)
        if on:
            pygame.draw.rect(surf, C.ACCENT, r, 2, border_radius=6)
        hud.text(surf, it["name"], (r.x + 10, r.centery), 20, C.HUD_FG if level else (190, 186, 210),
                 anchor="midleft")
        for k in range(MAX_LEVEL):                    # level pips
            x = r.right - 10 - (MAX_LEVEL - k) * 9
            col = CATEGORY_COLORS.get(it["category"], C.GOOD) if k < level else (90, 86, 110)
            pygame.draw.rect(surf, col, (x, r.centery - 4, 7, 8), border_radius=2)

    def _draw_kit_detail(self, surf, it, x0, panel_w):
        p = self.app.profile
        level = self._level(it["id"])
        price = self._price(it["id"])
        grey = (200, 196, 220)
        head = it["category"].upper()
        if self.kind == "tune":
            head = VEHICLES[p.selected["vehicle"]]["name"].upper()
        hud.text(surf, f"{head}  -  level {level} / {MAX_LEVEL}", (x0 + 12, 118), 18, grey)
        hud.text(surf, "Now:", (x0 + 12, 146), 18, grey)
        now = self._describe(it["id"], level) if level or self.kind == "tune" else "nothing yet"
        hud.text(surf, now, (x0 + 62, 146), 18)
        if price is not None:
            hud.text(surf, "Next:", (x0 + 12, 168), 18, grey)
            hud.text(surf, self._describe(it["id"], level + 1), (x0 + 62, 168), 18, C.GOOD)
        hud.text(surf, "Max:", (x0 + 12, 190), 18, grey)
        hud.text(surf, self._describe(it["id"], MAX_LEVEL), (x0 + 62, 190), 18, grey)
        note = ("Tunes your equipped bike only: every bike is tuned on its own, and level 5 "
                "is its full stat. Each level costs more than the last." if self.kind == "tune" else
                "Every level you buy applies to every run, all kit items at once. "
                "Each level costs more than the last.")
        _wrap(surf, note, x0 + 12, 226, panel_w - 24, 16)
        label = "MAXED" if price is None else f"LEVEL UP  {price}c"
        button(surf, self._action_rect(), label, on=True, size=22,
               enabled=price is not None and p.currency >= price)

    @staticmethod
    def _stat_rows(s):
        return [
            ("Top speed", (s.max_speed_a - 38) / 14),
            ("Accel", (1 / s.accel_interval - 0.18) / 0.14),
            ("Cool engine", (0.10 - s.heat_b) / 0.05),
            ("Air control", (s.pitch_rate - 1.3) / 1.6),
            ("Landing", (s.land_tolerance - 8) / 14),
            ("Dirt grip", (s.grip[DIRT] - 0.6) / 0.4),
            ("Grass grip", (s.grip[GRASS] - 0.6) / 0.4),
            ("Sand grip", (s.grip[SAND] - 0.6) / 0.4),
        ]

    def _stat_bars(self, surf, s, x, y, w, full=None):
        """Bars for stats `s`; with `full`, a dim marker shows the fully tuned value."""
        rows = self._stat_rows(s)
        fulls = self._stat_rows(full) if full else [(None, None)] * len(rows)
        for i, ((label, k), (_, kf)) in enumerate(zip(rows, fulls)):
            yy = y + i * 17
            hud.text(surf, label, (x, yy), 16)
            bw = max(40, w - 90)
            surf.fill((40, 36, 52), (x + 86, yy + 3, bw, 8))
            if kf is not None and kf > k + 0.01:
                kf = max(0.05, min(1.0, kf))
                surf.fill((80, 76, 100), (x + 86, yy + 3, int(bw * kf), 8))     # room to tune
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
