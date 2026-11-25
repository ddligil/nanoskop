"""Clustering and the 2D map. Row coordinates stay on the server; only hexagon cells leave it."""
import numpy as np, warnings
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from . import profile_nanomedicine as P
warnings.filterwarnings("ignore")
TOKEN = r"[A-Za-zÀ-ÿğüşöçıİĞÜŞÖÇ][A-Za-zÀ-ÿğüşöçıİĞÜŞÖÇ0-9\-]{2,}"
STOP = {"the","and","with","for","from","patients","study","treatment","effect","effects","use","used","based","were","was","that","this","not","all","are","non"}
KS = list(range(3, 9))  # the colour palette is limited to 8 categories

def bases_for(ds):
    if ds.domain:
        return P.CLUSTER_BASES
    b = {"terms_all": {"label": "All terms", "desc": "Phrases in the text fields", "kind": "terms", "groups": None},
         "info_type": {"label": "Information type", "desc": "Which fields are filled", "kind": "presence", "groups": None}}
    if sum(1 for c in ds.nums if ds.col_mode(c) == "full" and ds.meta[c]["fill"] > .3 * ds.n) >= 3:
        b["numeric"] = {"label": "Numeric fields", "desc": "Rank scale of the numeric values", "kind": "numeric", "groups": None}
    return b

def _matrix(ds, spec):
    cols = [c for c in ds.raw_cols if ds.col_mode(c) == "full" and ds.meta[c]["kind"] != "id"
            and (not spec["groups"] or ds.meta[c]["group"] in spec["groups"])]
    if ds.domain:
        cols = [c for c in cols if c not in ("drug_name", "api_norm", "phase_norm", "np_type_norm", "disease_any", "active_pharmaceutical_ingredient")]
    if spec["kind"] == "presence":
        X = ds.df[cols].notna().astype(float).values
        keep = X.sum(1) >= 2
        return X, keep, cols, "presence"
    if spec["kind"] == "numeric":
        cs = [c for c in ds.nums if ds.col_mode(c) == "full" and ds.meta[c]["fill"] > .3 * ds.n]
        import pandas as pd
        R = pd.DataFrame({c: ds.nums[c].rank(pct=True) for c in cs}).fillna(.5).values
        return R, np.ones(len(R), bool), cs, "numeric"
    text_cols = [c for c in cols if ds.meta[c]["kind"] != "num"]
    if not text_cols: return None, None, None, None
    txt = ds.df[text_cols].fillna("").astype(str).agg(" ".join, axis=1)
    tf = TfidfVectorizer(min_df=max(ds.cfg["k"], 5), max_df=.5, sublinear_tf=True, token_pattern=TOKEN, lowercase=True, max_features=8000, stop_words=list(STOP))
    T = tf.fit_transform(txt)
    keep = np.asarray((T > 0).sum(1)).ravel() >= 2
    return T, keep, np.array(tf.get_feature_names_out()), "terms"

def _labels(X, labels, k, names, kind, meta):
    out = []
    for c in range(k):
        i = labels == c
        if kind == "terms":
            d = np.asarray(X[i].mean(0)).ravel() - np.asarray(X[~i].mean(0)).ravel()
            tt = [str(names[j]) for j in d.argsort()[::-1][:6]]
        else:
            d = X[i].mean(0) - X[~i].mean(0)
            tt = [meta[names[j]]["label"] for j in d.argsort()[::-1][:6]]
        out.append(tt)
    return out

def build(ds, progress=lambda s: None):
    """For each basis: 2D coordinates and labels for k=3..8."""
    import umap
    res = {}
    for key, spec in bases_for(ds).items():
        progress(f"{spec['label']}")
        try:
            one = _build_one(ds, spec, umap)
        except Exception as e:  # if one basis fails the others keep going
            print(f"[clustering] skipped {key}: {e}", flush=True)
            continue
        if one: res[key] = one
    return res

def _build_one(ds, spec, umap):
    if True:
        X, keep, names, kind = _matrix(ds, spec)
        if X is None or keep.sum() < 50: return None
        Xk = X[keep]
        dim = min(30, Xk.shape[1] - 1)
        Z = normalize(TruncatedSVD(dim, random_state=7).fit_transform(Xk))
        nn = min(30, max(5, len(Z) // 20))
        U = umap.UMAP(n_neighbors=nn, min_dist=.05, metric="cosine", random_state=7, low_memory=True, n_jobs=1).fit_transform(Z)
        sample = np.random.RandomState(1).choice(len(Z), min(3000, len(Z)), replace=False)
        labs = {}; sil = {}; terms = {}
        for k in KS:
            if k >= len(Z) // ds.cfg["k"]: continue
            km = KMeans(k, n_init=3, random_state=7).fit(Z)
            # largest first so colour order stays stable
            order = np.argsort(-np.bincount(km.labels_, minlength=k)); remap = np.argsort(order)
            l = remap[km.labels_]
            if len(np.unique(l[sample])) < 2: continue
            labs[k] = l.astype(np.int8)
            sil[k] = round(float(silhouette_score(Z[sample], l[sample])), 3)
            terms[k] = _labels(Xk, l, k, names, kind, ds.meta)
        if not sil: return None
        best = max(sil, key=sil.get)
        return dict(label=spec["label"], desc=spec["desc"], kind=kind, keep=keep, xy=U.astype(np.float32), labels=labs, sil=sil, terms=terms, best=int(best))

def hexes(ds, basis, k, color, mask, filtered, radius_scale=None):
    """Hexagon cells for the selected rows; cells below k are never sent."""
    B = ds.clusters[basis]; xy = B["xy"]
    k = int(k) if int(k) in B["labels"] else B["best"]
    idx = np.nonzero(B["keep"])[0]
    sel = mask[idx]
    xmin, ymin = xy.min(0); xmax, ymax = xy.max(0)
    span = max(xmax - xmin, ymax - ymin)
    # fewer records -> bigger hexagons, so small files still read as regions
    r = span / (radius_scale or float(np.clip(np.sqrt(len(idx)) * .85, 22, 92)))
    q, s = _axial(xy, r)
    labels = B["labels"][k]
    if color == "cluster":
        cat = labels.astype(object); names = [f"Cluster {i + 1}" for i in range(k)]; cat = np.array([names[i] for i in labels], dtype=object)
    elif color in dict(ds.dims):
        cat = ds.df[color].values[idx].astype(object)
        # Ordered over all data so colours stay the same when filters change.
        vc = {}
        for c in cat: vc[c] = vc.get(c, 0) + 1
        names = [n for n, _ in sorted(vc.items(), key=lambda x: -x[1]) if n not in (P.PHASE_ORDER[-1], "Small groups")][:7]
        ns = set(names)
        cat = np.array([c if c in ns else "Other" for c in cat], dtype=object)
        names = names + ["Other"]
    else:
        cat = None; names = []
    bins = {}
    for i in range(len(idx)):
        key = (int(q[i]), int(s[i]))
        b = bins.setdefault(key, dict(all=0, n=0, c={}))
        b["all"] += 1
        if sel[i]:
            b["n"] += 1
            if cat is not None: b["c"][cat[i]] = b["c"].get(cat[i], 0) + 1
    out = []; bg = []
    for (a, c), b in bins.items():
        x = r * (np.sqrt(3) * a + np.sqrt(3) / 2 * c) + xmin; y = r * 1.5 * c + ymin
        if b["n"] >= ds.cfg["k"]:
            comp = sorted(b["c"].items(), key=lambda z: -z[1])
            top = [dict(name=str(nm), n=ds.rc(int(v), filtered)) for nm, v in comp[:4] if v >= ds.cfg["k"]]
            dom = comp[0][0] if comp else None
            out.append(dict(x=round(float(x), 3), y=round(float(y), 3), n=ds.rc(b["n"], filtered), cat=dom,
                            share=round(comp[0][1] / b["n"], 2) if comp else 1, top=top))
        elif filtered and b["all"] >= ds.cfg["k"]:
            bg.append([round(float(x), 3), round(float(y), 3)])
    # without a filter small cells are not drawn as background either: only those above k
    counts = np.bincount(labels[sel], minlength=k) if sel.any() else np.zeros(k, int)
    clusters = []
    tot = max(int(sel.sum()), 1)
    # profile per cluster
    for c in range(k):
        i_c = (labels == c) & sel
        n = int(i_c.sum())
        ent = dict(id=c, name=f"Cluster {c + 1}", n=ds.rc(n, filtered), pct=round(100 * n / tot), terms=B["terms"][k][c] if n >= ds.cfg["k"] else [])
        if n >= ds.cfg["k"]:
            cx, cy = xy[i_c].mean(0)
            ent.update(cx=round(float(cx), 3), cy=round(float(cy), 3))
            rows = idx[i_c]
            for dk, _ in ds.dims[:5]:
                vc = ds.df[dk].iloc[rows].value_counts()
                ent.setdefault("dims", {})[dk] = [dict(value=v, pct=round(100 * m / n)) for v, m in vc.items() if m >= ds.cfg["k"] and v not in ("Not specified",)][:4]
        clusters.append(ent)
    return dict(basis=basis, k=k, r=round(float(r), 4), hex=out, bg=bg, names=names, color=color, clusters=clusters,
                silhouette=B["sil"][k], best=B["best"], sil=B["sil"], coverage=round(100 * float(B["keep"].mean())),
                extent=[float(xmin), float(xmax), float(ymin), float(ymax)])

def _axial(xy, r):
    x0 = xy[:, 0] - xy[:, 0].min(); y0 = xy[:, 1] - xy[:, 1].min()
    qf = (np.sqrt(3) / 3 * x0 - y0 / 3) / r; sf = (2 / 3 * y0) / r
    tf = -qf - sf
    q = np.round(qf); s = np.round(sf); t = np.round(tf)
    dq = np.abs(q - qf); ds_ = np.abs(s - sf); dt = np.abs(t - tf)
    m1 = (dq > ds_) & (dq > dt); q[m1] = (-s - t)[m1]
    m2 = ~m1 & (ds_ > dt); s[m2] = (-q - t)[m2]
    return q.astype(int), s.astype(int)
