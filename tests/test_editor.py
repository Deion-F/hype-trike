"""Milestone 6: editor I/O, share codes, validation warnings, painting."""
import os

import pytest

from editor import io as tio
from track.static import static_track
from track.tiles import GAP, RAMP_S, START, DEBRIS, FLAT, Track, make_track
from track.validator import validate


def test_share_code_roundtrip():
    t = static_track()
    code = tio.encode(t)
    assert code.startswith("HT1-") and len(code) < 400
    t2 = tio.decode(code)
    assert t2.terrain == t.terrain and t2.surface == t.surface
    assert t2.material == t.material and t2.laps == t.laps and t2.name == t.name


def test_share_code_tolerates_whitespace_and_case_prefix():
    code = tio.encode(static_track())
    messy = "  ht1-" + "\n".join(code[4:][i:i + 20] for i in range(0, len(code) - 4, 20)) + " "
    assert tio.decode(messy).terrain == static_track().terrain


@pytest.mark.parametrize("bad", ["", "hello", "HT1-", "HT1-abc", "HT1-!!!!", None])
def test_bad_codes_raise_friendly_error(bad):
    with pytest.raises(tio.CodeError):
        tio.decode(bad)


def test_truncated_code_rejected():
    code = tio.encode(static_track())
    with pytest.raises(tio.CodeError):
        tio.decode(code[:-6])


def test_import_sanitises_fields():
    d = tio.to_compact(static_track())
    d["g"] = "." + d["g"][1:5] + "S" + d["g"][6:]     # no start at 0, extra start later
    d["l"] = 99
    d["t"] = "evil"
    d["n"] = "<script>" * 10
    t = tio.from_compact(d)
    assert t.terrain[0] == START and START not in t.terrain[1:]
    assert t.laps == 9 and t.theme == "valley" and "<" not in t.name and len(t.name) <= 24


def test_length_limits():
    d = tio.to_compact(make_track("S...."))
    with pytest.raises(tio.CodeError):
        tio.from_compact(d)


def test_json_save_load(tmp_path, monkeypatch):
    monkeypatch.setenv("HYPE_DATA_DIR", str(tmp_path))
    from meta.profile import Profile, Storage
    p = Profile.load(Storage())
    t = static_track(); t.name = "My Jumps"
    path = tio.save_track(p, t)
    assert path and os.path.exists(path)
    assert tio.from_json(open(path).read()).terrain == t.terrain
    p2 = Profile.load(Storage())
    assert "My Jumps" in tio.list_tracks(p2)
    assert tio.load_track(p2, "My Jumps").terrain == t.terrain
    # a JSON file dropped into the folder is picked up
    t.name = "Dropped In"
    open(os.path.join(tio.tracks_dir(), "x.json"), "w").write(tio.to_json(t))
    assert "Dropped In" in tio.list_tracks(p2)


def test_validator_flags_unclearable_gap():
    # small ramp straight into a 3-wide pit is unclearable at base speed
    t = make_track("S........sggg........", laps=1)
    res = validate(t)
    assert not res["ok"] and any(r == "pit" for r, _ in res["crashes"])


def test_editor_scene_paint_undo_and_check():
    import pygame
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import main as M
    from editor.ui import EditorScene, TOOLS
    app = M.App()
    e = EditorScene(app, tio.blank_track(30))
    gap = [i for i, t in enumerate(TOOLS) if t[2] == "Gap"][0]
    ramp = [i for i, t in enumerate(TOOLS) if t[2] == "Ramp S"][0]
    inp = app.input

    def stroke(col, lane):
        x = 30 + (col - e.scroll) * e.cw + 3
        y = e.lane_y(lane) + 5
        inp.begin_frame(); inp._down("m", x, y); e.frame(inp)
        inp.begin_frame(); inp._move("m", x + 1, y + 13); e.frame(inp)
        inp.begin_frame(); inp._up("m", x + 1, y + 13); e.frame(inp)

    assert e.check_ok
    e.tool = ramp; stroke(9, 0)
    e.tool = gap
    for c in (10, 11, 12):
        stroke(c, 1)
    assert e.track.terrain[9] == RAMP_S and e.track.terrain[10:13] == [GAP] * 3
    assert not e.check_ok and e.warnings            # live ghost warning
    for _ in range(3):
        e.undo()
    assert e.track.terrain[10] == FLAT and e.check_ok
    stroke(0, 0)                                     # start column is locked
    assert e.track.terrain[0] == START


def test_share_code_keeps_water_and_the_volcano_theme():
    from editor import io as tio
    from track.tiles import make_track, WATER
    t = make_track("S" + "." * 20, laps=2)
    t.surface[2][7] = WATER
    t.theme = "lava"
    back = tio.decode(tio.encode(t))
    assert back.surface[2][7] == WATER and back.theme == "lava"


def test_share_code_roundtrip_with_structures():
    t = make_track("S..utUTTDtkd..f.ff...")
    assert tio.decode(tio.encode(t)).terrain == t.terrain
