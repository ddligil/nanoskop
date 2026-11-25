"""Nanoskop API. The raw CSV is never served; the only row-level output is the admin-approved sample list."""
import hashlib, hmac, json, os, secrets, threading, time, base64, collections, gzip, pickle
from pathlib import Path
from fastapi import FastAPI, Request, Response, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from . import engine, cluster

ROOT = Path(__file__).resolve().parent.parent
# Hosted mode (Vercel and similar): the code folder is read-only, instances come and go, and there is no
# persistent disk. The project data then ships inside the deployment as a prepared file (see prepare.py),
# and the access codes come from environment variables.
HOSTED = bool(os.environ.get("VERCEL") or os.environ.get("NANOSKOP_HOSTED"))
PREPARED = Path(os.environ.get("NANOSKOP_PREPARED", ROOT / "data" / "prepared.pkl.gz"))
# Behind a reverse proxy (Nginx, Caddy) every request arrives from 127.0.0.1; the proxy's header carries the real address.
TRUST_PROXY = os.environ.get("NANOSKOP_TRUST_PROXY") == "1"
DATA = Path(os.environ.get("NANOSKOP_DATA", "/tmp/nanoskop" if HOSTED else ROOT / "data")); DATA.mkdir(parents=True, exist_ok=True)
STATIC = ROOT / "static"
CFG_PATH = DATA / "config.json"; CSV_PATH = DATA / "current.csv"; SAMPLE_PATH = DATA / "sample.json"; LOG_PATH = DATA / "access.log"
MAX_UPLOAD = int(os.environ.get("NANOSKOP_MAX_MB", "300")) * 1024 * 1024
SECURE = os.environ.get("NANOSKOP_SECURE_COOKIE", "1" if HOSTED else "0") == "1"
DEFAULTS = dict(k=5, min_cohort=20, round_to=5, num_min=10, sample_n=40, sample_enabled=True, column_modes={}, dataset_name="Nanomedicine dataset")

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

class MineMissing(Exception):
    """The caller's own file is not held by this server instance (yet)."""
state = dict(ds=None, status="empty", progress="", error=None, sample=None)
lock = threading.Lock()

def _hash(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
def _verify(pw, stored):
    if not stored: return False
    salt = stored.split("$")[0]
    return hmac.compare_digest(_hash(pw, salt), stored)

def load_cfg():
    if HOSTED:
        cfg = dict(DEFAULTS)
        for key in ("k", "min_cohort", "round_to", "num_min"):
            if os.environ.get("NANOSKOP_" + key.upper()): cfg[key] = int(os.environ["NANOSKOP_" + key.upper()])
        if os.environ.get("NANOSKOP_SAMPLES") == "0": cfg["sample_enabled"] = False
        if os.environ.get("NANOSKOP_NAME"): cfg["dataset_name"] = os.environ["NANOSKOP_NAME"][:80]
        admin = os.environ.get("NANOSKOP_ADMIN_PASSWORD", ""); viewer = os.environ.get("NANOSKOP_VIEWER_CODE", "")
        cfg["admin_hash"] = _hash(admin) if len(admin) >= 10 else None
        cfg["viewer_hash"] = _hash(viewer) if len(viewer) >= 6 else None
        if not (cfg["admin_hash"] and cfg["viewer_hash"]):
            print("Nanoskop: set NANOSKOP_ADMIN_PASSWORD (10+ characters) and NANOSKOP_VIEWER_CODE (6+ characters).", flush=True)
        # Every instance must sign sessions the same way, so the key is fixed rather than random.
        cfg["secret"] = os.environ.get("NANOSKOP_SECRET") or hashlib.sha256(f"nanoskop|{admin}|{viewer}".encode()).hexdigest()
        cfg["session_epoch"] = 1
        return cfg
    if CFG_PATH.exists():
        cfg = json.loads(CFG_PATH.read_text("utf-8"))
    else:
        cfg = dict(DEFAULTS); cfg["secret"] = secrets.token_hex(32); cfg["session_epoch"] = 1
        admin = os.environ.get("NANOSKOP_ADMIN_PASSWORD") or secrets.token_urlsafe(12)
        viewer = os.environ.get("NANOSKOP_VIEWER_CODE") or secrets.token_urlsafe(9)
        cfg["admin_hash"] = _hash(admin); cfg["viewer_hash"] = _hash(viewer)
        if not os.environ.get("NANOSKOP_ADMIN_PASSWORD"):
            print("\n=== Nanoskop first run ===\nAdmin password : %s\nViewer code    : %s\nThese values are shown only once.\n" % (admin, viewer), flush=True)
    for k, v in DEFAULTS.items(): cfg.setdefault(k, v)
    if cfg.get("dataset_name") == "Veri seti": cfg["dataset_name"] = DEFAULTS["dataset_name"]
    return cfg
CFG = load_cfg()
def save_cfg():
    if HOSTED: return
    tmp = CFG_PATH.with_suffix(".tmp"); tmp.write_text(json.dumps(CFG, ensure_ascii=False, indent=1), "utf-8"); tmp.replace(CFG_PATH)
    try: os.chmod(CFG_PATH, 0o600)
    except OSError: pass
save_cfg()

# ---- sessions ------------------------------------------------------------
TTL = 12 * 3600
def make_token(role):
    p = f"{role}|{int(time.time()) + TTL}|{CFG['session_epoch']}|{secrets.token_hex(6)}"
    sig = hmac.new(CFG["secret"].encode(), p.encode(), "sha256").hexdigest()
    return base64.urlsafe_b64encode(f"{p}|{sig}".encode()).decode()
def read_token(tok):
    try:
        p, sig = base64.urlsafe_b64decode(tok.encode()).decode().rsplit("|", 1)
        if not hmac.compare_digest(sig, hmac.new(CFG["secret"].encode(), p.encode(), "sha256").hexdigest()): return None
        role, exp, ep, sid = p.split("|")
        if int(exp) < time.time() or int(ep) != CFG["session_epoch"]: return None
        return dict(role=role, sid=sid)
    except Exception:
        return None
def session(req: Request):
    t = req.cookies.get("nanoskop")
    return read_token(t) if t else None
_hits = collections.defaultdict(collections.deque)
def limit(key, n, per):
    q = _hits[key]; now = time.time()
    while q and q[0] < now - per: q.popleft()
    if len(q) >= n: raise HTTPException(429, "Too many requests. Please wait a moment.")
    q.append(now)
def viewer(req: Request):
    s = session(req)
    if not s: raise HTTPException(401, "Sign in required.")
    limit("api:" + s["sid"], 240, 60)
    audit(req, s)
    return s
def admin(req: Request):
    s = session(req)
    if not s or s["role"] != "admin": raise HTTPException(403, "Admin sign-in required.")
    return s
def client_ip(req):
    if HOSTED and req.headers.get("x-forwarded-for"): return req.headers["x-forwarded-for"].split(",")[0].strip()
    if TRUST_PROXY:
        if req.headers.get("x-real-ip"): return req.headers["x-real-ip"].strip()
        if req.headers.get("x-forwarded-for"): return req.headers["x-forwarded-for"].split(",")[-1].strip()
    return req.client.host if req.client else "?"
def audit(req, s):
    if HOSTED:  # the hosting platform keeps stdout as its log
        print(json.dumps(dict(t=time.strftime("%Y-%m-%dT%H:%M:%S"), ip=client_ip(req), role=s["role"], sid=s["sid"], path=req.url.path, q=str(req.url.query)[:300]), ensure_ascii=False), flush=True)
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(dict(t=time.strftime("%Y-%m-%dT%H:%M:%S"), ip=client_ip(req), role=s["role"], sid=s["sid"], path=req.url.path, q=str(req.url.query)[:300]), ensure_ascii=False) + "\n")
    except OSError:
        pass

class CarryOwnFile:
    """Hosted platforms may send a request to a server copy that never received the viewer's own file.
    The page then repeats the request as POST ?carry=<name> with the compressed file as body; this
    registers the file for the session and answers the original GET."""
    def __init__(self, inner): self.inner = inner
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "POST" and scope["path"].startswith("/api/") and scope["path"] != "/api/mydata" and b"carry=" in scope.get("query_string", b""):
            from urllib.parse import parse_qs
            from starlette.requests import Request as _Rq
            req = _Rq(scope, receive); s = session(req)
            body = await req.body()
            name = parse_qs(scope["query_string"].decode()).get("carry", ["own.csv"])[0]
            if not s:
                return await JSONResponse(status_code=401, content=dict(detail="Sign in required."))(scope, receive, send)
            try:
                raw = gzip.decompress(body) if name.endswith(".gz") else body
            except OSError:
                return await JSONResponse(status_code=400, content=dict(detail="The compressed file could not be read."))(scope, receive, send)
            if len(raw) > MY_MAX:
                return await JSONResponse(status_code=413, content=dict(detail="The file is too large."))(scope, receive, send)
            entry = MY.get(s["sid"])
            if not entry or entry.get("ds") is None:
                entry = dict(name=os.path.basename(name).removesuffix(".gz")[:80], status="building", progress="", error=None, ds=None, t=time.time(), size=len(raw))
                from starlette.concurrency import run_in_threadpool
                await run_in_threadpool(_my_build, entry, raw)
                if entry["status"] == "error":
                    return await JSONResponse(status_code=400, content=dict(detail=entry.get("error") or "The file could not be used."))(scope, receive, send)
                with MY_LOCK: MY[s["sid"]] = entry
            scope = dict(scope, method="GET")
            async def empty(): return {"type": "http.request", "body": b"", "more_body": False}
            return await self.inner(scope, empty, send)
        return await self.inner(scope, receive, send)

@app.middleware("http")
async def headers(req, call_next):
    resp = await call_next(req)
    resp.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    resp.headers["X-Content-Type-Options"] = "nosniff"; resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    if req.url.path.startswith("/api") or req.url.path.startswith("/admin/api"):
        resp.headers["Cache-Control"] = "no-store"
    else:
        # pages and scripts are re-checked on every load, so an update is never hidden behind an old cached copy
        resp.headers["Cache-Control"] = "no-cache"
    return resp

@app.exception_handler(engine.CohortTooSmall)
async def small(req, exc):
    return JSONResponse(status_code=422, content=dict(code="cohort_too_small", detail=f"This selection is too narrow. Only selections with at least {CFG['min_cohort']} records can be shown. Remove a filter or choose a larger group."))
@app.exception_handler(MineMissing)
async def mine_missing(req, exc):
    return JSONResponse(status_code=409, content=dict(code="mine_missing", detail="Upload your own data first."))
@app.exception_handler(KeyError)
async def nokey(req, exc):
    return JSONResponse(status_code=404, content=dict(detail="This field is not available."))
@app.exception_handler(ValueError)
async def bad(req, exc):
    return JSONResponse(status_code=400, content=dict(detail=str(exc)))

# ---- data loading --------------------------------------------------------
def build_dataset(raw=None):
    try:
        state.update(status="building", progress="Reading CSV", error=None)
        raw = raw if raw is not None else CSV_PATH.read_bytes()
        df = engine.read_csv_robust(raw)
        ds = engine.Dataset(df, CFG, CFG.get("dataset_name", "Dataset"))
        ds.clusters = {}
        with lock:
            state["ds"] = ds
            state["status"] = "mapping"
        if SAMPLE_PATH.exists():
            s = json.loads(SAMPLE_PATH.read_text("utf-8"))
            if s.get("version") == ds.version and s.get("ui") == "en":
                state["sample"] = s
            else:
                state["sample"] = None
        if not state.get("sample"):
            _new_sample(ds)
        ds.topic_match()
        ds._terms()
        ds.clusters = cluster.build(ds, lambda p: state.update(progress=p))
        topic = ds.cache.get("topic")
        ds.cache.clear()
        if topic is not None: ds.cache["topic"] = topic
        state.update(status="ready", progress="")
    except Exception as e:
        state.update(status="error", error=str(e), progress="")
        raise

def _new_sample(ds, seed=None):
    s = ds.draw_sample(CFG["sample_n"], seed); s["version"] = ds.version; s["ui"] = "en"
    SAMPLE_PATH.write_text(json.dumps(s, ensure_ascii=False), "utf-8"); state["sample"] = s
    try: os.chmod(SAMPLE_PATH, 0o600)
    except OSError: pass

def load_prepared():
    """Hosted mode: load the dataset that prepare.py computed ahead of time (takes seconds, not minutes)."""
    try:
        with gzip.open(PREPARED, "rb") as fh: pack = pickle.load(fh)
        ds = pack["ds"]; ds.cfg = CFG; ds.name = CFG.get("dataset_name") or ds.name; ds.cache = {}
        if pack.get("topic") is not None: ds.cache["topic"] = pack["topic"]
        state.update(ds=ds, sample=pack.get("sample"), status="ready", progress="", error=None)
    except Exception as e:
        state.update(status="error", error=f"Could not load the prepared data: {e}")

@app.on_event("startup")
def startup():
    if HOSTED:
        if PREPARED.exists(): load_prepared()
        return
    if CSV_PATH.exists():
        threading.Thread(target=build_dataset, daemon=True).start()
    elif PREPARED.exists():   # server install: start with the project data shipped in the package
        load_prepared()
        if state["ds"] is not None and SAMPLE_PATH.exists():
            try:
                smp = json.loads(SAMPLE_PATH.read_text("utf-8"))
                if smp.get("version") == state["ds"].version and smp.get("ui") == "en": state["sample"] = smp
            except Exception: pass

def ensure_loaded():
    """Hosted platforms may skip the startup hook, so the prepared data also loads on first use."""
    if HOSTED and state["ds"] is None and state["status"] != "error" and PREPARED.exists():
        with lock:
            if state["ds"] is None: load_prepared()

def need():
    ensure_loaded()
    ds = state["ds"]
    if ds is None: raise HTTPException(409, "No data has been uploaded yet.")
    return ds

# ---- own data ------------------------------------------------------------
# A viewer's own CSV lives only in this process's memory, keyed by session. It is never written to disk
# and never reachable from another session. Thresholds are relaxed because it is the viewer's own data.
MY = {}
MY_LOCK = threading.Lock()
MY_MAX = int(os.environ.get("NANOSKOP_MY_MAX_MB", "50")) * 1024 * 1024
MY_MAX_ROWS = 200_000
MY_MAP_ROWS = 0 if HOSTED else 30_000   # no background work on hosted platforms
MY_MAX_SEND = 4_300_000 if HOSTED else None   # the platform's request limit, after compression
MY_IDLE = 12 * 3600
MY_SLOTS = 8
OWN_CFG = dict(k=1, min_cohort=3, round_to=1, num_min=5, sample_n=40, column_modes={})

def _my_prune():
    now = time.time()
    with MY_LOCK:
        for sid in [k for k, v in MY.items() if now - v["t"] > MY_IDLE]: MY.pop(sid, None)
        while len(MY) > MY_SLOTS:
            MY.pop(min(MY, key=lambda k: MY[k]["t"]), None)

def _my_build(entry, raw):
    try:
        df = engine.read_csv_robust(raw)
        if len(df) > MY_MAX_ROWS: raise ValueError(f"The file has {len(df):,} rows. The limit is {MY_MAX_ROWS:,}.")
        ds = engine.Dataset(df, dict(OWN_CFG), entry["name"]); ds.clusters = {}
        if ds.domain: ds.topic_match()
        entry.update(ds=ds, status="mapping", rows=ds.n, cols=len(ds.raw_cols))
        entry["sample"] = ds.draw_sample(40, 7) if ds.primary or ds.n else None
        if ds.n <= MY_MAP_ROWS:
            ds._terms()
            ds.clusters = cluster.build(ds, lambda p: entry.update(progress=p))
            topic = ds.cache.get("topic"); ds.cache.clear()
            if topic is not None: ds.cache["topic"] = topic
        else:
            entry["map_note"] = "The cluster map is not available for your own file here." if HOSTED else f"The cluster map is only built for files up to {MY_MAP_ROWS:,} rows."
        entry.update(status="ready", progress="")
    except Exception as e:
        entry.update(status="error", error=str(e), progress="", ds=None)

def pick(req: Request, s):
    """The dataset a request is about: the project data, or the caller's own upload when src=mine."""
    if req.query_params.get("src") != "mine": return need()
    e = MY.get(s["sid"])
    # On hosted platforms another instance may answer; the page then sends its copy of the file again.
    if not e: raise MineMissing()
    e["t"] = time.time()
    if e.get("ds") is None: raise HTTPException(409, "Your file is still being read." if e["status"] == "building" else e.get("error") or "Your file could not be read.")
    return e["ds"]
def filt(req: Request):
    f = {}
    for k, v in req.query_params.multi_items():
        if k.startswith("f."): f.setdefault(k[2:], []).append(v)
    return f
def cached(ds, key, fn):
    if key in ds.cache: return ds.cache[key]
    v = fn()
    if len(ds.cache) > 2000: ds.cache.clear()
    ds.cache[key] = v
    return v
def qkey(req): return req.url.path + "?" + "&".join(sorted(f"{k}={v}" for k, v in req.query_params.multi_items()))

# ---- session endpoints ----------------------------------------------------
@app.post("/api/login")
async def login(req: Request, resp: Response):
    ip = client_ip(req)
    limit("login:" + ip, 8, 300)
    body = await req.json(); code = str(body.get("code", "")).strip()
    role = "admin" if _verify(code, CFG["admin_hash"]) else "viewer" if _verify(code, CFG["viewer_hash"]) else None
    if not role: raise HTTPException(401, "That code is not valid.")
    resp.set_cookie("nanoskop", make_token(role), httponly=True, samesite="strict", secure=SECURE, max_age=TTL)
    return dict(role=role)
@app.post("/api/logout")
def logout(req: Request, resp: Response):
    sess = session(req)
    if sess: MY.pop(sess["sid"], None)
    resp.delete_cookie("nanoskop"); return dict(ok=True)

# ---- viewer endpoints ------------------------------------------------------
@app.get("/api/meta")
def meta(req: Request, s=Depends(viewer)):
    ensure_loaded()
    mine = MY.get(s["sid"])
    my_info = dict(status=mine["status"], name=mine["name"], progress=mine.get("progress", ""), error=mine.get("error"), rows=mine.get("rows"), cols=mine.get("cols"), map_note=mine.get("map_note")) if mine else None
    lim = dict(hosted=HOSTED, my_max_send=MY_MAX_SEND, my_max_mb=MY_MAX // 1024 // 1024)
    if req.query_params.get("src") == "mine":
        if not mine and req.query_params.get("src") == "mine": raise MineMissing()
        if not mine or mine.get("ds") is None:
            return dict(status=mine["status"] if mine else "empty", progress=mine.get("progress", "") if mine else "", error=mine.get("error") if mine else None, role=s["role"], src="mine", mine=my_info, privacy={k: OWN_CFG[k] for k in ("k", "min_cohort", "round_to", "num_min")}, sample_enabled=True, **lim)
        mine["t"] = time.time()
        ds = mine["ds"]
        base = dict(status=mine["status"], progress=mine.get("progress", ""), error=mine.get("error"), role=s["role"], src="mine", mine=my_info, map_note=mine.get("map_note"),
                    privacy={k: ds.cfg[k] for k in ("k", "min_cohort", "round_to", "num_min")}, sample_enabled=True, **lim)
    else:
        ds = state["ds"]
        base = dict(status=state["status"], progress=state["progress"], error=state["error"], role=s["role"], src="project", mine=my_info, privacy={k: CFG[k] for k in ("k", "min_cohort", "round_to", "num_min")}, sample_enabled=CFG["sample_enabled"], **lim)
    if ds is None: return base
    cols = [dict(name=c, label=ds.meta[c]["label"], kind=ds.meta[c]["kind"], group=ds.meta[c]["group"], unit=ds.meta[c]["unit"], fill=ds.meta[c]["fill"]) for c in ds.raw_cols if ds.explorable(c) and c not in ds.preferred]
    bases = [dict(key=k, label=v["label"], desc=v["desc"], best=v["best"], ks=sorted(v["labels"])) for k, v in ds.clusters.items()]
    sources = int(ds.df["pdf"].nunique()) if ds.domain and "pdf" in ds.df else None
    return dict(base, name=ds.name, n=ds.n, sources=sources, n_products=getattr(ds, "n_products", None), n_cols=sum(1 for c in ds.raw_cols if ds.visible(c)), dims=ds.dims_payload(), domain=ds.domain, primary=ds.primary, primary_label=ds.primary_label, columns=cols, bases=bases, version=ds.version)
@app.get("/api/overview")
def overview(req: Request, s=Depends(viewer)):
    ds = pick(req, s); return cached(ds, qkey(req), lambda: ds.overview(filt(req)))
@app.get("/api/quality")
def quality(req: Request, s=Depends(viewer)):
    ds = pick(req, s); return dict(items=ds.quality(), topic=ds.topic_match())
@app.get("/api/dictionary")
def dictionary(req: Request, s=Depends(viewer)):
    ds = pick(req, s); return cached(ds, qkey(req), lambda: ds.dictionary(filt(req)))
@app.get("/api/column/{name}")
def column(name: str, req: Request, s=Depends(viewer)):
    ds = pick(req, s); return cached(ds, qkey(req), lambda: ds.column(name, filt(req)))
@app.get("/api/completeness")
def completeness(req: Request, group: str | None = None, order: str = "similar", by: str | None = None, s=Depends(viewer)):
    ds = pick(req, s)
    if by and by not in dict(ds.dims): raise KeyError(by)
    return cached(ds, qkey(req), lambda: ds.completeness(filt(req), group, order, by))
@app.get("/api/explore")
def explore(req: Request, x: str, y: str | None = None, s=Depends(viewer)):
    ds = pick(req, s); return cached(ds, qkey(req), lambda: ds.explore(x, y or None, filt(req)))
@app.get("/api/compare")
def compare(req: Request, items: str, by: str | None = None, s=Depends(viewer)):
    ds = pick(req, s)
    if by and by not in dict(ds.dims): raise KeyError(by)
    return cached(ds, qkey(req), lambda: ds.compare(items.split("||"), by, filt(req)))
@app.get("/api/flow")
def flow(req: Request, dims: str = "", unspecified: bool = False, s=Depends(viewer)):
    ds = pick(req, s); return cached(ds, qkey(req), lambda: ds.flow(dims.split(",") if dims else None, filt(req), unspecified))
@app.get("/api/cooccurrence")
def cooc(req: Request, group: str | None = None, s=Depends(viewer)):
    ds = pick(req, s); return cached(ds, qkey(req), lambda: ds.cooccurrence(group or None, filt(req)))
@app.get("/api/correlation")
def corr(req: Request, s=Depends(viewer)):
    ds = pick(req, s); return cached(ds, qkey(req), lambda: ds.correlation(filt(req)))
@app.get("/api/map")
def amap(req: Request, basis: str = "terms_all", k: int = 0, color: str = "cluster", s=Depends(viewer)):
    ds = pick(req, s)
    if basis not in ds.clusters: raise HTTPException(409, "The map is not ready yet.")
    if color != "cluster" and color != "density" and color not in dict(ds.dims): raise ValueError("Invalid colour option.")
    def run():
        m, fl = ds.mask(filt(req))
        return cluster.hexes(ds, basis, k or ds.clusters[basis]["best"], color, m, fl)
    return cached(ds, qkey(req), run)
@app.get("/api/profile")
def profile(req: Request, by: str, value: str, s=Depends(viewer)):
    ds = pick(req, s); return cached(ds, qkey(req), lambda: ds.profile(by, value, filt(req)))
@app.get("/api/sample")
def sample(req: Request, s=Depends(viewer)):
    if req.query_params.get("src") == "mine":
        pick(req, s); smp = MY[s["sid"]].get("sample")
        if not smp: raise HTTPException(409, "There are no records to show.")
        return {k: v for k, v in smp.items() if k != "seed"}
    if not CFG["sample_enabled"]: raise HTTPException(403, "Sample records have been turned off by the admin.")
    smp = state.get("sample")
    if not smp: raise HTTPException(409, "The sample is not ready yet.")
    return {k: v for k, v in smp.items() if k not in ("seed", "ui", "version")}

@app.post("/api/mydata")
async def my_upload(req: Request, file: UploadFile = File(...), s=Depends(viewer)):
    limit("myup:" + s["sid"], 6, 600)
    fname = (file.filename or "").lower()
    packed = fname.endswith(".gz")
    if not fname.removesuffix(".gz").endswith((".csv", ".tsv", ".txt")): raise HTTPException(400, "Upload a CSV file.")
    raw = await file.read(MY_MAX + 1)
    if packed:
        try:
            d = gzip.GzipFile(fileobj=__import__("io").BytesIO(raw)); raw = d.read(MY_MAX + 1)
        except OSError:
            raise HTTPException(400, "The compressed file could not be read.")
    if len(raw) > MY_MAX: raise HTTPException(413, f"The file is larger than {MY_MAX // 1024 // 1024} MB.")
    _my_prune()
    entry = dict(name=os.path.basename(file.filename).removesuffix(".gz")[:80], status="building", progress="Reading the file", error=None, ds=None, t=time.time(), size=len(raw))
    with MY_LOCK: MY[s["sid"]] = entry
    if HOSTED:
        # Work after the response is not guaranteed here, so the file is analysed before answering.
        from starlette.concurrency import run_in_threadpool
        await run_in_threadpool(_my_build, entry, raw)
        if entry["status"] == "error": raise HTTPException(400, entry.get("error") or "The file could not be used.")
    else:
        threading.Thread(target=_my_build, args=(entry, raw), daemon=True).start()
    return dict(ok=True, status=entry["status"])
@app.delete("/api/mydata")
def my_delete(s=Depends(viewer)):
    with MY_LOCK: MY.pop(s["sid"], None)
    return dict(ok=True)

# ---- admin endpoints -------------------------------------------------------
@app.post("/admin/api/upload")
async def upload(req: Request, file: UploadFile = File(...), name: str = Form("Dataset"), s=Depends(admin)):
    if HOSTED: raise HTTPException(400, "This setting cannot be changed on the hosted version. Change the environment variables in the hosting dashboard, or update the data with prepare.py and deploy again.")
    raw = await file.read()
    if len(raw) > MAX_UPLOAD: raise HTTPException(413, "That file is too large.")
    if not (file.filename or "").lower().endswith((".csv", ".tsv", ".txt")): raise HTTPException(400, "Upload a CSV file.")
    try:
        engine.read_csv_robust(raw)
    except Exception as e:
        raise HTTPException(400, f"Could not read the CSV: {e}")
    tmp = CSV_PATH.with_suffix(".tmp"); tmp.write_bytes(raw); tmp.replace(CSV_PATH)
    try: os.chmod(CSV_PATH, 0o600)
    except OSError: pass
    CFG["dataset_name"] = name.strip()[:80] or "Dataset"; CFG["column_modes"] = {}; save_cfg()
    SAMPLE_PATH.unlink(missing_ok=True); state["sample"] = None; state["ds"] = None
    threading.Thread(target=build_dataset, args=(raw,), daemon=True).start()
    return dict(ok=True)
@app.get("/admin/api/config")
def get_config(s=Depends(admin)):
    ds = state["ds"]
    cols = [dict(name=c, kind=ds.meta[c]["kind"], group=ds.meta[c]["group"], mode=ds.col_mode(c), fill=ds.meta[c]["fill"]) for c in ds.raw_cols] if ds else []
    return dict(readonly=HOSTED, k=CFG["k"], min_cohort=CFG["min_cohort"], round_to=CFG["round_to"], num_min=CFG["num_min"], sample_n=CFG["sample_n"], sample_enabled=CFG["sample_enabled"],
                name=CFG["dataset_name"], columns=cols, status=state["status"], progress=state["progress"], error=state["error"], rows=ds.n if ds else 0, sample=state.get("sample") if ds else None)
@app.put("/admin/api/config")
async def put_config(req: Request, s=Depends(admin)):
    if HOSTED: raise HTTPException(400, "This setting cannot be changed on the hosted version. Change the environment variables in the hosting dashboard, or update the data with prepare.py and deploy again.")
    b = await req.json(); rebuild = False
    for key, lo, hi in (("k", 3, 100), ("min_cohort", 5, 1000), ("round_to", 1, 100), ("num_min", 5, 1000), ("sample_n", 0, 500)):
        if key in b:
            v = int(b[key])
            if not lo <= v <= hi: raise HTTPException(400, f"{key} must be between {lo} and {hi}.")
            rebuild |= key == "k" and v != CFG[key]
            CFG[key] = v
    if "sample_enabled" in b: CFG["sample_enabled"] = bool(b["sample_enabled"])
    if "name" in b: CFG["dataset_name"] = str(b["name"])[:80]
    if "column_modes" in b:
        cm = {c: m for c, m in b["column_modes"].items() if m in ("full", "stats", "hidden")}
        rebuild |= cm != CFG["column_modes"]; CFG["column_modes"] = cm
    save_cfg()
    ds = state["ds"]
    if ds: ds.name = CFG["dataset_name"]; ds.cache.clear()
    if rebuild and CSV_PATH.exists():
        SAMPLE_PATH.unlink(missing_ok=True); state["sample"] = None
        threading.Thread(target=build_dataset, daemon=True).start()
    return dict(ok=True, rebuilding=rebuild)
@app.post("/admin/api/resample")
def resample(s=Depends(admin)):
    if HOSTED: raise HTTPException(400, "This setting cannot be changed on the hosted version. Change the environment variables in the hosting dashboard, or update the data with prepare.py and deploy again.")
    ds = need(); _new_sample(ds); return dict(ok=True, n=state["sample"]["n"])
@app.post("/admin/api/codes")
async def codes(req: Request, s=Depends(admin)):
    if HOSTED: raise HTTPException(400, "This setting cannot be changed on the hosted version. Change the environment variables in the hosting dashboard, or update the data with prepare.py and deploy again.")
    b = await req.json()
    if b.get("viewer"):
        if len(b["viewer"]) < 6: raise HTTPException(400, "The code needs at least 6 characters.")
        CFG["viewer_hash"] = _hash(b["viewer"])
    if b.get("admin"):
        if len(b["admin"]) < 10: raise HTTPException(400, "The password needs at least 10 characters.")
        CFG["admin_hash"] = _hash(b["admin"])
    CFG["session_epoch"] += 1; save_cfg()
    return dict(ok=True, note="All sessions were signed out.")
@app.get("/admin/api/log")
def log(s=Depends(admin)):
    if not LOG_PATH.exists(): return dict(rows=[])
    lines = LOG_PATH.read_text("utf-8").splitlines()[-300:]
    return dict(rows=[json.loads(l) for l in reversed(lines) if l.strip()])

# ---- pages ----------------------------------------------------------------
@app.get("/")
def root(req: Request):
    return FileResponse(STATIC / "index.html") if session(req) else RedirectResponse("/login")
@app.get("/login")
def login_page(): return FileResponse(STATIC / "login.html")
@app.get("/admin")
def admin_page(req: Request):
    s = session(req)
    return FileResponse(STATIC / "admin.html") if s and s["role"] == "admin" else RedirectResponse("/login")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.add_middleware(CarryOwnFile)
