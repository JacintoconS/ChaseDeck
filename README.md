# ChaseDeck

Swipe through Pokémon cards to build your chase list, like a dating app for your grails.

**Live app:** https://jacintocons.github.io/ChaseDeck/

## Features

- **Built-in guide.** A quick how-to opens on first visit; tap the **?** button anytime to see it again.
- **Swipe to sort.** Swipe right to chase a card, left to pass, or up to mark it a Grail. Undo is one tap away.
- **Build your deck.** Filter by set, era, rarity (chase tier, hits & holos, or exact rarities), Pokémon or artist, and deal in shuffled or release order.
- **Live prices.** Shows the TCGplayer market price for each card, broken down by print variant.
- **Chase list.** See the total left to chase, sort by priority, price, set or name, and mark cards as acquired.
- **Graded or raw.** Set the version you want for each card (Raw, PSA 10, PSA 9, BGS 9.5, CGC 10).
- **Buy links.** Jump straight to TCGplayer, eBay listings, eBay sold comps and PriceCharting.
- **Export.** Copy your list as text or CSV, download a CSV, or move it between devices with a backup code.
- **Looks good.** Cards tilt in 3D with a holo foil shine, swipes use spring physics, and the theme is dark and phone-first.

## How it works

ChaseDeck is a single `index.html` file with no build step, no server and no account.

- Card data comes from the open [Pokémon TCG dataset](https://github.com/PokemonTCG/pokemon-tcg-data).
- Prices are TCGplayer market prices from [TCGdex](https://tcgdex.dev) (free, no key needed), with the [pokemontcg.io](https://pokemontcg.io) API as a backup.
- Your chase list and swipes are stored in your browser's local storage. Nothing is sent to a server.

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
