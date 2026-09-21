import csv
from pathlib import Path

from analysis.plot import main
from analysis.tests.test_report import make_run


def test_plot_writes_figures_and_csv_twins(tmp_path: Path) -> None:
    exps = tmp_path / "experiments"
    for c in (1, 2, 4):
        for i in range(3):
            make_run(
                exps / f"w4-c{c}",
                f"r{i}",
                hit=1 / c,
                ttft_p95=500 * c + i,
                config={"replay": {"concurrency": c}},
            )
    make_run(exps / "w4-c4-timestamp", "r0", hit=0.1, ttft_p95=18000, config={"replay": {"concurrency": 4}})
    for name in ("w3-control", "w3-timestamp"):
        make_run(exps / name, "r0", hit=0.9, ttft_p95=500)
    out = tmp_path / "figures"

    assert main(["--experiments-dir", str(exps), "--out", str(out)]) == 0
    for stem in ("w4-concurrency", "w3-transforms"):
        assert (out / f"{stem}.png").stat().st_size > 0 and (out / f"{stem}-dark.png").stat().st_size > 0
    with (out / "w4-concurrency.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert [r["experiment"] for r in rows] == ["w4-c1", "w4-c2", "w4-c4", "w4-c4-timestamp"]
    assert rows[2]["cache_hit_rate_n"] == "3" and rows[3]["transform"] == "system_timestamp"
    assert rows[0]["evicted_mtok_n"] == "0"  # no metrics snapshots in the fixture → skipped, not crashed
    with (out / "w3-transforms.csv").open() as f:
        assert [r["transform"] for r in csv.DictReader(f)] == ["append-only (control)", "system_timestamp"]

    # nothing to plot → non-zero, no files
    assert main(["--experiments-dir", str(tmp_path / "empty"), "--out", str(tmp_path / "none")]) == 1
    assert not (tmp_path / "none").exists()
