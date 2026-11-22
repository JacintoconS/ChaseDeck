"""Shared helpers for ChaseDeck's price scripts.

- Which cards we track
- Matching TCGplayer products (via tcgcsv.com) to our card ids
- Reading/writing prices/<setId>.json and compacting old history

Standard library only.
"""
import json, os, re, sys, time, urllib.request, urllib.error, urllib.parse
from pathlib import Path

CATALOG = os.environ.get("CATALOG_BASE", "https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master/")
TCGCSV = os.environ.get("TCGCSV_BASE", "https://tcgcsv.com/")
POKEMON = 3  # TCGplayer category id for Pokémon
UA = "ChaseDeck price recorder (+https://github.com/JacintoconS/ChaseDeck)"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "prices"
DAILY_DAYS = int(os.environ.get("DAILY_DAYS", "180"))         # keep every day for this long, then one point per week
SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,40}$")

# Which cards to track: (series, rarities)
RULES = [
    ({"Scarlet & Violet", "Mega Evolution"},
     {"Illustration Rare", "Special Illustration Rare", "Hyper Rare", "Mega Hyper Rare", "Ultra Rare",
      "Shiny Rare", "Shiny Ultra Rare", "MEGA_ATTACK_RARE"}),
    ({"Sword & Shield"},
     {"Rare Ultra", "Rare Secret", "Rare Rainbow", "Trainer Gallery Rare Holo", "Rare Shiny", "Shiny Rare",
      "Rare Shiny GX", "Amazing Rare"}),
    ({"Sun & Moon", "XY", "Black & White"},
     {"Rare Secret", "Rare Rainbow", "Rare Ultra", "Rare Shiny GX", "Rare Shiny"}),
    ({"Base", "Gym", "Neo", "E-Card", "EX", "Other"},
     {"Rare Holo", "Rare Holo EX", "Rare Holo Star", "Rare Secret", "Rare Holo LV.X", "Rare Shining"}),
]
SUBSETS = ("trainer gallery", "galarian gallery", "shiny vault", "classic collection", "radiant collection")


def log(*a):
    print(*a, flush=True)


def get(url, tries=4, as_json=True, pause=0.15):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            time.sleep(pause)
            return json.loads(data) if as_json else data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if i == tries - 1:
                raise
            time.sleep(10 if e.code == 429 else 3 * (i + 1))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def results(payload):
    if isinstance(payload, dict):
        return payload.get("results") or []
    return payload if isinstance(payload, list) else []


def norm_num(n):
    n = str(n or "").split("/")[0].strip().lower()
    return re.sub(r"^0+(?=[a-z0-9])", "", n)


def norm_name(n):
    n = str(n or "").lower().replace("&", " and ").replace("pokémon", "pokemon")
    return re.sub(r"[^a-z0-9]", "", n)


GROUP_PREFIX = re.compile(r"^\s*(?:SV|SWSH|SM|XY|BW|ME|DP|HGSS|PL|EX|MEP|SVP|SWSHP|SMP)[0-9A-Za-z.]*\s*[:\-]\s*", re.I)


def group_core(name):
    return norm_name(GROUP_PREFIX.sub("", str(name or "")))


def subset_of(name):
    l = str(name or "").lower()
    return next((s for s in SUBSETS if s in l), "")


# ---------- catalog ----------
def load_catalog():
    sets = get(CATALOG + "sets/en.json") or []
    return {s["id"]: s for s in sets if SAFE_ID.match(str(s.get("id", "")))}


def pick_ids():
    out = set()
    try:
        picks = json.loads((ROOT / "picks.json").read_text())
        for p in (picks.get("picks") or []) + (picks.get("history") or []):
            if isinstance(p, dict) and SAFE_ID.match(str(p.get("id", ""))):
                out.add(p["id"])
    except Exception:
        pass
    return out


def tracked_cards(sets):
    """{set_id: [(card_id, number, name), ...]} for the cards worth tracking."""
    picks = pick_ids()
    tracked = {}
    for sid, s in sets.items():
        rar = set()
        for series, rs in RULES:
            if s.get("series") in series:
                rar |= rs
        want = {i for i in picks if i.rsplit("-", 1)[0] == sid}
        if not rar and not want:
            continue
        cards = get(CATALOG + f"cards/en/{sid}.json", pause=0) or []
        chosen = [(c["id"], c.get("number"), c.get("name", "")) for c in cards
                  if SAFE_ID.match(str(c.get("id", ""))) and (c.get("rarity") in rar or c["id"] in want)]
        if chosen:
            tracked[sid] = chosen
    return tracked


# ---------- tcgcsv mapping ----------
def match_groups(sets, groups):
    """Map our set ids to TCGplayer group ids. Returns ({set_id: group_id}, report)."""
    out, report = {}, {"matched": {}, "unmatched": []}
    by_code = {}
    for g in groups:
        by_code.setdefault(str(g.get("abbreviation") or "").upper(), []).append(g)
    for sid, s in sets.items():
        name, code, sub = s.get("name", ""), str(s.get("ptcgoCode") or "").upper(), subset_of(s.get("name"))
        cands = [g for g in by_code.get(code, []) if code] if code else []
        cands = [g for g in cands if subset_of(g.get("name")) == sub] or ([] if sub else cands)
        how = "code"
        if len(cands) != 1:
            target = norm_name(name)
            byname = [g for g in groups if group_core(g.get("name")) in (target, target + "set", norm_name("base set") if target == "base" else target)]
            if len(byname) == 1:
                cands, how = byname, "name"
            elif len(cands) > 1:
                exact = [g for g in cands if group_core(g.get("name")) == target]
                cands, how = (exact, "code+name") if len(exact) == 1 else ([], "")
            else:
                loose = [g for g in groups if target and len(target) > 3 and target in group_core(g.get("name")) and subset_of(g.get("name")) == sub]
                cands, how = (loose, "contains") if len(loose) == 1 else ([], "")
        if len(cands) == 1:
            out[sid] = int(cands[0]["groupId"])
            report["matched"][sid] = {"group": cands[0].get("name"), "how": how}
        else:
            report["unmatched"].append({"set": sid, "name": name, "code": code})
    return out, report


def product_number(p):
    for e in p.get("extendedData") or []:
        if e.get("name") == "Number":
            return norm_num(e.get("value"))
    return None


def match_products(cards, products):
    """cards: [(card_id, number, name)] -> {product_id: card_id}"""
    by_num = {}
    for p in products:
        n = product_number(p)
        if n:
            by_num.setdefault(n, []).append(p)
    out = {}
    for cid, number, name in cards:
        cands = by_num.get(norm_num(number), [])
        if not cands:
            continue
        nn = norm_name(name)
        cands = sorted(cands, key=lambda p: (
            0 if norm_name(re.sub(r"\s*-\s*\S+/\S+.*$", "", p.get("name", ""))) == nn else 1,
            1 if "(" in str(p.get("name", "")) else 0,
            int(p.get("productId", 0))))
        out[int(cands[0]["productId"])] = cid
    return out


def build_map(sets, tracked):
    groups = results(get(TCGCSV + f"tcgplayer/{POKEMON}/groups"))
    gmap, report = match_groups({sid: sets[sid] for sid in tracked}, groups)
    mapping = {}  # group_id -> {product_id: card_id}
    total = matched = 0
    for sid, gid in gmap.items():
        products = results(get(TCGCSV + f"tcgplayer/{POKEMON}/{gid}/products"))
        pm = match_products(tracked[sid], products)
        mapping[str(gid)] = {str(k): v for k, v in pm.items()}
        total += len(tracked[sid]); matched += len(pm)
        report["matched"][sid]["cards"] = f"{len(pm)}/{len(tracked[sid])}"
    for sid in tracked:
        if sid not in gmap:
            total += len(tracked[sid])
    report["summary"] = {"tracked_cards": sum(len(v) for v in tracked.values()), "mapped_cards": matched,
                         "sets": len(tracked), "sets_matched": len(gmap)}
    return mapping, report


def best_price(rows):
    """rows: price rows for one product -> highest market price across printings."""
    best = None
    for r in rows:
        for k in ("marketPrice", "midPrice"):
            v = r.get(k)
            if isinstance(v, (int, float)) and 0 < v < 1e7:
                best = v if best is None or v > best else best
                break
    return round(best, 2) if best is not None else None


def prices_from_rows(rows, pmap):
    """price rows of one group + {product_id: card_id} -> {card_id: price}"""
    per = {}
    for r in rows:
        cid = pmap.get(str(r.get("productId")))
        if cid:
            per.setdefault(cid, []).append(r)
    out = {}
    for cid, rs in per.items():
        p = best_price(rs)
        if p is not None:
            out[cid] = p
    return out


# ---------- history files ----------
def compact(points, today):
    """Keep every day for DAILY_DAYS, then the last point of each week."""
    pts = sorted({d: v for d, v in points}.items())
    recent = [[d, v] for d, v in pts if d > today - DAILY_DAYS]
    weekly = {}
    for d, v in pts:
        if d <= today - DAILY_DAYS:
            weekly[d // 7] = [d, v]
    return [weekly[k] for k in sorted(weekly)] + recent


def write_history(new_points, today, replace=False):
    """new_points: {card_id: {day: price}}. Merges into prices/<set>.json."""
    OUT.mkdir(exist_ok=True)
    by_set = {}
    for cid, pts in new_points.items():
        by_set.setdefault(cid.rsplit("-", 1)[0], {})[cid] = pts
    for sid, cards_new in by_set.items():
        path = OUT / f"{sid}.json"
        try:
            data = json.loads(path.read_text()) if not replace else {}
        except Exception:
            data = {}
        cards = data.get("cards") if isinstance(data.get("cards"), dict) else {}
        for cid, pts in cards_new.items():
            old = {d: v for d, v in cards.get(cid, []) if isinstance(d, int)}
            old.update(pts)
            cards[cid] = compact(list(old.items()), today)
        path.write_text(json.dumps({"set": sid, "updated": today, "cards": cards}, separators=(",", ":")))
    files = sorted(p.stem for p in OUT.glob("*.json") if not p.stem.startswith("_") and p.stem != "index")
    (OUT / "index.json").write_text(json.dumps({"updated": today, "sets": files}, separators=(",", ":")))
