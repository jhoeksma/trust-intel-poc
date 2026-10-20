"""Read-only: what the benchmarking layer sees in the live database.  python -m scripts.bench_check"""
from collections import Counter

from app import benchmark
from app.db import SessionLocal

with SessionLocal() as db:
    cat = benchmark.catalogue(db)
    print("BENCH catalogue", len(cat), "measures;", Counter(c["source"] for c in cat))
    print("BENCH polarity", Counter(c["polarity"] or "none" for c in cat))
    print("BENCH core", [(c["core_rank"], c["metric_code"], c["orgs"]) for c in sorted((c for c in cat if c["core"]), key=lambda c: c["core_rank"])])
    missing = [w for w in benchmark.CORE_FIELDS if not any(c["core"] and (c["metric_code"] == w or c["metric_code"].split(":", 1)[-1] == w) for c in cat)]
    print("BENCH core_unresolved", missing)
    g = benchmark.peer_groups(db)
    print("BENCH groups", Counter(g.values()))
    for ods in ("RJ1", "RNK", "RY3", "RX8", "RRK"):
        b = benchmark.trust_benchmark(db, ods, benchmark.core_codes(db), "peers")
        print("BENCH", ods, b["peer_group"], [(m["metric_code"].split(":", 1)[-1], m["value"] is not None and round(m["value"], 2), m.get("rank"), m["stats"].get("n"), m["scope_used"]) for m in b["metrics"]])
    v = benchmark.metric_view(db, "nof:of5200", None)
    print("BENCH segment view", v["stats"], len(v["points"]))
