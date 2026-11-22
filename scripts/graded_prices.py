"""Build prices/_graded.json (PSA graded prices) and grow prices/_graded_hist.json.

Two free sources, both credited in the app:
  1. PSA CardFacts (psacard.com/cardfacts) - mostly vintage cards, every grade with
     last sale, average sale and PSA population - via the public mirror at
     github.com/ShafFEAR/Pokemon-Card-API (refreshed monthly by its owner).
  2. "Pokemon Card Sold-Price Reference by Grade" (github.com/rrh1441/pokemon-card-sold-price-reference,
     CC-BY-4.0) - raw / PSA 9 / PSA 10 median eBay sold prices for ~486 mostly modern cards.

We keep our own copy, so the data survives if a source disappears, and a monthly
graded price history builds up over time. Standard library only.
"""
import csv, io, json, re, sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pricelib import OUT, SAFE_ID, get, load_catalog, log, norm_name, norm_num, CATALOG  # noqa: E402

CARDFACTS = "https://raw.githubusercontent.com/ShafFEAR/Pokemon-Card-API/main/data/psa-cardfacts/by-card-id.json"
SOLDREF = "https://raw.githubusercontent.com/rrh1441/pokemon-card-sold-price-reference/main/gemsnipe-card-sold-price-reference.csv"
VINTAGE_GRADES = ("7", "8", "9", "10")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def money(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, 2) if 0 < v < 50_000_000 else None


def count(x):
    try:
        v = int(float(x))
    except (TypeError, ValueError):
        return None
    return v if 0 <= v < 100_000_000 else None


def variant_label(desc, siblings):
    d = str(desc or "").lower()
    for pat, lab in ((r"1st\s*edition", "1st Edition"), (r"shadowless", "Shadowless"), (r"reverse", "Reverse Holo"),
                     (r"no symbol", "No Symbol"), (r"gold star", "Gold Star"), (r"\bhidden legends\b", "Hidden Legends")):
        if re.search(pat, d):
            return lab
    has_first = any(re.search(r"1st\s*edition", str(s.get("description", "")).lower()) for s in siblings)
    return "Unlimited" if has_first else "Holo" if "holo" in d else "Standard"


def clean_grades(g):
    """Pick one value per grade ("v") and flag sales that look mislabeled ("s").

    A last sale more than 4x away from the average is suspect (PSA's own pages mix in
    mislabeled listings), and so is a higher grade selling for under half a lower one.
    """
    for e in g.values():
        l, a = e.get("l"), e.get("a")
        if l and a and (l > 4 * a or l < a / 4):
            e["s"] = 1
            e["v"] = a
        else:
            e["v"] = l or a
    prev = None
    for k in VINTAGE_GRADES:
        e = g.get(k)
        if not e or not e.get("v"):
            continue
        if prev and e["v"] < prev * 0.5:
            alt = e.get("a") if e.get("a") and e.get("a") >= prev * 0.5 else None
            e["s"] = 1
            if alt:
                e["v"] = alt
            else:
                e.pop("v")
                continue
        prev = e["v"]


def from_cardfacts():
    raw = get(CARDFACTS) or {}
    out = {}
    for cid, variants in raw.items():
        if not SAFE_ID.match(str(cid)) or not isinstance(variants, list):
            continue
        vs = []
        for v in variants[:8]:
            grades = v.get("grades") if isinstance(v, dict) else None
            if not isinstance(grades, dict):
                continue
            total = sum(count((g or {}).get("population")) or 0 for g in grades.values() if isinstance(g, dict))
            g = {}
            for k in VINTAGE_GRADES:
                e = grades.get(k)
                if not isinstance(e, dict):
                    continue
                rec = {"l": money(e.get("mostRecent")), "a": money(e.get("average")), "p": count(e.get("population"))}
                d = e.get("mostRecentDate")
                if isinstance(d, str) and DATE.match(d):
                    rec["d"] = d
                if rec["l"] or rec["a"] or rec["p"]:
                    g[k] = {x: y for x, y in rec.items() if y is not None}
            if not g:
                continue
            clean_grades(g)
            p10 = (g.get("10") or {}).get("p") or 0
            entry = {"n": variant_label(v.get("description"), variants), "g": g, "src": "cf"}
            if total:
                entry["tot"] = total
                entry["gem"] = round(p10 / total, 4)
            vs.append(entry)
        if vs:
            # 1st Edition first, then Shadowless, then the rest
            order = {"1st Edition": 0, "Shadowless": 1, "Unlimited": 2, "Holo": 3}
            vs.sort(key=lambda e: order.get(e["n"], 5))
            out[cid] = vs
    log(f"CardFacts: {len(out)} cards")
    return out


def from_soldref(sets):
    data = get(SOLDREF, as_json=False)
    if not data:
        return {}
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8", "replace"))))
    by_name = {}
    for sid, s in sets.items():
        by_name.setdefault(norm_name(s.get("name")), []).append(sid)
    cache, out, miss = {}, {}, 0
    for r in rows:
        cands = by_name.get(norm_name(r.get("set_name")), [])
        num = norm_num(r.get("local_id"))
        cid = None
        for sid in cands:
            if sid not in cache:
                cache[sid] = {norm_num(c.get("number")): c["id"] for c in (get(CATALOG + f"cards/en/{sid}.json", pause=0) or [])
                              if SAFE_ID.match(str(c.get("id", "")))}
            cid = cache[sid].get(num)
            if cid:
                break
        if not cid:
            miss += 1
            continue
        m = {"raw": money(r.get("raw_price_usd")), "9": money(r.get("psa9_price_usd")), "10": money(r.get("psa10_price_usd")),
             "n9": count(r.get("psa9_sample_count")), "n10": count(r.get("psa10_sample_count"))}
        m = {k: v for k, v in m.items() if v is not None}
        if m.get("9") or m.get("10"):
            out[cid] = m
    log(f"Sold-price reference: {len(out)} cards matched, {miss} unmatched")
    return out


def main():
    sets = load_catalog()
    if not sets:
        sys.exit("catalog unavailable")
    cf = from_cardfacts()
    sr = from_soldref(sets)
    if not cf and not sr:
        sys.exit("no graded data fetched - keeping the old file")
    today = date.today().isoformat()
    cards = {}
    for cid, vs in cf.items():
        cards.setdefault(cid, {})["v"] = vs
    for cid, m in sr.items():
        cards.setdefault(cid, {})["m"] = m
    payload = {
        "updated": today,
        "sources": {
            "cf": {"name": "PSA CardFacts", "url": "https://www.psacard.com/cardfacts",
                   "via": "https://github.com/ShafFEAR/Pokemon-Card-API"},
            "m": {"name": "Pokémon Card Sold-Price Reference by Grade (eBay sold, CC-BY-4.0)",
                  "url": "https://github.com/rrh1441/pokemon-card-sold-price-reference", "asOf": "2026-09"},
        },
        "cards": cards,
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "_graded.json").write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True))

    # History: one point per card/variant/grade whenever the last sale changes. [date, last, avg]
    hp = OUT / "_graded_hist.json"
    try:
        hist = json.loads(hp.read_text())
    except Exception:
        hist = {}
    added = 0
    for cid, vs in cf.items():
        for v in vs:
            for g, e in v["g"].items():
                if not e.get("l") or e.get("s"):
                    continue
                key = f"{v['n']}|{g}"
                pts = hist.setdefault(cid, {}).setdefault(key, [])
                pt = [e.get("d") or today, e["l"], e.get("a")]
                if not pts or pts[-1][:2] != pt[:2]:
                    pts.append(pt)
                    added += 1
                del pts[:-60]
    for cid, m in sr.items():
        for g in ("9", "10"):
            if m.get(g):
                pts = hist.setdefault(cid, {}).setdefault(f"PSA|{g}", [])
                pt = [today, m[g], None]
                if not pts or pts[-1][1] != pt[1]:
                    pts.append(pt)
                    added += 1
                del pts[:-60]
    hp.write_text(json.dumps(hist, separators=(",", ":"), sort_keys=True))
    log(f"Wrote {len(cards)} graded cards, {added} new history points")


if __name__ == "__main__":
    main()
