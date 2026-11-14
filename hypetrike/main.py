"""Hype Trike entry point.

Desktop:  python main.py           (from the hypetrike/ folder)
Web/APK:  pygbag hypetrike         (pygbag needs this async main loop)
"""
import asyncio
import os
import sys

import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as C  # noqa: E402
from audio import Audio, pre_init as audio_pre_init  # noqa: E402
from ui.input import InputManager  # noqa: E402

WEB = sys.platform == "emscripten"


def _web_aspect():
    try:
        import platform as _p
        w = _p.window.innerWidth
        h = _p.window.innerHeight
        return float(w) / float(h), h > w
    except Exception:
        return 16 / 9, False


class View:
    """Logical canvas (width x 360) and its mapping to the real window."""

    def __init__(self):
        self.height = C.VIEW_H
        self.portrait = False
        if WEB:
            aspect, self.portrait = _web_aspect()
            self.width = self._width_for(aspect)
            self.window = pygame.display.set_mode((self.width, self.height))
        else:
            size = (1280, 720)
            if os.environ.get("HYPE_WINDOW"):
                size = tuple(int(v) for v in os.environ["HYPE_WINDOW"].split("x"))
            self.window = pygame.display.set_mode(size, pygame.RESIZABLE)
            self.width = self._width_for(size[0] / size[1])
        self.surface = pygame.Surface((self.width, self.height))
        self.smooth = False
        # crisp text at window resolution (not in the browser or headless runs)
        self.hires_text = (not WEB and os.environ.get("SDL_VIDEODRIVER") != "dummy"
                           and not os.environ.get("HYPE_LOWRES_TEXT"))
        self._hires_fonts = {}
        self._sync_text_canvas()

    def _sync_text_canvas(self):
        from ui import hud
        hud.set_hires_canvas(self.surface if self.hires_text else None)

    def _width_for(self, aspect):
        w = int(round(self.height * max(aspect, 1.0)))
        w = max(C.MIN_VIEW_W, min(C.MAX_VIEW_W, w))
        return w - w % 2

    def resized(self, size=None):
        old = self.width
        if WEB:
            aspect, self.portrait = _web_aspect()
            self.width = self._width_for(aspect)
            if self.width != old:
                self.window = pygame.display.set_mode((self.width, self.height))
        else:
            size = size or self.window.get_size()
            self.width = self._width_for(size[0] / max(1, size[1]))
        if self.width != old:
            self.surface = pygame.Surface((self.width, self.height))
            self._sync_text_canvas()
            return True
        return False

    def _dest_rect(self):
        ww, wh = self.window.get_size()
        scale = min(ww / self.width, wh / self.height)
        w, h = int(self.width * scale), int(self.height * scale)
        return pygame.Rect((ww - w) // 2, (wh - h) // 2, w, h)

    def to_logical(self, pos):
        if WEB:
            return pos
        r = self._dest_rect()
        return ((pos[0] - r.x) * self.width / max(1, r.w),
                (pos[1] - r.y) * self.height / max(1, r.h))

    def _sharp_scale(self, size):
        """Pixel-art upscale without uneven pixels: nearest-neighbour to the largest
        whole multiple, then a smooth stretch for the remaining fraction. (A plain
        nearest scale by e.g. 3.67x makes some pixel columns 3 px wide and others
        4 px, which reads as jagged text.)"""
        sw, sh = self.surface.get_size()
        k = max(1, min(size[0] // sw, size[1] // sh))
        mid = (sw * k, sh * k)
        cache = getattr(self, "_scale_cache", None)
        if cache is None or cache[0].get_size() != mid or cache[1].get_size() != size:
            cache = (pygame.Surface(mid), pygame.Surface(size))
            self._scale_cache = cache
        if k > 1:
            pygame.transform.scale(self.surface, mid, cache[0])
            src = cache[0]
        else:
            src = self.surface
        if mid == size:
            return src
        pygame.transform.smoothscale(src, size, cache[1])
        return cache[1]

    def present(self):
        if WEB:
            if self.window is not self.surface:
                self.window.blit(self.surface, (0, 0))
        else:
            r = self._dest_rect()
            self.window.fill((0, 0, 0))
            if r.size == self.surface.get_size():
                self.window.blit(self.surface, r)
            elif self.smooth:
                self.window.blit(pygame.transform.smoothscale(self.surface, r.size), r)
            else:
                self.window.blit(self._sharp_scale(r.size), r)
            self._draw_hires_text(r)
        pygame.display.flip()

    def _draw_hires_text(self, r):
        """Queued HUD text (ui.hud.text), drawn smooth at the scaled size, centred on
        where it sat on the low-res canvas."""
        from ui import hud
        k = r.w / self.width
        prev = self.window.get_clip()
        for s, lr, size, color, shadow, clip, anchor in hud.take_queued():
            px = max(1, int(round(size * k)))
            f = self._hires_fonts.get(px)
            if f is None:
                f = self._hires_fonts[px] = pygame.font.Font(None, px)
            # keep the text's own anchor (left-aligned lines stay flush), vertically centred
            ax, ay = getattr(lr, anchor)
            ax, ay = r.x + ax * k, r.y + ay * k
            horiz = "left" if "left" in anchor else "right" if "right" in anchor else "centerx"
            cy = r.y + lr.centery * k
            self.window.set_clip(pygame.Rect(int(r.x + clip.x * k), int(r.y + clip.y * k),
                                             int(clip.w * k) + 1, int(clip.h * k) + 1))
            img = f.render(s, True, color)
            box = img.get_rect(**{horiz: ax, "centery": cy})
            if shadow:
                self.window.blit(f.render(s, True, (0, 0, 0)), box.move(round(k), round(k)))
            self.window.blit(img, box)
        self.window.set_clip(prev)


class App:
    def __init__(self):
        audio_pre_init()                 # mixer format + buffer must be set before pygame.init()
        pygame.init()
        pygame.display.set_caption(C.TITLE)
        self.view = View()
        self.input = InputManager(self.view)
        if WEB:
            self.input.force_touch_ui = True
        self.audio = Audio()
        from meta.profile import Profile
        self.profile = Profile.load()
        self.apply_settings()
        self.running = True
        self.scene = None
        self._aspect_check = 0
        from ui.menus import TitleScene
        self.set_scene(TitleScene(self))

    def apply_settings(self):
        st = self.profile.settings
        self.input.settings = st
        self.input.layout(self.view.width)
        self.view.smooth = st.get("smooth", False)
        if hasattr(self.audio, "configure"):
            self.audio.configure(st.get("sound", True), st.get("music", True),
                                 st.get("sfx_vol", 1.0), st.get("music_vol", 1.0))

    def set_scene(self, scene):
        self.scene = scene

    def handle_events(self):
        self.input.begin_frame()
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type in (pygame.VIDEORESIZE, pygame.WINDOWSIZECHANGED):
                if self.view.resized(getattr(e, "size", None)):
                    self.input.layout(self.view.width)
                    if self.scene:
                        self.scene.on_resize()
            else:
                self.input.handle(e)
        if WEB:
            self._aspect_check += 1
            if self._aspect_check % 30 == 0 and self.view.resized():
                self.input.layout(self.view.width)
                self.scene.on_resize()

    def draw(self):
        surf = self.view.surface
        self.scene.draw(surf)
        if self.view.portrait:
            from ui import hud
            surf.fill((20, 18, 30))
            hud.text(surf, "Rotate your phone to landscape", (self.view.width // 2, 170), 28,
                     anchor="center")
        self.view.present()


async def main():
    app = App()
    clock = pygame.time.Clock()
    step_ms = 1000.0 / C.FPS
    acc = 0.0
    while app.running:
        dt = clock.tick(C.FPS if not WEB else 0)
        # Snap near-one-step frames to exactly one step. clock.tick() works in
        # whole ms (16/17) and jitters, which otherwise makes some frames run 0
        # updates and others 2: everything visibly stutters, the scrolling
        # backdrop most of all.
        if abs(dt - step_ms) < 3.0:
            dt = step_ms
        acc += min(dt, 100)
        app.handle_events()
        app.scene.frame(app.input)
        app.audio.tick()
        n = 0
        while acc >= step_ms and n < 5:
            app.scene.update()
            acc -= step_ms
            n += 1
        app.draw()
        await asyncio.sleep(0)
    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
