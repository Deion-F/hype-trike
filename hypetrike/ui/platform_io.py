"""Clipboard + text prompts on web (browser APIs) and desktop (pygame)."""
import sys

import pygame

WEB = sys.platform == "emscripten"


def web_prompt(message, default=""):
    """Blocking browser prompt. Returns str, or None if cancelled/unavailable."""
    if not WEB:
        return None
    try:
        import platform as _p
        v = _p.window.prompt(message, default)
        if v is None:
            return None
        v = str(v)
        return None if v in ("null", "undefined") else v
    except Exception:
        return None


def copy_text(text):
    """Copy to clipboard. Returns True if it (probably) worked."""
    if WEB:
        # Browsers may refuse clipboard writes outside a direct tap; swallow the
        # rejection in JS so pygbag doesn't surface an "uncaught" alert.
        try:
            import json
            import platform as _p
            _p.window.eval("navigator.clipboard && navigator.clipboard.writeText(%s)"
                           ".catch(function(){})" % json.dumps(text))
        except Exception:
            pass
        return False   # unknown; caller also shows the code in a prompt
    try:
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        pygame.scrap.put_text(text)
        return True
    except Exception:
        return False


def paste_text():
    if WEB:
        return None
    try:
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        t = pygame.scrap.get_text()
        return t or None
    except Exception:
        return None


class TextEntry:
    """Minimal in-game single-line text box (desktop). Feed it InputManager
    text/keys each frame; .done is True on Enter/Esc, .value None if cancelled."""

    def __init__(self, title, value="", max_len=400):
        self.title = title
        self.value = value
        self.max_len = max_len
        self.done = False
        self.cancelled = False

    def feed(self, inp):
        for t in inp.text_in:
            self.value = (self.value + t)[: self.max_len]
        for k in inp.keys_down:
            mods = pygame.key.get_mods()
            if k == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
            elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.done = True
            elif k == pygame.K_ESCAPE:
                self.done = self.cancelled = True
            elif k == pygame.K_v and mods & (pygame.KMOD_CTRL | pygame.KMOD_META):
                pasted = paste_text()
                if pasted:
                    self.value = (self.value + pasted.strip())[: self.max_len]

    def draw(self, surf, hud, W):
        hud.panel(surf, (20, 120, W - 40, 100), 235)
        hud.text(surf, self.title, (34, 130), 22, (255, 196, 0))
        box = pygame.Rect(34, 156, W - 68, 28)
        pygame.draw.rect(surf, (20, 18, 30), box, border_radius=4)
        shown = self.value
        f = hud.font(20)
        while shown and f.size(shown + "_")[0] > box.w - 12:
            shown = shown[1:]
        hud.text(surf, shown + ("_" if (pygame.time.get_ticks() // 400) % 2 else " "), (box.x + 6, box.y + 7), 20)
        hud.text(surf, "Enter = OK   Esc = cancel   Ctrl+V = paste", (34, 196), 16, (200, 196, 220))
