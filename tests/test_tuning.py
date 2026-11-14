"""tools/tuning.py: report, archive and the simulated curve."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.path.insert(0, os.path.dirname(__file__))

import replay as rp  # noqa: E402
import tuning  # noqa: E402
from test_replay import record_race  # noqa: E402


def _recs(folder):
    for i, heat in enumerate((0, 0, 5)):
        _, d = record_race(True, seed=20 + i, depth=1)
        d["context"] = {"kind": "run", "heat": heat, "upgrades": []}
        d["summary"]["target_met"] = heat == 0
        rp.save(d, str(folder))


def test_report_groups_by_heat_and_flags_the_curve(tmp_path):
    _recs(tmp_path)
    rows, segs = tuning.aggregate(rp.list_recordings(str(tmp_path)))
    by = {r["group"]: r for r in rows}
    assert by["run heat 1"]["races"] == 2 and by["run heat 1"]["target_met"] == 1.0
    assert by["run heat 6"]["target_met"] == 0.0 and by["run heat 6"]["curve_goal"] == tuning.TARGET_CURVE[5]


def test_archive_moves_recordings_out_of_the_live_folder(tmp_path):
    _recs(tmp_path)
    tuning.main(["--dir", str(tmp_path), "archive", "--note", "test pass"])
    assert rp.list_recordings(str(tmp_path)) == []
    stamp = os.listdir(tmp_path / "archive")[0]
    files = os.listdir(tmp_path / "archive" / stamp)
    assert "NOTE.md" in files and sum(f.endswith(".json") for f in files) == 3
    assert "test pass" in (tmp_path / "archive" / stamp / "NOTE.md").read_text()


def test_sim_run_plays_every_heat():
    out = tuning.sim_run(1000, "good", "one")
    from run.manager import RUN_HEATS
    assert [h["heat"] for h in out] == list(range(RUN_HEATS))
    assert len(tuning.TARGET_CURVE) == RUN_HEATS
    assert out[0]["met"]                      # a good player clears the first heat
