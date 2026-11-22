# ChaseDeck

Swipe through Pokémon cards to build your chase list, like a dating app for your grails.

**Live app:** https://jacintocons.github.io/ChaseDeck/

## Features

- **Built-in guide.** A quick how-to opens on first visit; tap the **?** button anytime to see it again.
- **Swipe to sort.** Swipe right to chase a card, left to pass, or up to mark it a Grail. Undo is one tap away.
- **Build your deck.** Filter by price range (default $5+), favorite Pokémon, quick groups (Eeveelutions, starters, legendaries…), generation, card type, set, era and rarity, and deal in shuffled or release order.
- **Market signals.** Live badges from each card's recent price trend: 📈 Heating up, 💎 Possible dip, ⚠️ Overheated, 📉 Sliding.
- **Claude's picks.** A weekly list of cards worth targeting, researched by Claude, with the reasoning, sources, the price on the day of each call and a running track record.
- **Live prices.** Shows the TCGplayer market price for each card, broken down by print variant.
- **Folders.** Your own folders (PC, To flip…) plus smart folders that fill themselves by set, Pokémon, price, status or market signal (Buy now, Consider selling). File cards right after a swipe, or select several at once.
- **Collection tracking.** Mark cards as owned, record what you paid, and see your gain at market price.
- **Chase list.** See the total left to chase, sort by priority, price, set or name, and mark cards as acquired.
- **Graded or raw.** Set the version you want for each card (Raw, PSA 10, PSA 9, BGS 9.5, CGC 10).
- **Buy links.** Jump straight to TCGplayer, eBay listings, eBay sold comps and PriceCharting.
- **Export.** Copy your list as text or CSV, download a CSV, or move it between devices with a backup code.
- **Looks good.** Cards tilt in 3D with a holo foil shine, swipes use spring physics, and the theme is dark and phone-first.

## How it works

ChaseDeck is a single `index.html` file with no build step, no server and no account.

- Card data comes from the open [Pokémon TCG dataset](https://github.com/PokemonTCG/pokemon-tcg-data).
- Prices are TCGplayer market prices from [TCGdex](https://tcgdex.dev) (free, no key needed), with the [pokemontcg.io](https://pokemontcg.io) API as a backup.
- **Our own price data:** a daily GitHub Action ([`record-prices.yml`](.github/workflows/record-prices.yml)) saves TCGplayer prices for about 3,800 chase-tier and vintage cards from [tcgcsv.com](https://tcgcsv.com) (TCGdex as a fallback) into [`prices/`](prices). A one-time backfill ([`backfill-prices.yml`](.github/workflows/backfill-prices.yml)) loads history back to February 2024 from tcgcsv's daily archives: every day for the last 6 months, one point per week before that.
- Weekly picks live in [`picks.json`](picks.json) in this repo.
- Your chase list and swipes are stored in your browser's local storage. Nothing is sent to a server.

## Disclaimer

Market signals and Claude's picks are AI analysis of public market data. They can be wrong and are not financial advice.

## Security

- A strict Content Security Policy allows only the page's own script and a short list of data and image hosts.
- All card data and backup codes are validated before they are displayed.
- Links are limited to known marketplaces.
- CSV exports are protected against spreadsheet formula injection.

If you edit the script, update the `sha256-…` hash in the CSP meta tag, or the browser will block the script.

## Run it locally

Open `index.html` in any modern browser.

---

Not affiliated with The Pokémon Company, Nintendo, Creatures or Game Freak. Card images and data belong to their respective owners.
