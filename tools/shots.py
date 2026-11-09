"""Headless screenshots + art sheet.

  python tools/shots.py OUT_DIR

Renders: an art sheet (vehicles x liveries, rider poses, tiles, themes) and
in-race frames with the ghost AI driving the player.
"""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("HYPE_DATA_DIR", os.path.join(os.path.dirname(__file__), ".shotdata"))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hypetrike")
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

import config as C  # noqa: E402


def art_sheet(out):
    from ui import art, hud
    from ui.render import WorldRenderer
    from track.tiles import Track, FLAT, RAMP_S, RAMP_L, GAP, WHOOPS, START, COOLANT, MUD, DEBRIS, GRASS, SAND
    S = 4
    sheet = pygame.Surface((1200, 1400))
    sheet.fill((30, 28, 44))
    hud.text(sheet, "HYPE TRIKE - art sheet (generated in code)", (20, 14), 36, C.ACCENT)
    y = 60
    for vi, v in enumerate(["dirt", "trike", "scrambler", "sprinter"]):
        hud.text(sheet, v.upper(), (20, y + 70), 24)
        for li, liv in enumerate(["flame", "ocean", "lime", "violet", "gold"]):
            img = art.DRAWERS[v](art.LIVERIES[liv], li % 2)
            sheet.blit(pygame.transform.scale(img, (img.get_width() * 3, img.get_height() * 3)),
                       (150 + li * 170, y))
        y += 140
    hud.text(sheet, "RIDER: tumble x4, jog x2   |   bike vibration frames 0/1 (4x)", (20, y), 24)
    y += 30
    liv = art.LIVERIES["flame"]
    x = 20
    for t in range(4):
        img = art.draw_rider_tumble(liv, t)
        sheet.blit(pygame.transform.scale(img, (img.get_width() * S, img.get_height() * S)), (x, y))
        x += 110
    for t in (0, 6):
        img = art.draw_rider_run(liv, t)
        sheet.blit(pygame.transform.scale(img, (img.get_width() * S, img.get_height() * S)), (x, y))
        x += 80
    for f in (0, 1):
        img = art.draw_dirt_bike(liv, f)
        sheet.blit(pygame.transform.scale(img, (img.get_width() * S, img.get_height() * S)), (x, y - 20))
        x += 220
    y += 190
    hud.text(sheet, "TRACK TILES (2x): flat, ramp S, ramp L, gap, whoops, start, coolant/mud/debris, grass, sand", (20, y), 22)
    y += 26
    terr = [START, FLAT, RAMP_S, FLAT, RAMP_L, FLAT, GAP, FLAT, WHOOPS, WHOOPS, FLAT, FLAT, FLAT, FLAT]
    tr = Track(terr)
    tr.surface[0][10] = COOLANT
    tr.surface[1][11] = MUD
    tr.surface[2][12] = DEBRIS
    tr.surface[3][10] = MUD
    for i in (12, 13):
        tr.material[i] = GRASS
    tr.material[13] = SAND
    tr.rebuild()
    rd = WorldRenderer(560, "valley")
    for row, (start, theme) in enumerate([(0, "valley"), (7, "desert")]):
        rd.set_theme(theme, 560)
        s = pygame.Surface((560, 360))
        cam = start * C.TILE_W + C.BIKE_SCREEN_X
        rd.draw_backdrop(s, cam)
        rd.draw_track(s, tr, cam)
        sheet.blit(pygame.transform.scale(s.subsurface((0, 100, 560, 250)), (560, 250)), (20 + row * 590, y))
    y += 270
    hud.text(sheet, "THEMES", (20, y), 22)
    y += 24
    for i, th in enumerate(["valley", "desert", "night", "stadium"]):
        rd.set_theme(th, 560)
        s = pygame.Surface((560, 360))
        rd.draw_backdrop(s, 300)
        rd.draw_track(s, tr, 300)
        sheet.blit(pygame.transform.smoothscale(s, (280, 180)), (20 + i * 292, y))
        hud.text(sheet, th, (24 + i * 292, y + 4), 20)
    pygame.image.save(sheet, os.path.join(out, "art_sheet.png"))


def race_frames(out, ticks=(200, 560, 900, 1500), vehicle="dirt", rivals=3, tag="race"):
    import main as M
    from track.validator import GhostAI
    app = M.App()
    from ui.menus import TitleScene
    sc = TitleScene(app)
    app.set_scene(sc)
    app.draw()
    pygame.image.save(app.view.surface, os.path.join(out, "title.png"))
    sc.exhibition() if rivals else sc.practice()
    race_scene = app.scene
    ai = GhostAI(turbo=True, turbo_temp=26)
    app.input.force_touch_ui = True
    orig = app.input.race_controls
    app.input.race_controls = lambda: ai.controls(race_scene.race.bike)
    last = max(ticks)
    for t in range(1, last + 1):
        app.input.begin_frame()
        app.scene.frame(app.input)
        app.scene.update()
        if t in ticks:
            app.draw()
            pygame.image.save(app.view.surface, os.path.join(out, f"{tag}_{t:05d}.png"))
    app.input.race_controls = orig
    return race_scene


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "shots"
    os.makedirs(out, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((640, 360))
    art_sheet(out)
    race_frames(out)
    print("saved to", out)
