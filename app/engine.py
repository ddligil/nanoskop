"""All computation lives here: raw rows never leave this module.
The API layer only sees the aggregated dictionaries this class returns."""
import io, json, math, re, threading, time, hashlib
from pathlib import Path
import numpy as np, pandas as pd
from scipy.cluster.hierarchy import linkage, leaves_list
from scipy.spatial.distance import pdist
from . import profile_nanomedicine as P

NUM_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*$")
OTHER = "Small groups"

class CohortTooSmall(Exception):
    pass

def sig(x, n=3):
    if x is None or not np.isfinite(x): return None
    if x == 0: return 0.0
    return float(f"{x:.{n}g}")

def parse_num(s):
    """Turns '80-100' ranges into midpoints and everything else into numbers."""
    s = s.astype(object)
    def one(v):
        if not isinstance(v, str): return np.nan
        m = NUM_RE.match(v)
        if m: return (float(m[1]) + float(m[2])) / 2
        try: return float(v)
        except ValueError: return np.nan
    return s.map(one).astype(float)

def read_csv_robust(raw: bytes):
    for enc in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            text = raw.decode(enc); break
        except UnicodeDecodeError:
            continue
    head = text[:20000].split("\n")[0]
    sep = max([",", ";", "\t", "|"], key=head.count)
    df = pd.read_csv(io.StringIO(text), sep=sep, dtype=object, keep_default_na=True, na_values=["", "NA", "N/A", "nan", "NaN", "None", "null"], low_memory=False)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    if df.shape[0] < 10 or df.shape[1] < 2:
        raise ValueError("The CSV needs at least 10 rows and 2 columns.")
    if df.columns.duplicated().any():
        raise ValueError("The CSV has duplicate column names.")
    return df


class Dataset:
    def __init__(self, df: pd.DataFrame, cfg: dict, name="Veri seti"):
        self.cfg = cfg; self.name = name
        self.raw_cols = list(df.columns)
        self.domain = P.REQUIRED.issubset(df.columns)
        self.df = df.copy().reset_index(drop=True)
        self.n = len(df)
        self.version = hashlib.sha1(pd.util.hash_pandas_object(df.fillna(""), index=False).values.tobytes()).hexdigest()[:12]
        if self.domain: P.localize(self.df)
        self.nums = {}; self.invalid = {}; self.meta = {}
        self.preferred = P.PREFERRED if self.domain else {}
        self._classify()
        self._derive()
        self.cache = {}

    # ---- schema --------------------------------------------------------
    def _classify(self):
        groups = {}
        if self.domain:
            for g, cs in P.GROUPS.items():
                for c in cs: groups[c] = g
        for c in self.raw_cols:
            s = self.df[c].dropna()
            nn = len(s); uq = s.nunique()
            num = parse_num(s) if nn else pd.Series(dtype=float)
            nf = num.notna().mean() if nn else 0
            if nn and nf >= .5 and uq > 2: kind = "num"
            elif nn and (uq / nn > .7 and uq > 50 or re.search(r"(^|_)(id|pdf|doi|number)$|trial_number", c.lower()) and uq > 50): kind = "id"
            elif uq <= 40: kind = "cat"
            else: kind = "text"
            self.meta[c] = dict(name=c, kind=kind, group=groups.get(c, "Other fields" if self.domain else "All fields"), fill=nn, unique=uq,
                                label=P.label(c) if self.domain else c, unit=None, mixed=False)
            if kind == "num":
                v = parse_num(self.df[c])
                rule = P.VALID.get(c) if self.domain else None
                bad = pd.Series(False, index=v.index)
                if rule:
                    lo, hi, unit = rule
                    if lo is not None: bad |= v < lo
                    if hi is not None: bad |= v > hi
                    self.meta[c]["unit"] = unit
                self.invalid[c] = int(bad.sum())
                self.nums[c] = v.mask(bad)
                self.meta[c]["mixed"] = self.domain and c in P.MIXED_UNITS

    def _derive(self):
        df = self.df
        self.dims = []
        self.dim_order = {"_phase": P.PHASE_ORDER} if self.domain else {}
        if self.domain:
            for k, v in P.derive(df).items(): df[k] = v
            vc = df["drug_name"].value_counts()
            small = set(vc[vc < self.cfg["k"]].index)
            df["_product"] = df["drug_name"].where(~df["drug_name"].isin(small), OTHER)
            src = {"_product": "drug_name", "_class": "drug_name", "_platform": "drug_name", "_phase": "phase_norm", "_disease": "disease_any"}
            self.dims = [(k, l) for k, l in P.DIMS if self.col_mode(src[k]) == "full" and src[k] in self.meta]
            self.n_products = int(df["drug_name"].nunique())
            self.primary = self.dims[0][0] if self.dims else None
            self.primary_label = self.dims[0][1] if self.dims else None
            self.group_dim = "_class" if any(k == "_class" for k, _ in self.dims) else self.primary
        else:
            cands = [m for m in self.meta.values() if m["kind"] == "cat" and m["unique"] >= 2 and self.col_mode(m["name"]) == "full"]
            cands.sort(key=lambda m: -m["fill"])
            for m in cands[:5]:
                key = "_d_" + m["name"]
                vc = df[m["name"]].value_counts()
                small = set(vc[vc < self.cfg["k"]].index)
                df[key] = df[m["name"]].fillna("Not specified").where(lambda s: ~s.isin(small), OTHER)
                self.dims.append((key, m["name"]))
            if len(self.dims) < 3:
                nums = sorted((c for c in self.nums if self.col_mode(c) == "full"), key=lambda c: -self.meta[c]["fill"])
                for c in nums[: 3 - len(self.dims)]:
                    v = self.nums[c]
                    if v.notna().sum() < 4 * self.cfg["k"]: continue
                    q = np.unique(np.nanpercentile(v, [25, 50, 75]))
                    edges = [-np.inf, *q, np.inf]
                    names = []
                    for i in range(len(edges) - 1):
                        lo, hi = edges[i], edges[i + 1]
                        names.append(f"up to {sig(hi):g}" if lo == -np.inf else f"over {sig(lo):g}" if hi == np.inf else f"{sig(lo):g} to {sig(hi):g}")
                    key = "_b_" + c
                    cat = pd.cut(v, edges, labels=names, include_lowest=True).astype(object)
                    df[key] = cat.where(cat.notna(), "Not specified")
                    self.dims.append((key, f"{self.meta[c]['label']} range"))
                    self.dim_order[key] = names
            self.primary = self.dims[0][0] if self.dims else None
            self.primary_label = self.dims[0][1] if self.dims else None
            self.group_dim = self.primary

    def _rank(self, key, v):
        o = self.dim_order.get(key, [])
        return o.index(v) if v in o else len(o) + (1 if v in ("Not specified", OTHER) else 0)

    def _sort(self, key, items):
        if key in self.dim_order: items.sort(key=lambda i: self._rank(key, i["value"]))

    def col_mode(self, c):
        ov = self.cfg.get("column_modes", {}).get(c)
        if ov: return ov
        return "stats" if self.meta.get(c, {}).get("kind") == "id" else "full"

    def visible(self, c):
        return c in self.meta and self.col_mode(c) != "hidden"

    def explorable(self, c):
        return (c in self.meta and self.col_mode(c) == "full") or c in dict(self.dims)

    # ---- privacy -------------------------------------------------------
    def rc(self, n, filtered):
        """Hides small cells and rounds counts when a filter is active."""
        k = self.cfg["k"]
        if n < k: return None
        if filtered:
            r = self.cfg["round_to"]
            return int(max(k, r * round(n / r)))
        return int(n)

    def mask(self, f):
        if not f: return np.ones(self.n, bool), False
        m = np.ones(self.n, bool); valid = dict(self.dims)
        for k, vals in f.items():
            if k not in valid: raise ValueError("Invalid filter.")
            m &= self.df[k].isin(vals).values
        if m.sum() < self.cfg["min_cohort"]:
            raise CohortTooSmall()
        return m, True

    def tops(self, s, filtered, limit=12):
        vc = s.dropna().astype(str).str.strip().str.lower().value_counts()
        out = []
        for v, n in vc.head(limit * 2).items():
            c = self.rc(int(n), filtered)
            if c is None: continue
            out.append(dict(value=v[:70], n=c))
            if len(out) == limit: break
        return out

    def summarize(self, v, filtered):
        v = v[np.isfinite(v)]
        if len(v) < self.cfg["num_min"]:
            return dict(n=self.rc(len(v), filtered), suppressed=True)
        q = np.percentile(v, [5, 25, 50, 75, 95])
        return dict(n=self.rc(len(v), filtered), suppressed=False, p5=sig(q[0]), p25=sig(q[1]), p50=sig(q[2]), p75=sig(q[3]), p95=sig(q[4]))

    def hist(self, v, filtered, bins=26):
        v = v[np.isfinite(v)]
        if len(v) < self.cfg["num_min"]: return None
        lo, hi = np.percentile(v, [1, 99])
        if lo == hi: lo, hi = v.min(), v.max()
        if lo == hi: return None
        logx = lo > 0 and hi / max(np.median(v), 1e-12) > 6
        vv = np.log10(v) if logx else v
        a, b = (np.log10(lo), np.log10(hi)) if logx else (lo, hi)
        edges = np.linspace(a, b, bins + 1)
        inside = vv[(vv >= a) & (vv <= b)]
        cnt, _ = np.histogram(inside, edges)
        real = (10 ** edges) if logx else edges
        out = []
        for i, c in enumerate(cnt):
            out.append(dict(a=sig(float(real[i])), b=sig(float(real[i + 1])), n=self.rc(int(c), filtered), empty=int(c) == 0))
        return dict(log=bool(logx), bins=out, tails=self.rc(int(len(vv) - len(inside)), filtered))

    # ---- schema and coverage ---------------------------------------------
    def dims_payload(self):
        out = []
        for k, l in self.dims:
            vc = self.df[k].value_counts()
            items = [dict(value=v, n=int(n)) for v, n in vc.items() if n >= self.cfg["k"]]
            self._sort(k, items)
            out.append(dict(key=k, label=l, options=items))
        return out

    def dictionary(self, f=None):
        m, fl = self.mask(f); sub = self.df[m]; tot = int(m.sum()); out = []
        for c in self.raw_cols:
            if not self.visible(c): continue
            mt = self.meta[c]; nn = int(sub[c].notna().sum())
            item = dict(name=c, label=mt["label"], kind=mt["kind"], group=mt["group"], unit=mt["unit"], mixed=mt["mixed"],
                        mode=self.col_mode(c), fill_pct=None if nn < self.cfg["k"] else round(100 * nn / tot, 0 if fl else 1),
                        unique=None if (fl or mt["unique"] < self.cfg["k"]) else mt["unique"],
                        invalid=self.rc(self.invalid.get(c, 0), False) if not fl else None)
            if self.col_mode(c) == "full" and mt["kind"] == "num":
                item["summary"] = self.summarize(self.nums[c].values[m], fl)
            elif self.col_mode(c) == "full" and mt["kind"] in ("text", "cat"):
                item["top"] = self.tops(sub[c], fl, 3)
            out.append(item)
        return out

    def column(self, c, f=None):
        if not self.explorable(c): raise KeyError(c)
        m, fl = self.mask(f); sub = self.df[m]
        mt = self.meta.get(c, dict(kind="cat", label=dict(self.dims).get(c, c), unit=None, mixed=False, group=""))
        nn = int(sub[c].notna().sum()); tot = int(m.sum())
        out = dict(name=c, label=mt["label"], kind=mt["kind"], unit=mt["unit"], mixed=mt["mixed"], group=mt["group"],
                   filled=self.rc(nn, fl), total=self.rc(tot, fl), fill_pct=None if nn < self.cfg["k"] else round(100 * nn / tot, 0 if fl else 1))
        if mt["kind"] == "num":
            v = self.nums[c].values[m]
            out["summary"] = self.summarize(v, fl); out["hist"] = self.hist(v, fl)
            nonnum = sub[c].dropna().astype(str)
            pn = parse_num(nonnum)
            out["nonnumeric"] = self.rc(int(pn.isna().sum()), fl)
            out["invalid"] = None if fl else self.rc(self.invalid.get(c, 0), False)
        else:
            out["top"] = self.tops(sub[c], fl, 16)
        # which groups fill this field most
        if self.primary and c != self.primary:
            g = sub.groupby(self.primary, observed=True)[c].agg(lambda s: s.notna().mean())
            sz = sub.groupby(self.primary, observed=True)[c].size()
            rows = [dict(value=k, pct=round(100 * float(g[k]))) for k in g.index if sz[k] >= self.cfg["num_min"] and k != OTHER]
            rows.sort(key=lambda r: -r["pct"])
            out["by_primary"] = rows[:6]
        return out

    # ---- overview --------------------------------------------------------
    def overview(self, f=None):
        m, fl = self.mask(f); sub = self.df[m]; tot = int(m.sum())
        dims = {}
        for k, l in self.dims:
            vc = sub[k].value_counts()
            rows = [dict(value=v, n=self.rc(int(n), fl), small=False) for v, n in vc.items() if v != OTHER and n >= self.cfg["k"]]
            hidden = int(vc[(vc < self.cfg["k"]) | (vc.index == OTHER)].sum())
            if hidden >= self.cfg["k"]: rows.append(dict(value=OTHER, n=self.rc(hidden, fl), small=True))
            self._sort(k, rows)
            dims[k] = dict(label=l, rows=rows)
        tree = []
        keys = dict(self.dims)
        if "_class" in keys and "_product" in keys:
            for cl, g in sub.groupby("_class", observed=True):
                if len(g) < self.cfg["k"]: continue
                ch = [dict(name=p, value=self.rc(int(n), fl)) for p, n in g["_product"].value_counts().items() if n >= self.cfg["k"]]
                tree.append(dict(name=cl, value=self.rc(len(g), fl), children=ch))
            tree.sort(key=lambda x: -x["value"])
        nn = sub[self.raw_cols].notna().sum(axis=1).values
        vis = [c for c in self.raw_cols if self.col_mode(c) != "hidden"]
        fills = sub[vis].notna().mean() * 100
        out = dict(n=self.rc(tot, fl), total=self.n, share=round(100 * tot / self.n), filtered=fl, n_cols=len(vis),
                   numeric=sum(self.meta[c]["kind"] == "num" for c in vis), dims=dims, tree=tree,
                   median_filled=int(np.median(nn)), mean_fill=round(float(fills.mean())),
                   over50=int((fills >= 50).sum()), under10=int((fills < 10).sum()),
                   groups=self._group_fill(sub, vis), insights=self._insights(sub, fl))
        return out

    def _group_fill(self, sub, vis):
        g = {}
        for c in vis: g.setdefault(self.meta[c]["group"], []).append(c)
        rows = [dict(group=k, n_cols=len(v), fill=round(float(sub[v].notna().mean().mean() * 100))) for k, v in g.items()]
        return sorted(rows, key=lambda r: -r["fill"])

    def _insights(self, sub, fl):
        out = []
        if not self.primary: return out
        vc = sub[self.primary].value_counts(normalize=True)
        if len(vc) >= 2:
            out.append(f"About {round(100 * vc.iloc[:2].sum())}% of records belong to two groups: {vc.index[0]} and {vc.index[1]}.")
        if self.domain:
            if "_phase" in dict(self.dims):
                ph = (sub["_phase"] != "Not specified").mean()
                out.append(f"About {round(100 * ph)}% of records state a clinical phase.")
            ps = self.nums["particle_size_clean"].values[sub.index] if self.col_mode("particle_size_clean") == "full" else np.array([])
            ps = ps[np.isfinite(ps)]
            if len(ps) >= self.cfg["num_min"]:
                a, b, c = np.percentile(ps, [25, 50, 75])
                out.append(f"The median particle size is {sig(b, 2):g} nm; the middle half lies between {sig(a, 2):g} and {sig(c, 2):g} nm.")
        return out

    def quality(self):
        items = []
        dup = int(self.df[self.raw_cols].duplicated().sum())
        items.append(dict(title="Exact duplicate rows", value=f"{dup:,}", note="Not removed, so that row counts match the CSV exactly."))
        if self.domain and "pdf" in self.df:
            d2 = int(self.df.duplicated(["drug_name", "pdf"]).sum())
            items.append(dict(title="Extra records for the same source and product", value=f"{d2:,}", note="A row is a record extracted for one source and product pair, not a patient or a study arm."))
        badc = sorted(((k, v) for k, v in self.invalid.items() if v and self.visible(k)), key=lambda x: -x[1])
        if badc:
            tot = sum(v for _, v in badc)
            items.append(dict(title="Numbers outside the valid range", value=f"{tot:,}", note="Excluded from distributions. Most common in: " + ", ".join(self.meta[k]["label"] for k, _ in badc[:3]) + "."))
        if self.domain:
            items.append(dict(title="Numeric fields without recorded units", value=str(sum(1 for m in self.meta.values() if m["mixed"])), note="Half-life, clearance and similar fields may mix units, so read their distributions as approximate."))
            uq = int(self.df["api_norm"].nunique())
            items.append(dict(title="Active ingredient spellings", value=f"{uq} variants", note="The same ingredient can appear under several spellings (vcr and vincristine, for example). Compare by product or drug class instead."))
        return items

    def topic_match(self):
        """Per product: does any cell in the row mention the product or active ingredient?"""
        if not self.domain: return []
        if "topic" in self.cache: return self.cache["topic"]
        txt_cols = [c for c in self.raw_cols if c not in ("drug_name", "pdf", "api_norm", "active_pharmaceutical_ingredient") and self.meta[c]["kind"] != "num"]
        api_cols = [c for c in ("active_pharmaceutical_ingredient", "api_norm", "payload") if c in self.df]
        all_txt = self.df[txt_cols + [c for c in api_cols if c not in txt_cols]].fillna("").astype(str).agg(" ".join, axis=1).str.lower()
        out = []
        for d, (cl, pl, pat) in P.PRODUCTS.items():
            idx = self.df["drug_name"] == d
            if idx.sum() < max(30, self.cfg["k"]): continue
            out.append(dict(product=d, n=int(idx.sum()), pct=round(100 * float(all_txt[idx].str.contains(pat, regex=True).mean()))))
        out.sort(key=lambda r: r["pct"])
        self.cache["topic"] = out
        return out

    # ---- coverage matrix ---------------------------------------------
    def completeness(self, f=None, group=None, order="size", by=None):
        """Coverage table: rows are groups, columns are information types (or the fields of one type)."""
        by = by or self.primary
        if not by: raise ValueError("There is no grouping field to compare.")
        m, fl = self.mask(f); sub = self.df[m]
        vis = [c for c in self.raw_cols if self.visible(c)]
        vc = sub[by].value_counts()
        rows = [r for r in vc.index if vc[r] >= max(self.cfg["min_cohort"], self.cfg["k"]) and r != OTHER]
        groups = {}
        for c in vis: groups.setdefault(self.meta[c]["group"], []).append(c)
        filled = sub[vis].notna()
        g_rows = {r: filled[(sub[by] == r).values] for r in rows}
        if group and group in groups:
            keys = sorted(groups[group], key=lambda c: -filled[c].mean())
            cols = [dict(key=c, label=self.meta[c]["label"], kind=self.meta[c]["kind"]) for c in keys]
            val = lambda fr: [float(fr[c].mean()) for c in keys]
        else:
            group = None
            keys = sorted(groups, key=lambda g: -filled[groups[g]].mean().mean())
            cols = [dict(key=g, label=g, n_fields=len(groups[g])) for g in keys]
            val = lambda fr: [float(fr[groups[g]].mean().mean()) for g in keys]
        mat = {r: val(g_rows[r]) for r in rows}
        if order == "name": rows = sorted(rows, key=str.lower)
        elif order == "coverage": rows = sorted(rows, key=lambda r: -float(np.mean(mat[r])))
        elif order == "similar" and len(rows) >= 3:
            fp = np.array([g_rows[r].mean().values for r in rows])
            idx = leaves_list(linkage(pdist(fp + 1e-9, metric="cosine"), "average")).tolist()
            rows = [rows[i] for i in idx]
        dg = 0 if fl else 1
        return dict(by=by, by_label=dict(self.dims).get(by, by), group=group, groups=[dict(name=g, n_fields=len(groups[g])) for g in sorted(groups)],
                    cols=cols, all=[round(100 * v, dg) for v in val(filled)], n_all=self.rc(len(sub), fl),
                    rows=[dict(name=r, n=self.rc(int(vc[r]), fl), values=[round(100 * v, dg) for v in mat[r]]) for r in rows])

    def _kind(self, c):
        if c in dict(self.dims): return "cat"
        return self.meta[c]["kind"]

    def explore(self, x, y=None, f=None):
        for c in (x, y):
            if c and not self.explorable(c): raise KeyError(c)
        m, fl = self.mask(f); sub = self.df[m]
        x = self.preferred.get(x, x); y = self.preferred.get(y, y) if y else y
        kx, ky = self._kind(x), self._kind(y) if y else None
        lab = lambda c: dict(self.dims).get(c) or self.meta[c]["label"]
        unit = lambda c: self.meta.get(c, {}).get("unit")
        base = dict(x=x, y=y, xlabel=lab(x), ylabel=lab(y) if y else None, xunit=unit(x), yunit=unit(y) if y else None,
                    mixed=any(self.meta.get(c, {}).get("mixed") for c in (x, y) if c))
        if not y:
            if kx == "num":
                v = self.nums[x].values[m]
                return dict(base, view="hist", summary=self.summarize(v, fl), hist=self.hist(v, fl))
            return dict(base, view="bars", top=self.tops(sub[x], fl, 20), filled=self.rc(int(sub[x].notna().sum()), fl))
        if kx != "num" and ky == "num": x, y, kx, ky = y, x, ky, kx; base.update(x=x, y=y, xlabel=lab(x), ylabel=lab(y), xunit=unit(x), yunit=unit(y))
        if kx == "num" and ky == "num": return dict(base, view="grid", **self._grid2d(x, y, m, fl))
        if kx == "num":
            return dict(base, view="box", groups=self._box(sub, y, self.nums[x].values[m], fl))
        return dict(base, view="cross", **self._cross(sub, x, y, fl))

    def _axis(self, v):
        lo, hi = np.percentile(v, [1, 99])
        lg = lo > 0 and hi / max(np.median(v), 1e-12) > 6
        return (float(lo), float(hi), bool(lg))

    def _grid2d(self, x, y, m, fl):
        a, b = self.nums[x].values[m], self.nums[y].values[m]
        ok = np.isfinite(a) & np.isfinite(b); a, b = a[ok], b[ok]
        n = int(np.clip(np.sqrt(len(a)) * .7, 8, 26))
        if len(a) < self.cfg["min_cohort"]:
            return dict(cells=[], n=self.rc(len(a), fl), rho=None, too_few=True)
        lx, hx, gx = self._axis(a); ly, hy, gy = self._axis(b)
        tr = lambda v, g: np.log10(v) if g else v
        ex = np.linspace(tr(lx, gx), tr(hx, gx), n + 1); ey = np.linspace(tr(ly, gy), tr(hy, gy), n + 1)
        ax, by = (np.log10(a) if gx else a), (np.log10(b) if gy else b)
        H, _, _ = np.histogram2d(ax, by, [ex, ey])
        cells = [[int(i), int(j), self.rc(int(H[i, j]), fl)] for i, j in zip(*np.nonzero(H >= self.cfg["k"]))]
        unshown = int(H[H < self.cfg["k"]].sum())
        from scipy.stats import spearmanr
        rho = spearmanr(a, b).statistic if len(a) >= 30 else None
        fmt = lambda e, g: [sig(float(10 ** q if g else q)) for q in e]
        return dict(cells=cells, xe=fmt(ex, gx), ye=fmt(ey, gy), xlog=gx, ylog=gy, n=self.rc(len(a), fl),
                    rho=sig(float(rho), 2) if rho is not None else None, hidden_points=self.rc(unshown, fl) if unshown >= self.cfg["k"] else None, too_few=False)

    def _box(self, sub, g, vals, fl):
        col = sub[g].astype(object).where(sub[g].notna())
        norm = col.astype(str).str.strip().where(col.notna())
        if g not in dict(self.dims): norm = norm.str.lower()
        rows = []
        for key, ix in norm.groupby(norm, observed=True).groups.items():
            pos = sub.index.get_indexer(ix); v = vals[pos]; v = v[np.isfinite(v)]
            if len(v) < self.cfg["num_min"] or key == OTHER: continue
            q = np.percentile(v, [5, 25, 50, 75, 95])
            rows.append(dict(group=str(key)[:40], n=self.rc(len(v), fl), q=[sig(float(i)) for i in q]))
        rows.sort(key=lambda r: -r["q"][2])
        return rows[:16]

    def _cross(self, sub, x, y, fl, top=12):
        nz = lambda s: s.astype(object).where(s.notna()).map(lambda v: v.strip().lower()[:40] if isinstance(v, str) else v) if s.name not in dict(self.dims) else s
        a, b = nz(sub[x]), nz(sub[y])
        ok = a.notna() & b.notna(); a, b = a[ok], b[ok]
        ta = [v for v in a.value_counts().index if v != OTHER][:top]; tb = [v for v in b.value_counts().index if v != OTHER][:top]
        if x in self.dim_order: ta.sort(key=lambda v: self._rank(x, v))
        if y in self.dim_order: tb.sort(key=lambda v: self._rank(y, v))
        ct = pd.crosstab(a, b).reindex(index=ta, columns=tb).fillna(0).astype(int)
        cells = []
        for i, r in enumerate(ct.values):
            tot = r.sum()
            for j, v in enumerate(r):
                if v >= self.cfg["k"]: cells.append([j, i, self.rc(int(v), fl), round(100 * v / max(tot, 1))])
        return dict(rows=[str(v) for v in ta], cols=[str(v) for v in tb], cells=cells, n=self.rc(int(ok.sum()), fl))

    # ---- comparison --------------------------------------------------------
    def compare(self, items, by=None, f=None):
        by = by or self.primary
        items = [i for i in items if i != OTHER][:4]
        base, fl0 = self.mask(f)
        res = []
        numeric = self._key_numeric()
        for it in items:
            m = base & (self.df[by] == it).values
            if m.sum() < self.cfg["min_cohort"]:
                res.append(dict(name=it, too_small=True)); continue
            sub = self.df[m]; fl = fl0
            d = dict(name=it, n=self.rc(int(m.sum()), fl), too_small=False)
            if self.domain and "_class" in dict(self.dims):
                d["cls"] = sub["_class"].mode().iat[0]; d["platform"] = sub["_platform"].mode().iat[0]
                d["api"] = sub["api_norm"].mode().iat[0] if sub["api_norm"].notna().any() else None
            d["dims"] = {}
            for k, l in self.dims:
                if k == by: continue
                vc = sub[k].value_counts()
                tot = len(sub); rows = [dict(value=v, pct=round(100 * n / tot), n=self.rc(int(n), fl)) for v, n in vc.items() if n >= self.cfg["k"]]
                d["dims"][k] = rows[:8]
            d["num"] = {c: self.summarize(self.nums[c].values[m], fl) for c in numeric}
            d["tops"] = {c: self.tops(sub[c], fl, 6) for c in self._key_text()}
            d["groups"] = self._group_fill(sub, [c for c in self.raw_cols if self.visible(c)])
            res.append(d)
        return dict(items=res, numeric=[dict(key=c, label=self.meta[c]["label"], unit=self.meta[c]["unit"], mixed=self.meta[c]["mixed"]) for c in numeric],
                    text=[dict(key=c, label=self.meta[c]["label"]) for c in self._key_text()], dims=[dict(key=k, label=l) for k, l in self.dims if k != by])

    def _key_numeric(self):
        order = ["particle_size_clean", "zeta_potential", "polydispersity", "dose_mg_per_kg_clean", "dose_mg_per_m2", "number_of_patients_clean", "half_life", "clinical_follow_up_period"] if self.domain else []
        cs = [c for c in order if c in self.nums and self.col_mode(c) == "full"]
        if not cs:
            cs = sorted((c for c in self.nums if self.col_mode(c) == "full"), key=lambda c: -self.meta[c]["fill"])[:8]
        return cs

    def _key_text(self):
        order = ["cell_line", "adverse_reactions", "excipient"] if self.domain else []
        cs = [c for c in order if c in self.meta and self.col_mode(c) == "full"]
        if not cs:
            cs = sorted((c for c, m in self.meta.items() if m["kind"] in ("text", "cat") and self.col_mode(c) == "full"), key=lambda c: -self.meta[c]["fill"])[:3]
        return cs

    # ---- relationships -----------------------------------------------------
    def flow(self, dims=None, f=None, include_unspecified=False):
        valid = dict(self.dims)
        dims = [d for d in (dims or []) if d in valid] or ([d for d in ("_platform", "_class", "_phase", "_disease") if d in valid] or list(valid)[:3])
        if len(dims) < 2: raise ValueError("Select at least two dimensions.")
        m, fl = self.mask(f); sub = self.df[m]
        nodes = {}; links = []
        for a, b in zip(dims, dims[1:]):
            s = sub[[a, b]]
            if not include_unspecified:
                s = s[(s[a] != "Not specified") & (s[b] != "Not specified")]
            for (x, y), n in s.groupby([a, b], observed=True).size().items():
                c = self.rc(int(n), fl)
                if c is None or OTHER in (x, y): continue
                sa = f"{valid[a]}§{x}"; sb = f"{valid[b]}§{y}"
                nodes[sa] = dict(name=sa, label=x, dim=valid[a], depth=dims.index(a))
                nodes[sb] = dict(name=sb, label=y, dim=valid[b], depth=dims.index(b))
                links.append(dict(source=sa, target=sb, value=c))
        return dict(nodes=list(nodes.values()), links=links, dims=[dict(key=d, label=valid[d]) for d in dims])

    def cooccurrence(self, group=None, f=None, limit=12):
        """Of the records that report field A (row), the share that also report field B (column)."""
        m, fl = self.mask(f); sub = self.df[m]
        dupes = P.RAW_DUPES if self.domain else set()
        vis = [c for c in self.raw_cols if self.visible(c) and self.col_mode(c) == "full" and c not in dupes and c not in self.preferred
               and not (self.domain and c in ("drug_name", "pdf"))]
        groups = sorted({self.meta[c]["group"] for c in vis})
        cs = [c for c in vis if (not group or self.meta[c]["group"] == group) and 0 < sub[c].notna().mean() < .99]
        cs = sorted(cs, key=lambda c: -sub[c].notna().sum())[:limit]
        X = sub[cs].notna().values.astype(float)
        N = max(len(sub), 1); n = X.sum(0); co = X.T @ X
        cells = []
        for i in range(len(cs)):
            for j in range(len(cs)):
                if i == j or n[i] < self.cfg["num_min"] or co[i, j] < self.cfg["k"]: continue
                cells.append([j, i, round(float(100 * co[i, j] / n[i])), self.rc(int(co[i, j]), fl)])
        return dict(cols=[self.meta[c]["label"] for c in cs], base=[round(float(100 * v / N)) for v in n], cells=cells, groups=groups, group=group)

    def correlation(self, f=None, limit=12):
        m, fl = self.mask(f)
        dupes = P.RAW_DUPES if self.domain else set()
        cs = [c for c in self.nums if self.col_mode(c) == "full" and c not in self.preferred and c not in dupes]
        cs = sorted(cs, key=lambda c: -np.isfinite(self.nums[c].values[m]).sum())[:limit]
        X = pd.DataFrame({c: self.nums[c].values[m] for c in cs})
        rho = X.corr(method="spearman", min_periods=30)
        ok = X.notna().astype(int).T @ X.notna().astype(int)
        cells = []
        for i, a in enumerate(cs):
            for j, b in enumerate(cs):
                if i == j or pd.isna(rho.loc[a, b]): continue
                cells.append([j, i, round(float(rho.loc[a, b]), 2), self.rc(int(ok.loc[a, b]), fl)])
        pairs = sorted(({"a": self.meta[cs[i]]["label"], "b": self.meta[cs[j]]["label"], "rho": v, "n": n, "mixed": self.meta[cs[i]]["mixed"] or self.meta[cs[j]]["mixed"]}
                        for j, i, v, n in cells if i < j), key=lambda r: -abs(r["rho"]))
        return dict(cols=[self.meta[c]["label"] for c in cs], cells=cells, top=pairs[:6])

    # ---- entity profile --------------------------------------------------
    def _terms(self):
        """Binary term matrix used for distinctive terms and similarity (cached, server side only)."""
        if hasattr(self, "_term_cache"): return self._term_cache
        from sklearn.feature_extraction.text import CountVectorizer
        from .cluster import TOKEN, STOP
        cols = [c for c in self.raw_cols if self.col_mode(c) == "full" and self.meta[c]["kind"] in ("text", "cat")]
        if not cols:
            self._term_cache = (None, None); return self._term_cache
        txt = self.df[cols].fillna("").astype(str).agg(" ".join, axis=1)
        cv = CountVectorizer(binary=True, min_df=max(self.cfg["k"], 5), max_df=.6, token_pattern=TOKEN, lowercase=True, stop_words=list(STOP), max_features=12000)
        try:
            X = cv.fit_transform(txt).tocsr()
            self._term_cache = (X, np.array(cv.get_feature_names_out()))
        except ValueError:
            self._term_cache = (None, None)
        return self._term_cache

    def _similar(self, by, value, limit=5):
        X, _ = self._terms()
        if X is None: return []
        key = "fp:" + by
        if key not in self.cache:
            vc = self.df[by].value_counts()
            names = [v for v, n in vc.items() if n >= self.cfg["min_cohort"] and v not in (OTHER, "Not specified")]
            fp = np.vstack([np.asarray(X[(self.df[by] == v).values].mean(0)).ravel() for v in names]) if names else np.zeros((0, 1))
            fp = fp / np.maximum(np.linalg.norm(fp, axis=1, keepdims=True), 1e-9) if names else fp
            self.cache[key] = (names, fp)
        names, fp = self.cache[key]
        if value not in names: return []
        s = fp @ fp[names.index(value)]
        order = [i for i in np.argsort(-s) if names[i] != value][:limit]
        return [dict(name=names[i], score=round(float(s[i]), 2)) for i in order]

    def profile(self, by, value, f=None):
        """Everything shown on the profile page for one group: aggregates only."""
        if by not in dict(self.dims): raise KeyError(by)
        base, fl = self.mask(f)
        m = base & (self.df[by] == value).values
        if value == OTHER or m.sum() < self.cfg["min_cohort"]: raise CohortTooSmall()
        k = self.cfg["k"]; sub = self.df[m]; allsub = self.df[base]; n = int(m.sum()); tot = int(base.sum())
        out = dict(by=by, by_label=dict(self.dims)[by], value=value, n=self.rc(n, fl), total=self.rc(tot, fl), share=round(100 * n / tot, 1), filtered=fl)
        sizes = allsub[by].value_counts()
        sizes = sizes[~sizes.index.isin([OTHER, "Not specified"])]
        out["rank"] = int(list(sizes.index).index(value) + 1) if value in sizes.index else None
        out["n_groups"] = int(len(sizes))
        if self.domain and "pdf" in self.df:
            out["sources"] = self.rc(int(sub["pdf"].nunique()), fl)
        if self.domain:
            if "_class" in sub: out["cls"] = sub["_class"].mode().iat[0]
            if "_platform" in sub: out["platform"] = sub["_platform"].mode().iat[0]
            if sub["api_norm"].notna().any() and self.col_mode("api_norm") == "full": out["api"] = sub["api_norm"].mode().iat[0]
            match = [t for t in self.topic_match() if t["product"] == value]
            if match and by == "_product": out["topic_pct"] = match[0]["pct"]
        # dimensions
        out["dims"] = {}
        for key, lab in self.dims:
            if key == by: continue
            vc = sub[key].value_counts(); va = allsub[key].value_counts()
            rows = [dict(value=v, n=self.rc(int(c), fl), pct=round(100 * c / n), all_pct=round(100 * va.get(v, 0) / tot)) for v, c in vc.items() if c >= k and v != OTHER]
            self._sort(key, rows)
            out["dims"][key] = dict(label=lab, rows=rows[:14])
        # coverage by information type
        vis = [c for c in self.raw_cols if self.visible(c)]
        ga = {g["group"]: g["fill"] for g in self._group_fill(allsub, vis)}
        out["coverage"] = [dict(group=g["group"], n_cols=g["n_cols"], fill=g["fill"], all=ga.get(g["group"])) for g in self._group_fill(sub, vis)]
        # measurements: histogram against all selected records on shared bins
        fields = []
        order = {c: i for i, c in enumerate(self._key_numeric())}
        for c in self.nums:
            if self.col_mode(c) != "full" or c in self.preferred: continue
            v = self.nums[c].values[m]; v = v[np.isfinite(v)]
            if len(v) < self.cfg["num_min"]: continue
            a = self.nums[c].values[base]; a = a[np.isfinite(a)]
            fields.append(dict(key=c, label=self.meta[c]["label"], unit=self.meta[c]["unit"], mixed=self.meta[c]["mixed"],
                               summary=self.summarize(v, fl), all_summary=self.summarize(a, fl), hist=self._shared_hist(v, a, fl), _o=order.get(c, 99), _n=len(v)))
        fields.sort(key=lambda d: (d.pop("_o"), -d.pop("_n")))
        out["measurements"] = fields
        # every field: how often this group reports it and its top values
        groups = {}
        for c in vis:
            mt = self.meta[c]; nn = int(sub[c].notna().sum()); na = int(allsub[c].notna().sum())
            pct = None if nn < k else round(100 * nn / n, 1); ap = round(100 * na / tot, 1) if na >= k else None
            row = dict(key=c, label=mt["label"], kind=mt["kind"], pct=pct, all_pct=ap, n=self.rc(nn, fl))
            if self.col_mode(c) == "full" and mt["kind"] in ("text", "cat"): row["top"] = self.tops(sub[c], fl, 6)
            groups.setdefault(mt["group"], []).append(row)
        out["fields"] = [dict(group=g, rows=sorted(r, key=lambda x: -(x["pct"] or 0))) for g, r in groups.items()]
        # distinctive terms
        X, names = self._terms()
        out["terms"] = []
        if X is not None:
            pg = np.asarray(X[m].mean(0)).ravel(); pa = np.asarray(X[base].mean(0)).ravel(); cg = np.asarray(X[m].sum(0)).ravel()
            ok = cg >= max(k, 5)
            score = (pg - pa) * np.log((pg + .005) / (pa + .005))
            score[~ok | (pg <= pa)] = -1
            for i in np.argsort(-score)[:24]:
                if score[i] <= 0: break
                out["terms"].append(dict(term=str(names[i]), pct=round(100 * float(pg[i])), all_pct=round(100 * float(pa[i]), 1)))
        out["similar"] = self._similar(by, value)
        # clusters
        clusters = getattr(self, "clusters", {})
        if clusters:
            key = "terms_all" if "terms_all" in clusters else next(iter(clusters))
            B = clusters[key]; best = B["best"]; idx = np.nonzero(B["keep"])[0]; lab = B["labels"][best]
            sel = m[idx]; cnt = np.bincount(lab[sel], minlength=best); kept = max(int(sel.sum()), 1); rows = []
            for i, c in enumerate(cnt):
                if c >= k: rows.append(dict(name=f"Cluster {i + 1}", id=i, pct=round(100 * int(c) / kept), terms=B["terms"][best][i][:5]))
            out["clusters"] = dict(basis=key, k=int(best), rows=sorted(rows, key=lambda r: -r["pct"]))
        return out

    def _shared_hist(self, v, a, fl, bins=22):
        lo, hi = np.percentile(a, [1, 99])
        if lo == hi: lo, hi = a.min(), a.max()
        if lo == hi: return None
        logx = lo > 0 and hi / max(np.median(a), 1e-12) > 6
        tr = (lambda z: np.log10(z)) if logx else (lambda z: z)
        e = np.linspace(tr(lo), tr(hi), bins + 1)
        cv, _ = np.histogram(tr(v[v > 0]) if logx else v, e); ca, _ = np.histogram(tr(a[a > 0]) if logx else a, e)
        real = 10 ** e if logx else e; rows = []
        for i in range(bins):
            n = self.rc(int(cv[i]), fl)
            rows.append(dict(a=sig(float(real[i])), b=sig(float(real[i + 1])), n=n, empty=int(cv[i]) == 0,
                             share=round(100 * int(cv[i]) / len(v), 1) if n is not None else None,
                             all_share=round(100 * int(ca[i]) / len(a), 1) if ca[i] >= self.cfg["k"] else None))
        return dict(log=bool(logx), bins=rows)

    # ---- sample records ------------------------------------------------
    def draw_sample(self, total=40, seed=None):
        seed = int(time.time()) if seed is None else seed
        rng = np.random.RandomState(seed)
        if self.domain:
            cols = [c for c in P.SAMPLE_COLUMNS if c in self.meta]
            gkey = "_class" if "_class" in dict(self.dims) else self.primary
        else:
            cols = [c for c in self.raw_cols if self.meta[c]["kind"] != "id"][:14]
            gkey = self.primary
        cols = [c for c in cols if self.col_mode(c) == "full"]
        valid_rows = np.ones(self.n, bool)
        for c, v in self.nums.items():
            valid_rows &= ~(self.df[c].notna().values & np.isnan(v.values) & parse_num(self.df[c]).notna().values)
        dfv = self.df[valid_rows & ~self.df[self.raw_cols].duplicated().values]
        filled = dfv[cols].notna().sum(axis=1)
        if gkey is None:
            pick = filled.sort_values(ascending=False).head(total * 5).sample(min(total, len(dfv)), random_state=rng).index
            groups = {"All": list(pick)}
        else:
            sizes = dfv[gkey].value_counts()
            sizes = sizes[(sizes >= self.cfg["k"]) & (sizes.index != OTHER)]
            alloc = {g: 1 for g in sizes.index} if total >= len(sizes) else {g: 1 for g in sizes.index[:total]}
            left = total - sum(alloc.values())
            weights = np.sqrt(sizes.reindex(alloc.keys()).values.astype(float))
            shares = weights / weights.sum() * left
            for g, s in zip(alloc, np.floor(shares)): alloc[g] += int(s)
            rem = total - sum(alloc.values())
            for g in sorted(alloc, key=lambda g: -sizes[g])[:rem]: alloc[g] += 1
            groups = {}
            for g, nn in alloc.items():
                idx = dfv.index[dfv[gkey] == g]; pool = filled.loc[idx]
                good = pool[pool >= pool.quantile(.85)].index
                # diversify the products in each group
                chosen = []
                if self.domain and gkey == "_class":
                    prods = dfv.loc[good, "drug_name"].value_counts().index.tolist()
                    while len(chosen) < nn and prods:
                        for p_ in list(prods):
                            cand = [i for i in good if dfv.at[i, "drug_name"] == p_ and i not in chosen]
                            if not cand: prods.remove(p_); continue
                            chosen.append(int(rng.choice(cand)))
                            if len(chosen) == nn: break
                else:
                    chosen = [int(i) for i in rng.choice(good, min(nn, len(good)), replace=False)]
                groups[g] = chosen
        rows = []
        for g, ids in groups.items():
            for i in ids:
                rec = {}
                for c in cols:
                    v = self.df.at[i, c]
                    if isinstance(v, str) and self.meta[c]["kind"] == "num":
                        pv = self.nums[c].iat[i]
                        rec[c] = None if np.isnan(pv) else sig(float(pv), 4)
                    else:
                        rec[c] = None if pd.isna(v) else str(v)[:80]
                rows.append(dict(group=str(g), values=rec))
        return dict(columns=[dict(key=c, label=self.meta[c]["label"], unit=self.meta[c]["unit"]) for c in cols], rows=rows,
                    seed=int(seed), n=len(rows), drawn_at=time.strftime("%Y-%m-%d"))
