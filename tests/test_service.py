"""End-to-end tests of the privacy rules: python -m pytest tests -q"""
import io, json, os, re, tempfile, time
import numpy as np, pandas as pd, pytest

tmp = tempfile.mkdtemp()
os.environ.update(NANOSKOP_DATA=tmp, NANOSKOP_ADMIN_PASSWORD="yonetici-parola", NANOSKOP_VIEWER_CODE="goruntule1")
from fastapi.testclient import TestClient
from app.main import app, state, CFG, _hits

SECRET = "GIZLI-DOI-10.1234"
def csv_bytes():
    r = np.random.RandomState(0); n = 600
    df = pd.DataFrame({
        "kaynak_id": [f"{SECRET}-{i}" for i in range(n)],
        "grup": r.choice(["A", "B", "C"], n, p=[.6, .3, .1]),
        "nadir": ["tek-bir-kisi"] + ["yaygin"] * (n - 1),
        "olcum": r.normal(100, 15, n).round(2),
        "ikinci": r.normal(5, 1, n).round(3),
        "notlar": [f"terim{i % 7} ortak ifade" for i in range(n)],
    })
    df.loc[0, "olcum"] = 987654.0  # tek bir uç değer
    return df.to_csv(index=False).encode(), df

@pytest.fixture(scope="module")
def clients():
    _hits.clear()
    a = TestClient(app); v = TestClient(app)
    assert a.post("/api/login", json={"code": "yonetici-parola"}).json()["role"] == "admin"
    assert v.post("/api/login", json={"code": "goruntule1"}).json()["role"] == "viewer"
    raw, df = csv_bytes()
    assert a.post("/admin/api/upload", files={"file": ("x.csv", raw)}, data={"name": "Test"}).status_code == 200
    t = time.time()
    while state["status"] not in ("ready", "error") and time.time() - t < 240: time.sleep(1)
    assert state["status"] == "ready", state["error"]
    return a, v, df

def viewer_urls(meta):
    u = ["/api/meta", "/api/overview", "/api/quality", "/api/dictionary", "/api/flow", "/api/cooccurrence", "/api/correlation", "/api/sample", "/api/completeness"]
    for c in meta["columns"]:
        u += [f"/api/column/{c['name']}", f"/api/explore?x={c['name']}"]
    for b in meta["bases"]:
        u.append(f"/api/map?basis={b['key']}")
    return u

def test_no_auth_no_data():
    c = TestClient(app)
    for p in ["/api/overview", "/api/sample", "/api/dictionary"]:
        assert c.get(p).status_code == 401
    assert c.get("/admin/api/config").status_code == 403

def test_csv_never_served(clients):
    a, v, _ = clients
    for p in ["/data/current.csv", "/static/../data/current.csv", "/static/%2e%2e/data/current.csv", "/current.csv"]:
        assert SECRET not in v.get(p).text

def test_viewer_cannot_use_admin(clients):
    _, v, _ = clients
    assert v.get("/admin/api/config").status_code == 403
    assert v.post("/admin/api/resample").status_code == 403
    assert v.post("/admin/api/upload", files={"file": ("x.csv", b"a,b\n1,2\n")}).status_code == 403

def test_nothing_leaks_anywhere(clients):
    _, v, _ = clients
    meta = v.get("/api/meta").json()
    assert not any(c["name"] == "kaynak_id" for c in meta["columns"]), "kimlik alanı keşfedilebilir olmamalı"
    for u in viewer_urls(meta):
        t = v.get(u).text
        assert SECRET not in t, u
        assert "tek-bir-kisi" not in t or u == "/api/sample", u
        assert "987654" not in t, u

def test_id_column_blocked(clients):
    _, v, _ = clients
    assert v.get("/api/column/kaynak_id").status_code == 404
    assert v.get("/api/explore?x=kaynak_id").status_code == 404

def test_small_cells_suppressed_and_rounded(clients):
    _, v, df = clients
    d = v.get("/api/explore?x=olcum&y=ikinci").json()
    k = CFG["k"]
    assert all(c[2] >= k for c in d["cells"])
    meta = v.get("/api/meta").json()
    key = meta["dims"][0]["key"]; opt = meta["dims"][0]["options"][0]["value"]
    o = v.get(f"/api/overview?f.{key}={opt}").json()
    assert o["n"] % CFG["round_to"] == 0

def test_narrow_filter_refused(clients):
    a, v, df = clients
    meta = v.get("/api/meta").json()
    old = CFG["min_cohort"]; CFG["min_cohort"] = 10 ** 6
    state["ds"].cache.clear()
    key = meta["dims"][0]["key"]; opt = meta["dims"][0]["options"][0]["value"]
    r = v.get(f"/api/overview?f.{key}={opt}")
    CFG["min_cohort"] = old; state["ds"].cache.clear()
    assert r.status_code == 422 and r.json()["code"] == "cohort_too_small"

def test_invalid_filter_rejected(clients):
    _, v, _ = clients
    assert v.get("/api/overview?f.kaynak_id=x").status_code == 400

def test_numbers_match_source(clients):
    _, v, df = clients
    d = v.get("/api/explore?x=ikinci").json()
    assert d["summary"]["n"] == df["ikinci"].notna().sum()
    assert d["summary"]["p50"] == pytest.approx(df["ikinci"].median(), rel=.01)

def test_sample_size_and_columns(clients):
    _, v, _ = clients
    s = v.get("/api/sample").json()
    assert s["n"] == 40 and "seed" not in s
    assert not any(c["key"] == "kaynak_id" for c in s["columns"])

def test_hidden_column_disappears(clients):
    a, v, _ = clients
    assert a.put("/admin/api/config", json={"column_modes": {"notlar": "hidden"}}).json()["rebuilding"]
    time.sleep(.5); t = time.time()
    while state["status"] != "ready" and time.time() - t < 240: time.sleep(1)
    meta = v.get("/api/meta").json()
    assert not any(c["name"] == "notlar" for c in meta["columns"])
    assert "terim1" not in v.get("/api/dictionary").text
    assert v.get("/api/column/notlar").status_code == 404
    a.put("/admin/api/config", json={"column_modes": {}})
    t = time.time(); time.sleep(.5)
    while state["status"] != "ready" and time.time() - t < 240: time.sleep(1)

def test_wrong_code(clients):
    _hits.clear()
    assert TestClient(app).post("/api/login", json={"code": "yanlis"}).status_code == 401

def _wait_mine(client, t=120):
    end = time.time() + t
    while time.time() < end:
        m = client.get("/api/meta?src=mine").json()
        if m["status"] in ("ready", "error"): return m
        time.sleep(.5)
    raise AssertionError("own data did not finish")

def test_own_data_is_private_and_removable(clients):
    _hits.clear()
    a, v, df = clients
    own = pd.DataFrame({"kind": ["p", "q", "r"] * 40, "value": np.arange(120) * 1.5, "note": ["benim-gizli-notum"] * 120})
    r = v.post("/api/mydata", files={"file": ("mine.csv", own.to_csv(index=False).encode())})
    assert r.status_code == 200, r.text
    m = _wait_mine(v)
    assert m["status"] == "ready" and m["n"] == 120 and m["src"] == "mine"
    assert v.get("/api/overview?src=mine").json()["n"] == 120
    assert v.get("/api/overview").json()["n"] == len(df)          # project view unchanged
    other = TestClient(app); assert other.post("/api/login", json={"code": "goruntule1"}).status_code == 200
    assert other.get("/api/overview?src=mine").status_code == 409  # another session cannot reach it
    assert other.get("/api/meta").json()["mine"] is None
    assert "benim-gizli-notum" not in other.get("/api/dictionary").text
    assert "benim-gizli-notum" in v.get("/api/dictionary?src=mine").text
    assert not any("benim-gizli-notum" in p.read_text(errors="ignore") for p in __import__("pathlib").Path(tmp).rglob("*") if p.is_file())
    assert v.delete("/api/mydata").status_code == 200
    assert v.get("/api/overview?src=mine").status_code == 409

def test_own_data_rejects_non_csv(clients):
    _hits.clear()
    _, v, _ = clients
    assert v.post("/api/mydata", files={"file": ("x.xlsx", b"PK")}).status_code == 400
    assert TestClient(app).post("/api/mydata", files={"file": ("x.csv", b"a,b\n1,2\n")}).status_code == 401

def test_coverage_shape(clients):
    _, v, _ = clients
    d = v.get("/api/completeness").json()
    assert d["rows"] and len(d["all"]) == len(d["cols"]) and all(len(r["values"]) == len(d["cols"]) for r in d["rows"])
