"""Hand-made tracks: the Milestone 1 static track and a tutorial-ish warmup."""
from track.tiles import make_track, apply_layer, GRASS, SAND


def static_track():
    t = make_track(
        #0         1         2         3         4         5         6
        #0123456789012345678901234567890123456789012345678901234567890123
        "S.....s....s.s.....L..g....wwww.....L......s..L.gg.....s.......",
        laps=2, name="Valley Loop", theme="valley")
    apply_layer(t, 0, "........m.................c..............d..........m....")
    apply_layer(t, 1, "...............d...........................c.............")
    apply_layer(t, 2, "..........m..............c........d.....................d")
    apply_layer(t, 3, ".................m.............m..........c.........d....")
    for i in range(32, 36):
        t.material[i] = GRASS
    return t


def material_demo_track():
    t = make_track("S....s.....L....s...wwww....L.g....s.....", laps=1,
                   name="Mixed Ground", theme="desert")
    for i in range(8, 18):
        t.material[i] = GRASS
    for i in range(24, 36):
        t.material[i] = SAND
    t.rebuild()
    return t
