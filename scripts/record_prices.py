#!/usr/bin/env python3
"""ChaseDeck daily price recorder.

Runs once a day on GitHub Actions, after tcgcsv.com's daily update (about 20:00 UTC).
For each tracked set it downloads one TCGplayer price file from tcgcsv.com and adds
today's price for every tracked card to prices/<setId>.json. If tcgcsv.com is down,
it falls back to TCGdex. Standard library only.
"""
import json, os, re, sys, time, urllib.request, urllib.error, urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from pricelib import (TCGCSV, POKEMON, OUT, log, get, results, load_catalog, tracked_cards,
                      build_map, prices_from_rows, write_history, norm_num, norm_name)

TCGDEX = os.environ.get("TCGDEX_BASE", "https://api.tcgdex.net/v2/en/")
WORKERS = 6
MAP_MAX_AGE = 7  # days before the product mapping is rebuilt


def guess_dex_id(set_id):
    g = re.sub(r"^(sv|me)(\d)(?=\D|$)", lambda m: m.group(1) + "0" + m.group(2), set_id)
    return re.sub(r"pt5$", ".5", g)


def dex_best(pricing):
    tp = (pricing or {}).get("tcgplayer")
    if not isinstance(tp, dict):
        return None
    best = None
    for v in tp.values():
        if isinstance(v, dict):
            for k in ("marketPrice", "midPrice", "lowPrice"):
                x = v.get(k)
                if isinstance(x, (int, float)) and 0 < x < 1e7:
                    best = x if best is None or x > best else best
                    break
    return round(best, 2) if best is not None else None


def from_tcgdex(sets, tracked):
    dex_sets = [d for d in (get(TCGDEX + "sets", pause=0) or []) if isinstance(d, dict) and d.get("id")]
    ids = {d["id"] for d in dex_sets}
    jobs = []
    for sid, cards in tracked.items():
        nm = norm_name(sets[sid].get("name"))
        byname = [d["id"] for d in dex_sets if norm_name(d.get("name")) == nm]
        dsid = byname[0] if len(byname) == 1 else next((g for g in (guess_dex_id(sid), sid) if g in ids), byname[0] if byname else None)
        if not dsid:
            continue
        detail = get(TCGDEX + "sets/" + urllib.parse.quote(dsid), pause=0) or {}
        by_num = {norm_num(c.get("localId")): c.get("id") for c in detail.get("cards") or [] if isinstance(c, dict)}
        for cid, number, _ in cards:
            if by_num.get(norm_num(number)):
                jobs.append((cid, by_num[norm_num(number)]))
    def fetch(job):
        try:
            d = get(TCGDEX + "cards/" + urllib.parse.quote(job[1]), pause=0)
            return job[0], dex_best((d or {}).get("pricing"))
        except Exception:
            return job[0], None
    out = {}
    with ThreadPoolExecutor(WORKERS) as ex:
        for cid, p in ex.map(fetch, jobs):
            if p is not None:
                out[cid] = p
    return out


def from_tcgcsv(sets, tracked, today):
    mpath = OUT / "_map.json"
    mapping = None
    try:
        m = json.loads(mpath.read_text())
        if today - int(m.get("built", 0)) <= MAP_MAX_AGE:
            mapping = m["groups"]
    except Exception:
        pass
    if mapping is None:
        mapping, report = build_map(sets, tracked)
        OUT.mkdir(exist_ok=True)
        mpath.write_text(json.dumps({"built": today, "groups": mapping}, separators=(",", ":")))
        (OUT / "_report.json").write_text(json.dumps(report, indent=1))
        log("Rebuilt product mapping:", json.dumps(report["summary"]))
    out = {}
    for gid, pmap in mapping.items():
        rows = results(get(TCGCSV + f"tcgplayer/{POKEMON}/{gid}/prices"))
        out.update(prices_from_rows(rows, pmap))
    return out


def main():
    today = int(time.time() // 86400) + int(os.environ.get("DAY_OFFSET", "0"))
    sets = load_catalog()
    tracked = tracked_cards(sets)
    log(f"Tracking {sum(len(v) for v in tracked.values())} cards in {len(tracked)} sets")
    prices, source = {}, "tcgcsv"
    try:
        prices = from_tcgcsv(sets, tracked, today)
    except Exception as e:
        log(f"tcgcsv failed: {e}")
    if len(prices) < 50:
        source = "tcgdex"
        log("Falling back to TCGdex")
        try:
            prices.update(from_tcgdex(sets, tracked))
        except Exception as e:
            log(f"TCGdex failed: {e}")
    log(f"Got {len(prices)} prices from {source}")
    if not prices:
        return 1
    write_history({cid: {today: p} for cid, p in prices.items()}, today)
    return 0


if __name__ == "__main__":
    sys.exit(main())
