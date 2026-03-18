# E2E All Orders Tests

---

## Results

| # | Order Type | Description | Status | OrderID / TX Hash |
|---|-----------|-------------|--------|-------------------|
| 1 | Limit BUY (GTC) | Resting buy order that sits in the book until filled or cancelled | ✅ Passed | orderID: `0xf68a1542c87a9529680e661a708bb7035f94d4890221cdbd476f67343d478245` (cancelled) |
| 2 | Marketable Limit BUY (GTC @ bestAsk) | Limit buy priced at the best ask, immediately crossing the spread | ✅ Passed | tx: `0x19feaf04f35b6b40929d5b6dbd2287309ab85c03c19c7d5ed12f5cfe8b6830e0` |
| 3 | Marketable Limit SELL (GTC @ bestBid) | Limit sell priced at the best bid, immediately crossing the spread | ✅ Passed | tx: `0x4d0b7dcc3ebd87e5e3b87c43007fec0b7b1a1be16a57513c801af18a6d13e377` |
| 4 | Market BUY (FOK) | Fill-or-kill buy executed at market price; fails if not fully filled instantly | ✅ Passed | tx: `0x69721c10598d3c07ef9e6f14aa8d4b745fc20d51e08071658197ac6238189525` |
| 5 | Market SELL (FOK) | Fill-or-kill sell executed at market price; fails if not fully filled instantly | ✅ Passed | tx: `0x5dc53a6cc428f194fc17f3ab517afe579f42133e6560488eb2ef8e2b60cfb36e` |
| 6 | Market BUY with fees (FOK) | Market FOK buy with platform fee applied via `userUSDCBalance` for fee-adjusted sizing | ✅ Passed | tx: `0x30d825834a13fbf99770a33ffda8290deaca05ea8e321115a344f5e70bcb0488` |
| 7 | Market SELL with fees (FOK) | Market FOK sell with platform fee applied via `userUSDCBalance` | ✅ Passed | tx: `0x9929bfd896b5c9adcd3cabe01f183ab8b3945450f1c2af7e8929b86f6248c089` |
| 8 | Market BUY with fees + builder code (FOK) | Market FOK buy with both platform and builder taker fees, identified by builder code | ✅ Passed | tx: `0x08b5604767a1d8008fa891189317c8be08c45890e81352881f1801ab02d58888` |
| 9 | Market SELL with fees + builder code (FOK) | Market FOK sell with both platform and builder taker fees, identified by builder code | ✅ Passed | tx: `0x759fdf7ebfd68f8390c3baf09928288dd16c695e01ed9cf68132d9d738d2afed` |
| 10 | Limit SELL (GTC) | Resting sell order that sits in the book until filled or cancelled | ✅ Passed | orderID: `0xcb7e0724197d8264bb64ed00608092ef46eba92bf66acf05c3edfad93579a190` (cancelled) |

---
