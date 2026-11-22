#!/usr/bin/env python3
"""Screen ChaseDeck's price history for weekly pick candidates.

Reads prices/*.json plus card names from the open catalog and prints shortlists:
steady climbers, dips that are leveling off, still-sliding cards and fast spikes.
Used by the weekly picks research run; it doesn't change any files.
Usage: python scripts/screen_picks.py [--min-price 20] [--json out.json]
"""
import argparse, json, math, sys, datetime as dt
from pathlib import Path
from pricelib import load_catalog, get, CATALOG, OUT

POP = ["Charizard","Pikachu","Umbreon","Gengar","Mewtwo","Mew ","Eevee","Espeon","Sylveon","Rayquaza","Lugia","Greninja","Snorlax",
       "Dragonite","Gyarados","Blastoise","Venusaur","Lucario","Garchomp","Tyranitar","Mimikyu","Darkrai","Giratina","Glaceon","Leafeon",
       "Vaporeon","Jolteon","Flareon","Moltres","Zapdos","Articuno","Celebi","Jirachi","Latias","Latios","Arceus","Psyduck","Bulbasaur",
       "Squirtle","Charmander","Ho-Oh","Suicune","Lillie","Iono","Marnie","Cynthia","Erika","Misty"]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--min-price", type=float, default=20); ap.add_argument("--json")
    a = ap.parse_args()
    sets = load_catalog(); rows = []
    for f in sorted(OUT.glob("*.json")):
        if f.stem.startswith("_") or f.stem == "index": continue
        sid = f.stem; s = sets.get(sid, {})
        names = {c["id"]: c for c in (get(CATALOG + f"cards/en/{sid}.json", pause=0) or [])}
        for cid, pts in json.loads(f.read_text())["cards"].items():
            if len(pts) < 3: continue
            today, last = pts[-1]
            at = lambda d: next((v for x, v in reversed(pts) if x <= today - d), None)
            win = lambda d: [v for x, v in pts if x > today - d]
            ch = lambda base: (last - base) / base if base else None
            rel = dt.date(*map(int, s.get("releaseDate", "1999/01/01").split("/")))
            c = names.get(cid, {})
            rows.append(dict(id=cid, name=c.get("name", cid), rarity=c.get("rarity"), set=s.get("name"), series=s.get("series"),
                age=(dt.date(1970,1,1) + dt.timedelta(days=today) - rel).days, price=last,
                d7=ch(at(7)), d14=ch(at(14)), d30=ch(at(30)), d90=ch(at(90)), d180=ch(at(180)), d365=ch(at(365)),
                hi90=max(win(90) or [last]), hi365=max(win(365) or [last]), liq=len(set(win(30))),
                pop=any(p in (c.get("name") or "") + " " for p in POP)))
    fm = lambda x: f"{x*100:+.0f}%" if x is not None else "  - "
    def show(title, lst, n=30):
        print(f"\n== {title} ({len(lst)})")
        for r in lst[:n]:
            print(f"{r['id']:<16}{(r['name'] or '')[:26]:<27}{(r['set'] or '')[:20]:<21}${r['price']:>9.2f} 7d{fm(r['d7'])} 30d{fm(r['d30'])} "
                  f"90d{fm(r['d90'])} 180d{fm(r['d180'])} 1y{fm(r['d365'])} hi90 ${r['hi90']:.0f} liq{r['liq']} age{r['age']}{' *' if r['pop'] else ''}")
    P = [r for r in rows if r["price"] >= a.min_price and r["liq"] >= 12]
    w = lambda r: 1.4 if r["pop"] else 1
    up = [r for r in P if r["d90"] and 0.08 <= r["d90"] <= 0.7 and r["d30"] is not None and 0 <= r["d30"] <= 0.35 and (r["d7"] or 0) > -0.06]
    up.sort(key=lambda r: -r["d90"] * math.log(r["price"]) * w(r)); show("STEADY CLIMBERS", up)
    dip = [r for r in P if (r["hi90"] - r["price"]) / r["hi90"] >= 0.18 and r["d14"] is not None and r["d14"] >= -0.03 and (r["d7"] or 0) >= -0.03]
    dip.sort(key=lambda r: -((r["hi90"] - r["price"]) / r["hi90"]) * math.log(r["price"]) * w(r)); show("DIPS LEVELING OFF", dip)
    slide = [r for r in P if r["d30"] is not None and r["d30"] < -0.2 and (r["d7"] or 0) < -0.04]
    slide.sort(key=lambda r: r["d30"]); show("STILL SLIDING", slide, 20)
    hot = [r for r in P if (r["d30"] or 0) > 0.35 or (r["d7"] or 0) > 0.2]; hot.sort(key=lambda r: -(r["d30"] or 0)); show("FAST SPIKES", hot, 20)
    new = [r for r in P if r["age"] <= 120]; new.sort(key=lambda r: -r["price"]); show("NEW RELEASES (<=120 days)", new, 25)
    if a.json: Path(a.json).write_text(json.dumps(rows))

if __name__ == "__main__":
    sys.exit(main())
