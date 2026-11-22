#!/usr/bin/env python3
"""ChaseDeck daily price recorder.

Runs once a day on GitHub Actions. Picks the cards worth tracking from the open
Pokémon TCG catalog, looks up each card's TCGplayer market price (USD) on TCGdex,
and appends today's price to prices/<setId>.json. The app reads these files to
draw price history charts and compute market signals.

Standard library only, so the workflow needs no installs.
"""
import json, os, re, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CATALOG = os.environ.get("CATALOG_BASE", "https://raw.githubusercontent.com/PokemonTCG/pokemon-tcg-data/master/")
TCGDEX = os.environ.get("TCGDEX_BASE", "https://api.tcgdex.net/v2/en/")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "prices"
MAX_POINTS = 730          # about two years of daily prices per card
WORKERS = 6
UA = "ChaseDeck price recorder (+https://github.com/JacintoconS/ChaseDeck)"

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
SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,40}$")


def get_json(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if i == tries - 1:
                raise
        except Exception:
            if i == tries - 1:
                raise
        time.sleep(2 * (i + 1))


def norm_name(n):
    return re.sub(r"[^a-z0-9]", "", str(n or "").lower().replace("&", "and"))


def norm_num(n):
    return re.sub(r"^0+(?=[a-z0-9])", "", str(n or "").lower())


def guess_dex_id(set_id):
    g = re.sub(r"^(sv|me)(\d)(?=\D|$)", lambda m: m.group(1) + "0" + m.group(2), set_id)
    return re.sub(r"pt5$", ".5", g)


def best_price(pricing):
    """Highest TCGplayer market price across print variants (same rule as the app)."""
    tp = (pricing or {}).get("tcgplayer")
    if not isinstance(tp, dict):
        return None
    best = None
    for v in tp.values():
        if not isinstance(v, dict):
            continue
        for k in ("marketPrice", "midPrice", "lowPrice"):
            x = v.get(k)
            if isinstance(x, (int, float)) and 0 < x < 1e7:
                best = x if best is None or x > best else best
                break
    return round(best, 2) if best is not None else None


def main():
    today = int(time.time() // 86400)
    sets = get_json(CATALOG + "sets/en.json") or []
    set_by_id = {s["id"]: s for s in sets if SAFE_ID.match(s.get("id", ""))}

    pick_ids = set()
    try:
        picks = json.loads((ROOT / "picks.json").read_text())
        for p in (picks.get("picks") or []) + (picks.get("history") or []):
            if isinstance(p, dict) and SAFE_ID.match(str(p.get("id", ""))):
                pick_ids.add(p["id"])
    except Exception:
        pass

    # 1. choose cards
    tracked = {}  # set_id -> list of (card_id, number)
    for sid, s in set_by_id.items():
        rarities = set()
        for series, rs in RULES:
            if s.get("series") in series:
                rarities |= rs
        wanted_picks = {i for i in pick_ids if i.rsplit("-", 1)[0] == sid}
        if not rarities and not wanted_picks:
            continue
        cards = get_json(CATALOG + f"cards/en/{sid}.json") or []
        chosen = [(c["id"], c.get("number")) for c in cards
                  if SAFE_ID.match(c.get("id", "")) and (c.get("rarity") in rarities or c["id"] in wanted_picks)]
        if chosen:
            tracked[sid] = chosen
    total = sum(len(v) for v in tracked.values())
    print(f"Tracking {total} cards in {len(tracked)} sets")

    # 2. map catalog sets to TCGdex sets, and card numbers to TCGdex card ids
    dex_sets = [d for d in (get_json(TCGDEX + "sets") or []) if isinstance(d, dict) and d.get("id")]
    dex_ids = {d["id"] for d in dex_sets}

    def dex_set_for(sid):
        name = norm_name(set_by_id[sid].get("name"))
        by_name = [d["id"] for d in dex_sets if norm_name(d.get("name")) == name]
        if len(by_name) == 1:
            return by_name[0]
        for g in (guess_dex_id(sid), sid):
            if g in dex_ids:
                return g
        return by_name[0] if by_name else None

    jobs = []  # (set_id, card_id, dex_card_id)
    for sid, cards in tracked.items():
        dsid = dex_set_for(sid)
        if not dsid:
            continue
        detail = get_json(TCGDEX + "sets/" + urllib.parse.quote(dsid)) or {}
        by_num = {norm_num(c.get("localId")): c.get("id") for c in detail.get("cards") or [] if isinstance(c, dict)}
        for cid, number in cards:
            dcid = by_num.get(norm_num(number))
            if dcid:
                jobs.append((sid, cid, dcid))
    print(f"Matched {len(jobs)} of {total} cards on TCGdex")

    # 3. fetch prices
    def fetch(job):
        sid, cid, dcid = job
        try:
            d = get_json(TCGDEX + "cards/" + urllib.parse.quote(dcid))
            return sid, cid, best_price((d or {}).get("pricing"))
        except Exception:
            return sid, cid, None

    results = {}
    with ThreadPoolExecutor(WORKERS) as ex:
        for sid, cid, price in ex.map(fetch, jobs):
            if price is not None:
                results.setdefault(sid, {})[cid] = price
    got = sum(len(v) for v in results.values())
    print(f"Got prices for {got} cards")
    if got == 0:
        print("No prices recorded; TCGdex may be down.", file=sys.stderr)
        return 1

    # 4. append today's prices
    OUT.mkdir(exist_ok=True)
    for sid, prices in results.items():
        path = OUT / f"{sid}.json"
        try:
            data = json.loads(path.read_text())
        except Exception:
            data = {}
        cards = data.get("cards") if isinstance(data.get("cards"), dict) else {}
        for cid, price in prices.items():
            pts = [p for p in cards.get(cid, []) if isinstance(p, list) and len(p) == 2]
            if pts and pts[-1][0] == today:
                pts[-1][1] = price
            else:
                pts.append([today, price])
            cards[cid] = pts[-MAX_POINTS:]
        path.write_text(json.dumps({"set": sid, "updated": today, "cards": cards}, separators=(",", ":")))
    (OUT / "index.json").write_text(json.dumps(
        {"updated": today, "cards": got, "sets": sorted(p.stem for p in OUT.glob("*.json") if p.stem != "index")},
        separators=(",", ":")))
    return 0


if __name__ == "__main__":
    import urllib.parse  # noqa: E402  (used by quote())
    sys.exit(main())
