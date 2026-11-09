"""Milestone 3: procedural tracks (spec §5, acceptance: 10 consecutive
generated tracks are completable and visibly varied)."""
from bike import base_stats
from track.generator import generate, LIBRARY
from track.tiles import GAP, COOLANT, GRASS, SAND, START
from track.validator import validate


def test_ten_consecutive_tracks_completable_and_varied():
    shapes = set()
    for seed in range(100, 110):
        g = generate(seed, depth=seed % 6)
        assert g.validation["ok"], seed
        assert validate(g.track)["ok"]           # independent re-check
        shapes.add(tuple(g.track.terrain))
    assert len(shapes) == 10


def test_generation_is_deterministic():
    a = generate(42, 3).track.to_dict()
    b = generate(42, 3).track.to_dict()
    assert a == b


def test_difficulty_scales_with_depth():
    def score(depth):
        tot = 0
        for seed in range(12):
            t = generate(seed, depth).track
            tot += t.ncols + 10 * sum(1 for x in t.terrain if x == GAP)
        return tot
    assert score(0) < score(3) < score(5)


def test_materials_only_in_later_levels():
    for seed in range(8):
        assert all(m == 0 for m in generate(seed, 0).track.material)
    assert any(any(m in (GRASS, SAND) for m in generate(s, 4).track.material) for s in range(8))


def test_coolant_pads_present_unless_modifier():
    def pads(t):
        return sum(1 for l in t.surface for x in l if x == COOLANT)
    assert all(pads(generate(s, 2).track) > 0 for s in range(6))
    assert all(pads(generate(s, 2, modifiers=("no_coolant",)).track) == 0 for s in range(6))


def test_always_a_free_lane():
    for seed in range(20):
        t = generate(seed, 5).track
        for c in range(t.ncols):
            assert any(t.surface[l][c] in (-1, COOLANT) for l in range(4)), (seed, c)


def test_validated_for_selected_vehicle():
    for v in ("trike", "sprinter"):
        for seed in range(6):
            g = generate(seed, 4, validate_with=base_stats(v))
            assert validate(g.track, base_stats(v))["ok"]
            assert validate(g.track, base_stats("dirt"))["ok"]


def test_starts_with_start_tile():
    assert generate(1, 1).track.terrain[0] == START
