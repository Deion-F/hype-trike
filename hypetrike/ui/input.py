"""Unified input: keyboard + multi-touch + mouse, in logical coordinates.

Race controls (decision Q2): on-screen buttons for throttle (A), turbo (B),
lean back / lean forward, plus vertical swipes anywhere else for lane changes.
Menus and the editor consume generic pointer events (down / move / up / tap).
"""
import pygame

from bike import Controls

SWIPE_STEP = 26          # logical px of vertical drag per lane change
TAP_SLOP = 12            # max movement for a tap


class Button:
    def __init__(self, name, cx, cy, r, label):
        self.name, self.cx, self.cy, self.r, self.label = name, cx, cy, r, label

    def hit(self, x, y, pad=8):
        return (x - self.cx) ** 2 + (y - self.cy) ** 2 <= (self.r + pad) ** 2


class Pointer:
    __slots__ = ("pid", "x", "y", "sx", "sy", "button", "swipe_y", "moved")

    def __init__(self, pid, x, y):
        self.pid, self.x, self.y, self.sx, self.sy = pid, x, y, x, y
        self.button = None
        self.swipe_y = y
        self.moved = False


class InputManager:
    def __init__(self, view):
        self.view = view               # object with .width/.height and to_logical()
        self.pointers = {}
        self.touch_seen = False
        self.force_touch_ui = False
        self.pointer_events = []       # (kind, pid, x, y) for menus/editor this frame
        self.keys_down = []            # pygame key codes pressed this frame
        self.text_in = []
        self._edge = {"lane_up": False, "lane_down": False}
        self.race_mode = False
        self.settings = {}
        self.layout(view.width)

    # -- layout --------------------------------------------------------------
    def layout(self, width):
        h = self.view.height
        st = getattr(self, "settings", None) or {}
        k = float(st.get("button_scale", 1.0))
        swap = st.get("swap_sides", False)
        lane_btns = st.get("lane_mode", "swipe") in ("buttons", "both")
        L = lambda x: width - x if swap else x      # noqa: E731
        R = lambda x: x if swap else width - x      # noqa: E731
        self.buttons = [
            Button("left", L(48 * k), h - 54 * k, 28 * k, "<"),
            Button("right", L(118 * k), h - 54 * k, 28 * k, ">"),
            Button("b", R(128 * k), h - 62 * k, 28 * k, "B"),
            Button("a", R(54 * k), h - 50 * k, 32 * k, "A"),
        ]
        if lane_btns:
            self.buttons += [
                Button("up", L(83 * k), h - 160 * k, 22 * k, "^"),
                Button("down", L(83 * k), h - 112 * k, 22 * k, "v"),
            ]
        self.buttons.append(Button("pause", width - 20, 64, 14, "II"))

    @property
    def show_touch(self):
        mode = self.settings.get("touch_ui", "auto")
        if mode == "on":
            return True
        if mode == "off":
            return False
        return self.touch_seen or self.force_touch_ui

    # -- event intake -------------------------------------------------------------
    def begin_frame(self):
        self.pointer_events = []
        self.keys_down = []
        self.text_in = []

    def handle(self, e):
        if e.type == pygame.TEXTINPUT:
            self.text_in.append(e.text)
            return
        if e.type == pygame.KEYDOWN:
            self.keys_down.append(e.key)
            if e.key in (pygame.K_UP, pygame.K_w):
                self._edge["lane_up"] = True
            elif e.key in (pygame.K_DOWN, pygame.K_s):
                self._edge["lane_down"] = True
        elif e.type == pygame.FINGERDOWN:
            self.touch_seen = True
            x, y = e.x * self.view.width, e.y * self.view.height
            self._down(("f", e.finger_id), x, y)
        elif e.type == pygame.FINGERMOTION:
            self._move(("f", e.finger_id), e.x * self.view.width, e.y * self.view.height)
        elif e.type == pygame.FINGERUP:
            self._up(("f", e.finger_id), e.x * self.view.width, e.y * self.view.height)
        elif e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
            if getattr(e, "touch", False) or self.touch_seen:
                return  # synthetic mouse from touch; fingers already handled
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) and e.button == 3:
                x, y = self.view.to_logical(e.pos)
                self.pointer_events.append(("rdown" if e.type == pygame.MOUSEBUTTONDOWN else "rup", "r", x, y))
                return
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) and e.button != 1:
                return
            x, y = self.view.to_logical(e.pos)
            if e.type == pygame.MOUSEBUTTONDOWN:
                self._down("m", x, y)
            elif e.type == pygame.MOUSEMOTION:
                if "m" in self.pointers:
                    self._move("m", x, y)
                else:
                    self.pointer_events.append(("hover", "m", x, y))
                if e.buttons[2]:
                    self.pointer_events.append(("rmove", "r", x, y))
            else:
                self._up("m", x, y)
        elif e.type == pygame.MOUSEWHEEL:
            self.pointer_events.append(("wheel", "m", e.y, e.x))

    def _down(self, pid, x, y):
        p = Pointer(pid, x, y)
        if self.race_mode and self.show_touch:
            for b in self.buttons:
                if b.hit(x, y):
                    p.button = b.name
                    if b.name == "up":
                        self._edge["lane_up"] = True
                    elif b.name == "down":
                        self._edge["lane_down"] = True
                    break
        self.pointers[pid] = p
        self.pointer_events.append(("down", pid, x, y))

    def _move(self, pid, x, y):
        p = self.pointers.get(pid)
        if not p:
            return
        p.x, p.y = x, y
        if abs(x - p.sx) > TAP_SLOP or abs(y - p.sy) > TAP_SLOP:
            p.moved = True
        swipe_ok = self.settings.get("lane_mode", "swipe") in ("swipe", "both")
        if self.race_mode and p.button is None and swipe_ok:
            dy = y - p.swipe_y
            if dy <= -SWIPE_STEP:
                self._edge["lane_up"] = True
                p.swipe_y = y
            elif dy >= SWIPE_STEP:
                self._edge["lane_down"] = True
                p.swipe_y = y
        elif self.race_mode and p.button in ("left", "right", "a", "b"):
            # thumbs slide between neighbouring buttons
            for b in self.buttons:
                if b.name != "pause" and b.hit(x, y, pad=4):
                    p.button = b.name
                    break
        self.pointer_events.append(("move", pid, x, y))

    def _up(self, pid, x, y):
        p = self.pointers.pop(pid, None)
        self.pointer_events.append(("up", pid, x, y))
        if p and not p.moved:
            self.pointer_events.append(("tap", pid, x, y))

    # -- queries ---------------------------------------------------------------
    def taps(self):
        return [(x, y) for k, _, x, y in self.pointer_events if k == "tap"]

    def touch_held(self, name):
        return any(p.button == name for p in self.pointers.values())

    def race_controls(self):
        k = pygame.key.get_pressed()
        c = Controls(
            a=k[pygame.K_z] or k[pygame.K_j] or k[pygame.K_SPACE] or self.touch_held("a"),
            b=k[pygame.K_x] or k[pygame.K_k] or self.touch_held("b"),
            left=k[pygame.K_LEFT] or k[pygame.K_a] or self.touch_held("left"),
            right=k[pygame.K_RIGHT] or k[pygame.K_d] or self.touch_held("right"),
            lane_up=self._edge["lane_up"],
            lane_down=self._edge["lane_down"],
        )
        return c

    def consume_edges(self):
        self._edge["lane_up"] = False
        self._edge["lane_down"] = False

    def pause_tapped(self):
        if not self.show_touch:
            return False
        b = self.buttons[-1]
        return any(b.hit(x, y) for x, y in self.taps())

    # -- drawing ------------------------------------------------------------------
    def draw_touch(self, surf, font_fn):
        if not self.show_touch:
            return
        for b in self.buttons:
            held = self.touch_held(b.name)
            s = pygame.Surface((b.r * 2 + 2, b.r * 2 + 2), pygame.SRCALPHA)
            col = {"a": (90, 220, 110), "b": (255, 120, 60)}.get(b.name, (230, 230, 240))
            pygame.draw.circle(s, (*col, 150 if held else 70), (b.r + 1, b.r + 1), b.r)
            pygame.draw.circle(s, (*col, 220), (b.r + 1, b.r + 1), b.r, 2)
            surf.blit(s, (b.cx - b.r - 1, b.cy - b.r - 1))
            f = font_fn(26 if b.r > 20 else 16)
            img = f.render(b.label, False, (255, 255, 255))
            surf.blit(img, img.get_rect(center=(b.cx, b.cy)))
