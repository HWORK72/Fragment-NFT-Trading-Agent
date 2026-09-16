# Fragment NFT Trading Agent

[🇷🇺 Читать на русском](README_RU.md)

---

This project is an automated trading bot for the Fragment marketplace designed to detect and snipe Telegram Gifts listed below market value. On Fragment, gifts are traded as digital assets on the TON blockchain. Many sellers, whether due to inexperience or an urgency for quick liquidity, list rare items at floor prices. The bot continuously monitors the market, spots these mispriced listings in split seconds, and prepares them for purchase before manual users even notice them.

The core focus is on tracking rare attributes, especially sought-after black backgrounds such as Onyx Black or Obsidian. While a standard gift on the platform might trade around 5 TON, a rare piece with a black background can fetch 20 to 25 TON from collectors. If a seller mistakenly lists a rare item at standard floor price, the bot instantly identifies the discrepancy, cross-references it with market data, and flags the listing as a high-margin trade opportunity.

To safeguard funds, a strict risk management module is built into the architecture. The bot operates using a dedicated, isolated wallet, ensuring personal holdings remain completely untouched. The algorithm filters out high-risk trades, strictly adheres to user-defined price ceilings, and always maintains a reserve balance to cover network gas fees. If an auction triggers an aggressive bidding war, the bot automatically walks away to preserve capital.

I thoroughly battle-tested the entire system on live data. The bot interfaced directly with Fragment, pulling up to 180 listings within seconds without triggering rate limits or bans. The engine was linked to the TON testnet, where a test wallet was provisioned, funded, and verified on-chain. Every trade execution, price fluctuation, and market signal is logged and stored reliably in a local database.
