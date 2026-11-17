"""Garage, two tabs:

BIKES  pick the bike you ride and spend its XP on its upgrades. The stat bars sit
       beside the upgrade list; pointing at an upgrade (or selecting it) lights up
       how far its next level moves its bar. Bikes unlock by clearing biomes.
STYLE  bike paint, rider colours and boost colours on one screen, with a big
       preview of the whole combination (try-on of whatever the cursor is on).
       Coins buy these, and only these.
"""
import pygame

import config as C
from bike import VEHICLES, base_stats
from meta import shop
from meta.bike_tune import UPGRADES, MAX_LEVEL, apply_tune, stat_bars
from ui import hud, art
from ui.art import LIVERIES, BOOSTS, livery_key
from ui.menus import BackdropScene, button

TABS = [("bikes", "BIKES"), ("style", "STYLE")]
STYLE_ROWS = [("livery", "BIKE PAINT"), ("rider", "RIDER"), ("boost", "BOOST")]
GREY = (200, 196, 220)
DIM = (150, 146, 170)
XP_COL = (120, 210, 255)
PREVIEW_COL = (140, 230, 255)


class GarageScene(BackdropScene):
    def __init__(self, app, back=None):
        super().__init__(app)
        self.back = back
        self.tab = 0
        self.flash = None          # (text, color, ticks)
        self.sprites = art.SpriteCache()
        self.hover = None          # logical mouse position while it hovers
        shop.check_vehicle_unlocks(app.profile)
        app.profile.save()
        # BIKES: the bike being viewed and the upgrade row
        self.vi = list(VEHICLES).index(app.profile.selected["vehicle"])
        self.row = 0
        self.confirm = None        # reset waiting for a second tap: ("bike" | "all", ticks left)
        # STYLE: cursor (row, column), starting on what's equipped
        self.srow = 0
        self.scol = [self._equipped_index(k) for k, _ in STYLE_ROWS]

    # -- shared ----------------------------------------------------------------------
    @property
    def kind(self):
        return TABS[self.tab][0]

    def _back_rect(self):
        return pygame.Rect(10, 8, 70, 26)

    def _tab_rects(self):
        return [pygame.Rect(90 + i * 100, 8, 94, 26) for i in range(len(TABS))]

    def _action_rect(self):
        W = self.app.view.width
        return pygame.Rect(W - 200, C.VIEW_H - 44, 188, 34)

    def _reset_rects(self):
        """BIKES tab: refund this bike's upgrades / every bike's (left of UPGRADE)."""
        a = self._action_rect()
        return {"all": pygame.Rect(a.x - 98, a.y, 92, 22),
                "bike": pygame.Rect(a.x - 98 - 100, a.y, 94, 22)}

    def _leave(self):
        if self.back:
            self.back()
        else:
            from ui.menus import TitleScene
            self.app.set_scene(TitleScene(self.app))

    def _say(self, text, col, ticks=70):
        self.flash = (text, col, ticks)

    def update(self):
        super().update()
        if self.flash:
            t, c, n = self.flash
            self.flash = (t, c, n - 1) if n > 1 else None
        if self.confirm:
            which, n = self.confirm
            self.confirm = (which, n - 1) if n > 1 else None

    def frame(self, inp):
        for kind, _, x, y in inp.pointer_events:
            if kind in ("hover", "move", "down"):
                self.hover = (x, y)
        if self.hover is not None:
            self._hover_select(*self.hover)
        for k in inp.keys_down:
            if k in (pygame.K_ESCAPE, pygame.K_AC_BACK):
                return self._leave()
            if k in (pygame.K_TAB, pygame.K_q, pygame.K_e):
                self.tab = (self.tab + 1) % len(TABS)
            elif self.kind == "bikes":
                self._bikes_key(k)
            else:
                self._style_key(k)
        for x, y in inp.taps():
            if self._back_rect().collidepoint(x, y):
                return self._leave()
            for i, r in enumerate(self._tab_rects()):
                if r.collidepoint(x, y):
                    self.tab = i
                    return
            if self.kind == "bikes":
                self._bikes_tap(x, y)
            else:
                self._style_tap(x, y)

    def _hover_select(self, x, y):
        """The mouse pointing at a row selects it (that's the hover preview)."""
        if self.kind == "bikes":
            for i, r in enumerate(self._row_rects()):
                if r.collidepoint(x, y):
                    self.row = i
        else:
            for ri, rects in enumerate(self._swatch_rects()):
                for ci, r in enumerate(rects):
                    if r.collidepoint(x, y):
                        self.srow, self.scol[ri] = ri, ci

    # -- BIKES: data ---------------------------------------------------------------------
    @property
    def vehicle(self):
        return list(VEHICLES)[self.vi]

    def _owned(self, v=None):
        return (v or self.vehicle) in self.app.profile.data["vehicles"]

    def _levels(self):
        return self.app.profile.bike_levels(self.vehicle)

    def _next_price(self, uid):
        return shop.upgrade_price(self.app.profile, self.vehicle, uid)

    # -- BIKES: layout -------------------------------------------------------------------
    def _chip_rects(self):
        n = len(VEHICLES)
        w = 112
        return [pygame.Rect(14 + i * (w + 6), 42, w, 26) for i in range(n)]

    def _row_rects(self):
        return [pygame.Rect(14, 76 + i * 26, 236, 24) for i in range(len(UPGRADES))]

    # -- BIKES: input --------------------------------------------------------------------
    def _bikes_key(self, k):
        n = len(UPGRADES)
        if k in (pygame.K_LEFT, pygame.K_a):
            self._view_bike((self.vi - 1) % len(VEHICLES))
        elif k in (pygame.K_RIGHT, pygame.K_d):
            self._view_bike((self.vi + 1) % len(VEHICLES))
        elif k in (pygame.K_UP, pygame.K_w):
            self.row = (self.row - 1) % n
            self.hover = None
        elif k in (pygame.K_DOWN, pygame.K_s):
            self.row = (self.row + 1) % n
            self.hover = None
        elif k in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_z):
            self._buy_upgrade()
        elif k == pygame.K_r:
            self._reset("all" if pygame.key.get_mods() & pygame.KMOD_SHIFT else "bike")

    def _bikes_tap(self, x, y):
        for i, r in enumerate(self._chip_rects()):
            if r.collidepoint(x, y):
                self._view_bike(i)
                return
        for i, r in enumerate(self._row_rects()):
            if r.collidepoint(x, y):
                if self.row == i:
                    self._buy_upgrade()    # mouse: hover then click; touch: tap twice
                self.row = i
                return
        if self._action_rect().collidepoint(x, y):
            self._buy_upgrade()
        for which, r in self._reset_rects().items():
            if r.collidepoint(x, y):
                self._reset(which)

    CONFIRM_TICKS = 150

    def _reset(self, which):
        """Refund upgrades for this bike ("bike") or every bike ("all"). Asks for a
        second tap / key press first, since it wipes levels."""
        p = self.app.profile
        name = VEHICLES[self.vehicle]["name"]
        if not self.confirm or self.confirm[0] != which:
            self.confirm = (which, self.CONFIRM_TICKS)
            what = f"the {name}'s upgrades" if which == "bike" else "upgrades on ALL bikes"
            self.app.audio.ui("click")
            self._say(f"Refund {what}? Tap again to confirm", C.ACCENT, self.CONFIRM_TICKS)
            return
        self.confirm = None
        back = p.refund_bike(self.vehicle) if which == "bike" else p.refund_all_bikes()
        p.save()
        self.app.audio.ui("buy")
        who = name if which == "bike" else "All bikes"
        self._say(f"{who} reset to stock: {back} XP refunded", C.GOOD)

    def _view_bike(self, i):
        """Show a bike; an unlocked one is also equipped (it's the one you'll ride)."""
        self.vi = i
        if self._owned():
            if shop.select(self.app.profile, "vehicle", self.vehicle):
                self.app.audio.ui("click")

    def _buy_upgrade(self):
        p = self.app.profile
        uid = list(UPGRADES)[self.row]
        up = UPGRADES[uid]
        cost = self._next_price(uid)
        if not self._owned():
            self.app.audio.ui("deny")
            self._say(shop.unlock_text(self.vehicle), C.DANGER, 80)
        elif cost is None:
            self.app.audio.ui("deny")
            self._say(f"{up.name} is maxed", GREY, 50)
        elif shop.buy_upgrade(p, self.vehicle, uid):
            self.app.audio.ui("buy")
            self._say(f"{up.name} level {self._levels()[uid]}!  {up.stat} up", C.GOOD)
        else:
            self.app.audio.ui("deny")
            self._say(f"Need {cost - p.bike_xp(self.vehicle)} more XP: race this bike in runs", C.DANGER, 80)

    # -- STYLE: data ---------------------------------------------------------------------
    def _style_items(self, kind):
        return list(shop.PRICES[kind])

    def _equipped_index(self, kind):
        items = self._style_items(kind)
        for i, it in enumerate(items):
            if shop.is_selected(self.app.profile, kind, it):
                return i
        return 0

    def _cursor(self):
        kind = STYLE_ROWS[self.srow][0]
        return kind, self._style_items(kind)[self.scol[self.srow]]

    def _style_owned(self, kind, item):
        return item in self.app.profile.data[shop.KIND_KEY[kind]]

    def _swatch_rects(self):
        out = []
        for ri in range(len(STYLE_ROWS)):
            y = 66 + ri * 82
            out.append([pygame.Rect(14 + ci * 44, y + 18, 40, 40) for ci in range(len(self._style_items(
                STYLE_ROWS[ri][0])))])
        return out

    # -- STYLE: input --------------------------------------------------------------------
    def _style_key(self, k):
        n = len(self._style_items(STYLE_ROWS[self.srow][0]))
        if k in (pygame.K_UP, pygame.K_w):
            self.srow = (self.srow - 1) % len(STYLE_ROWS)
        elif k in (pygame.K_DOWN, pygame.K_s):
            self.srow = (self.srow + 1) % len(STYLE_ROWS)
        elif k in (pygame.K_LEFT, pygame.K_a):
            self.scol[self.srow] = (self.scol[self.srow] - 1) % n
        elif k in (pygame.K_RIGHT, pygame.K_d):
            self.scol[self.srow] = (self.scol[self.srow] + 1) % n
        else:
            if k in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_z):
                self._style_act()
            return
        self.hover = None

    def _style_tap(self, x, y):
        for ri, rects in enumerate(self._swatch_rects()):
            for ci, r in enumerate(rects):
                if r.collidepoint(x, y):
                    same = self.srow == ri and self.scol[ri] == ci
                    self.srow, self.scol[ri] = ri, ci
                    kind, item = self._cursor()
                    if same or self._style_owned(kind, item):
                        self._style_act()       # owned: equip on tap; for sale: tap again (or BUY)
                    return
        if self._action_rect().collidepoint(x, y):
            self._style_act()

    def _style_act(self):
        p = self.app.profile
        kind, item = self._cursor()
        name = (BOOSTS if kind == "boost" else LIVERIES)[item]["name"]
        if not self._style_owned(kind, item):
            cost = shop.PRICES[kind][item]
            if shop.buy(p, kind, item):
                shop.select(p, kind, item)
                self.app.audio.ui("buy")
                self._say(f"Unlocked {name}!", C.GOOD)
            else:
                self.app.audio.ui("deny")
                self._say(f"Need {cost - p.currency} more coins", C.DANGER, 60)
            return
        if not shop.is_selected(p, kind, item):
            shop.select(p, kind, item)
            self.app.audio.ui("click")

    # -- drawing ---------------------------------------------------------------------------
    def draw(self, surf):
        W = self.app.view.width
        p = self.app.profile
        self.draw_bg(surf)
        button(surf, self._back_rect(), "< BACK", size=18)
        for i, (r, (_, label)) in enumerate(zip(self._tab_rects(), TABS)):
            button(surf, r, label, on=i == self.tab, size=18)
        hud.text(surf, f"{p.currency} coins", (W - 12, 12), 22, C.ACCENT, anchor="topright")
        if self.kind == "bikes":
            self._draw_bikes(surf, W)
        else:
            self._draw_style(surf, W)
        if self.flash:
            y = C.VIEW_H - 9 if self.kind == "bikes" else C.VIEW_H - 28    # under the reset buttons
            hud.text(surf, self.flash[0], (14, y), 16 if self.kind == "bikes" else 18, self.flash[1],
                     anchor="midleft")

    # -- BIKES -----------------------------------------------------------------------------
    def _draw_bikes(self, surf, W):
        p = self.app.profile
        for i, (r, v) in enumerate(zip(self._chip_rects(), VEHICLES)):
            owned = self._owned(v)
            on = i == self.vi
            pygame.draw.rect(surf, (78, 70, 110) if on else (46, 42, 66), r, border_radius=6)
            if on:
                pygame.draw.rect(surf, C.ACCENT, r, 2, border_radius=6)
            label = VEHICLES[v]["name"] if owned else "LOCKED"
            hud.text(surf, label, (r.centerx - (6 if p.selected["vehicle"] == v else 0), r.centery), 16,
                     C.HUD_FG if owned else DIM, anchor="center")
            if p.selected["vehicle"] == v:
                pygame.draw.circle(surf, C.GOOD, (r.right - 9, r.centery), 4)     # the bike you ride
        owned = self._owned()
        levels = self._levels()
        xp = p.bike_xp(self.vehicle)
        for i, (r, (uid, up)) in enumerate(zip(self._row_rects(), UPGRADES.items())):
            on = i == self.row
            lv = levels.get(uid, 0)
            cost = self._next_price(uid)
            pygame.draw.rect(surf, (78, 70, 110) if on else (46, 42, 66), r, border_radius=5)
            if on:
                pygame.draw.rect(surf, C.ACCENT, r, 2, border_radius=5)
            hud.text(surf, up.name, (r.x + 8, r.centery), 16, C.HUD_FG if owned else DIM, anchor="midleft")
            for k in range(MAX_LEVEL):                          # level pips
                x = r.x + 110 + k * 9
                pygame.draw.rect(surf, C.GOOD if k < lv else (90, 86, 110), (x, r.centery - 4, 7, 8),
                                 border_radius=2)
            if cost is None:
                tag, col = "MAX", C.GOOD
            else:
                tag, col = f"{cost} XP", (XP_COL if owned and xp >= cost else (170, 120, 120))
            hud.text(surf, tag, (r.right - 7, r.centery), 15, col, anchor="midright")
        self._draw_bike_panel(surf, W)

    def _draw_bike_panel(self, surf, W):
        p = self.app.profile
        v = self.vehicle
        x0 = 262
        pw = W - x0 - 12
        hud.panel(surf, (x0, 76, pw, 236), 200)
        owned = self._owned()
        livery = p.player_livery()
        img = self.sprites.vehicle(v, livery, (self.t // 6) % 2)
        big = pygame.transform.scale(img, (img.get_width() * 3 // 2, img.get_height() * 3 // 2))
        surf.blit(big, (x0 + 2, 72))
        tx = x0 + big.get_width() + 6
        hud.text(surf, VEHICLES[v]["name"], (tx, 82), 22, C.ACCENT)
        if owned:
            hud.text(surf, f"{p.bike_xp(v)} XP", (x0 + pw - 10, 84), 20, XP_COL, anchor="topright")
            _wrap(surf, VEHICLES[v]["desc"], tx, 106, x0 + pw - tx - 8, 15, GREY)
        else:
            _wrap(surf, shop.unlock_text(v), tx, 106, x0 + pw - tx - 8, 15, C.DANGER)
        # stat bars, with the selected upgrade's next level previewed
        uid = list(UPGRADES)[self.row]
        levels = self.app.profile.bike_levels(v)
        now = stat_bars(apply_tune(base_stats(v), levels))
        cost = self._next_price(uid)
        nxt = None
        if cost is not None:
            nxt = stat_bars(apply_tune(base_stats(v), {**levels, uid: levels.get(uid, 0) + 1}))
        top = stat_bars(apply_tune(base_stats(v), {u: MAX_LEVEL for u in UPGRADES}))
        bx, bw = x0 + 104, pw - 140
        y = 152
        for i, (rid, label, k) in enumerate(now):
            yy = y + i * 15
            hot = rid == uid
            hud.text(surf, label, (x0 + 10, yy), 14, C.ACCENT if hot else C.HUD_FG)
            surf.fill((40, 36, 52), (bx, yy + 3, bw, 9))
            surf.fill((66, 62, 84), (bx, yy + 3, int(bw * top[i][2]), 9))          # fully upgraded
            col = C.GOOD if k > 0.66 else (C.ACCENT if k > 0.33 else C.DANGER)
            surf.fill(col, (bx, yy + 3, max(2, int(bw * k)), 9))
            if hot and nxt is not None and nxt[i][2] > k:
                gain = int(bw * nxt[i][2]) - int(bw * k)
                pulse = 160 + int(70 * abs(((self.t % 40) - 20) / 20))
                surf.fill((pulse, 240, 255), (bx + int(bw * k), yy + 3, max(2, gain), 9))
                pct = (nxt[i][2] - k) * 100
                hud.text(surf, f"+{pct:.0f}", (bx + bw + 6, yy), 14, PREVIEW_COL)
            if hot:
                pygame.draw.rect(surf, C.ACCENT, (bx - 1, yy + 2, bw + 2, 11), 1)
        up = UPGRADES[uid]
        if cost is not None:
            line = f"{up.name} {levels.get(uid, 0) + 1}: {up.describe(levels.get(uid, 0) + 1)} vs stock"
        else:
            line = f"{up.name} maxed: {up.describe(MAX_LEVEL)} vs stock"
        hud.text(surf, line, (x0 + 10, 308), 14, GREY, anchor="bottomleft")
        if not owned:
            label, enabled = "LOCKED", False
        elif cost is None:
            label, enabled = "MAXED", False
        else:
            label, enabled = f"UPGRADE  {cost} XP", p.bike_xp(v) >= cost
        button(surf, self._action_rect(), label, on=True, size=20, enabled=enabled)
        conf = self.confirm[0] if self.confirm else None
        for which, r in self._reset_rects().items():
            text = "CONFIRM?" if conf == which else ("RESET BIKE" if which == "bike" else "RESET ALL")
            button(surf, r, text, on=conf == which, size=14)
        if p.settings.get("free_upgrades", False):
            hud.text(surf, "FREE UPGRADES (testing)", (300, 14), 14, C.ACCENT)

    # -- STYLE -----------------------------------------------------------------------------
    def _draw_style(self, surf, W):
        p = self.app.profile
        sel = p.selected
        for ri, ((kind, title), rects) in enumerate(zip(STYLE_ROWS, self._swatch_rects())):
            y = 66 + ri * 82
            hud.text(surf, title, (14, y), 16, C.ACCENT if ri == self.srow else GREY)
            for ci, (r, item) in enumerate(zip(rects, self._style_items(kind))):
                owned = self._style_owned(kind, item)
                pygame.draw.rect(surf, (46, 42, 66), r, border_radius=6)
                self._swatch(surf, kind, item, r.inflate(-10, -10))
                if not owned:
                    shade = pygame.Surface(r.size, pygame.SRCALPHA)
                    shade.fill((20, 16, 28, 120))
                    surf.blit(shade, r)
                    hud.text(surf, f"{shop.PRICES[kind][item]}", (r.centerx, r.bottom + 7), 12,
                             C.ACCENT if p.currency >= shop.PRICES[kind][item] else (170, 120, 120),
                             anchor="center")
                if shop.is_selected(p, kind, item):
                    pygame.draw.rect(surf, C.GOOD, r, 2, border_radius=6)
                if ri == self.srow and ci == self.scol[ri]:
                    pygame.draw.rect(surf, C.ACCENT, r.inflate(4, 4), 2, border_radius=7)
        # the whole combination, with the cursor's item tried on
        kind, item = self._cursor()
        look = {"livery": sel.get("livery", "flame"), "rider": sel.get("rider", sel.get("livery", "flame")),
                "boost": sel.get("boost", "flame")}
        look[kind] = item
        x0 = 286
        pw = W - x0 - 12
        hud.panel(surf, (x0, 44, pw, 268), 200)
        names = (f"{LIVERIES[look['livery']]['name']} bike  -  {LIVERIES[look['rider']]['name']} rider  -  "
                 f"{BOOSTS[look['boost']]['name']} boost")
        hud.text(surf, "YOUR LOOK" if self._style_owned(kind, item) else "PREVIEW", (x0 + pw // 2, 52), 18,
                 C.ACCENT, anchor="midtop")
        hud.text(surf, names, (x0 + pw // 2, 72), 13, GREY, anchor="midtop")
        self._draw_combo(surf, sel["vehicle"], look, x0, pw)
        if self._style_owned(kind, item):
            label = "EQUIPPED" if shop.is_selected(p, kind, item) else "EQUIP"
            enabled = True
        else:
            cost = shop.PRICES[kind][item]
            label, enabled = f"BUY  {cost} coins", p.currency >= cost
        button(surf, self._action_rect(), label, on=True, size=20, enabled=enabled)
        conf = self.confirm[0] if self.confirm else None
        for which, r in self._reset_rects().items():
            text = "CONFIRM?" if conf == which else ("RESET BIKE" if which == "bike" else "RESET ALL")
            button(surf, r, text, on=conf == which, size=14)
        if p.settings.get("free_upgrades", False):
            hud.text(surf, "FREE UPGRADES (testing)", (300, 14), 14, C.ACCENT)

    @staticmethod
    def _swatch(surf, kind, item, r):
        if kind == "boost":
            pal = BOOSTS[item]
            cols = (pal["cold"][0][0], pal["boost"][0][0], pal["boost"][1][0], pal["red"][1][1])
            w = r.w / len(cols)
            for i, c in enumerate(cols):
                surf.fill(c, (r.x + int(i * w), r.y, int(w) + 1, r.h))
            return
        lv = LIVERIES[item]
        if kind == "livery":
            surf.fill(lv["body"], r)
            surf.fill(lv["dark"], (r.x, r.bottom - r.h // 3, r.w, r.h // 3))
        else:
            surf.fill(lv["suit"], r)
            pygame.draw.circle(surf, lv["helmet"], r.center, r.w // 3)
            pygame.draw.circle(surf, (20, 16, 28), r.center, r.w // 3, 1)

    def _draw_combo(self, surf, vehicle, look, x0, pw):
        """Big bike + rider with the boost flame, and the flame in all four heat zones."""
        from types import SimpleNamespace
        from ui.render import WorldRenderer
        rd = getattr(self, "_flame_rd", None) or WorldRenderer(320)
        self._flame_rd = rd
        key = livery_key(look["livery"], look["rider"])
        sprite = self.sprites.vehicle(vehicle, key, (self.t // 6) % 2)

        def bike_with_flame(temp, scale):
            cx, cy = 66, 60
            layer = pygame.Surface((100, 66), pygame.SRCALPHA)
            fake = SimpleNamespace(x=0.0, lane_pos=0.0, angle=0.0, temp=temp,
                                   h=C.lane_y(0) + C.LANE_SPACING // 2 + 2 - cy,
                                   stats=SimpleNamespace(vehicle=vehicle))
            rd.draw_heat_flame(layer, fake, C.BIKE_SCREEN_X - cx, self.t, look["boost"])
            layer.blit(sprite, (cx - art.CONTACT[0], cy - art.CONTACT[1]))
            return pygame.transform.scale(layer, (int(100 * scale), int(66 * scale)))

        big = bike_with_flame((C.ONE_HOT_AT + C.ONE_OVERHEAT_AT) / 2, 2.2)
        surf.blit(big, (x0 + pw // 2 - big.get_width() * 66 // 100, 84))
        temps = (C.ONE_BOOST_AT * 0.7, (C.ONE_BOOST_AT + C.ONE_HOT_AT) / 2,
                 (C.ONE_HOT_AT + C.ONE_OVERHEAT_AT) / 2, C.ONE_OVERHEAT_AT + 3)
        cell = pw // 4
        for k, temp in enumerate(temps):
            small = bike_with_flame(temp, 0.8)
            bx = x0 + k * cell + (cell - small.get_width()) // 2 + 6
            surf.blit(small, (bx, 232))
            hud.text(surf, ("cold", "warm", "hot", "overheating")[k], (x0 + k * cell + cell // 2, 290), 13,
                     GREY, anchor="center")


def _wrap(surf, text, x, y, w, size, col=C.HUD_FG):
    f = hud.font(size)
    line = ""
    for word in text.split():
        t = (line + " " + word).strip()
        if f.size(t)[0] > w and line:
            hud.text(surf, line, (x, y), size, col)
            y += size - 2
            line = word
        else:
            line = t
    if line:
        hud.text(surf, line, (x, y), size, col)
