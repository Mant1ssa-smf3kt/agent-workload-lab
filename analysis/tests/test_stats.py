from analysis.stats import pct, pct_censored, percentile


def test_percentile_nearest_rank() -> None:
    xs = [1.0, 2.0, 3.0, 4.0]
    assert percentile(xs, 50) == 2.0 and percentile(xs, 95) == 4.0 and percentile(xs, 0) == 1.0


def test_pct_censored_matches_pct_without_censoring() -> None:
    vals = [5.0, 1.0, None, 3.0]
    c = pct_censored((v, False) for v in vals)
    p = pct(vals)
    assert {k: c[k] for k in p} == p  # type: ignore[literal-required]
    assert c["n_censored"] == 0 and not c["p99_censored"] and not c["max_censored"]


def test_pct_censored_flags_ranks_at_or_above_first_bound() -> None:
    # 100 observations; two timed out at 600 s. P50/P95 exact, P99 lands on a censored value.
    xs: list[tuple[float | None, bool]] = [(float(i), False) for i in range(1, 99)]
    xs += [(600_000.0, True), (600_000.0, True)]
    c = pct_censored(xs)
    assert c["n"] == 100 and c["n_censored"] == 2
    assert c["p50"] == 50.0 and not c["p50_censored"]
    assert c["p95"] == 95.0 and not c["p95_censored"]
    assert c["p99"] == 600_000.0 and c["p99_censored"] and c["max_censored"]

    # a censored value ranked *below* P95 makes P95 and P99 bounds even if they land on exact values
    mixed: list[tuple[float | None, bool]] = [(1.0, False), (2.0, True), (3.0, False), (4.0, False)]
    m = pct_censored(mixed)
    assert m["p50"] == 2.0 and m["p50_censored"]
    assert m["p99"] == 4.0 and m["p99_censored"] and not m["max_censored"]

    e = pct_censored([])
    assert e["n"] == 0 and e["p50"] is None and not e["p99_censored"]
