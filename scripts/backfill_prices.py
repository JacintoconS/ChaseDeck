#!/usr/bin/env python3
"""One-time backfill of ChaseDeck's price history from tcgcsv.com's daily archives.

tcgcsv.com keeps a daily snapshot of TCGplayer prices back to 2024-02-08. Their
guidance: downloading the archive once is fine, re-downloading it every day is not.
So this runs once (by hand, from the Actions tab). To keep the download and the
repo small, it takes one archive per week for older history and every day for
the last 180 days.
"""
import datetime as dt, json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
from pricelib import (TCGCSV, POKEMON, OUT, DAILY_DAYS, log, get, results, load_catalog,
                      tracked_cards, build_map, prices_from_rows, write_history)

FIRST = dt.date(2024, 2, 8)


def extract(archive, dest):
    if shutil.which("7z"):
        subprocess.run(["7z", "x", "-y", f"-o{dest}", str(archive)], check=True, stdout=subprocess.DEVNULL)
    else:
        import py7zr
        with py7zr.SevenZipFile(archive) as z:
            z.extractall(dest)


def main():
    today_d = dt.datetime.now(dt.timezone.utc).date()
    today = (today_d - dt.date(1970, 1, 1)).days
    start = dt.date.fromisoformat(os.environ.get("BACKFILL_FROM", FIRST.isoformat()))
    start = max(start, FIRST)
    cutoff = today_d - dt.timedelta(days=DAILY_DAYS)
    dates, d = [], start
    while d < today_d:
        if d >= cutoff or (d - start).days % 7 == 0:
            dates.append(d)
        d += dt.timedelta(days=1)
    log(f"Backfilling {len(dates)} archives from {start} to {dates[-1] if dates else '-'}")

    sets = load_catalog()
    tracked = tracked_cards(sets)
    mapping, report = build_map(sets, tracked)
    OUT.mkdir(exist_ok=True)
    (OUT / "_map.json").write_text(json.dumps({"built": today, "groups": mapping}, separators=(",", ":")))
    log("Mapping:", json.dumps(report["summary"]))

    points, ok, missing = {}, 0, []
    with tempfile.TemporaryDirectory() as tmp:
        for i, day in enumerate(dates):
            name = f"prices-{day.isoformat()}.ppmd.7z"
            try:
                blob = get(TCGCSV + "archive/tcgplayer/" + name, as_json=False, pause=1.0)
            except Exception as e:
                blob = None; log(f"  {day}: download failed ({e})")
            if not blob:
                missing.append(day.isoformat()); continue
            arc = Path(tmp) / name; arc.write_bytes(blob)
            out = Path(tmp) / "x"
            try:
                extract(arc, out)
            except Exception as e:
                log(f"  {day}: extract failed ({e})"); missing.append(day.isoformat()); continue
            finally:
                arc.unlink(missing_ok=True)
            base = next((p for p in out.glob(f"*/{POKEMON}") if p.is_dir()), None)
            dnum = (day - dt.date(1970, 1, 1)).days
            n = 0
            if base:
                for gid, pmap in mapping.items():
                    f = base / gid / "prices"
                    if not f.exists():
                        continue
                    try:
                        rows = results(json.loads(f.read_text()))
                    except Exception:
                        continue
                    for cid, price in prices_from_rows(rows, pmap).items():
                        points.setdefault(cid, {})[dnum] = price; n += 1
            shutil.rmtree(out, ignore_errors=True)
            ok += 1
            if i % 20 == 0 or i == len(dates) - 1:
                log(f"  [{i+1}/{len(dates)}] {day}: {n} prices")

    log(f"Archives used: {ok}, missing: {len(missing)}; cards with history: {len(points)}")
    if not points:
        print("Nothing recorded.", file=sys.stderr)
        return 1
    write_history(points, today)
    report["backfill"] = {"archives": ok, "missing": missing[:50], "cards_with_history": len(points),
                          "from": dates[0].isoformat(), "to": dates[-1].isoformat()}
    (OUT / "_report.json").write_text(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
