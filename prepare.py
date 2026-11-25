"""Prepare the project data for hosted deployment (Vercel and similar).

    python prepare.py path/to/data.csv

Runs the full analysis once (summaries, sample records, cluster map) and writes data/prepared.pkl.gz.
Deploy that file together with the code. To change the data later, run this again and redeploy.
Use the same package versions as requirements-hosted.txt so the hosted server can read the file.
"""
import gzip, os, pickle, sys, time
from pathlib import Path

os.environ.pop("VERCEL", None); os.environ.pop("NANOSKOP_HOSTED", None)
from app import engine, cluster  # noqa: E402

DEFAULTS = dict(k=5, min_cohort=20, round_to=5, num_min=10, sample_n=40, sample_enabled=True, column_modes={})

def main(path, out="data/prepared.pkl.gz"):
    t = time.time()
    cfg = dict(DEFAULTS)
    for key in ("k", "min_cohort", "round_to", "num_min"):
        if os.environ.get("NANOSKOP_" + key.upper()): cfg[key] = int(os.environ["NANOSKOP_" + key.upper()])
    ds = engine.Dataset(engine.read_csv_robust(Path(path).read_bytes()), cfg, os.environ.get("NANOSKOP_NAME", "Nanomedicine dataset"))
    print(f"Read {ds.n:,} rows and {len(ds.raw_cols)} columns.")
    sample = ds.draw_sample(cfg["sample_n"], 7); sample["version"] = ds.version
    topic = ds.topic_match()
    ds._terms()
    print("Building the cluster map (a few minutes)...")
    ds.clusters = cluster.build(ds, lambda p: print("  " + p))
    ds.cache = {}
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wb", compresslevel=6) as fh:
        pickle.dump(dict(ds=ds, sample=sample, topic=topic, made=time.strftime("%Y-%m-%d %H:%M")), fh, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"Wrote {out} ({Path(out).stat().st_size / 1e6:.1f} MB) in {time.time() - t:.0f} s.")

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(__doc__)
    main(sys.argv[1])
