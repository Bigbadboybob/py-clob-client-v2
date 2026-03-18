import json
import os
import sys
import time
from typing import Optional

from dotenv import load_dotenv
from web3 import Web3

from py_clob_client_v2.client import ClobClient
from py_clob_client_v2.clob_types import (
    AssetType,
    BalanceAllowanceParams,
    BuilderConfig,
    MarketOrderArgsV2,
    OrderArgsV2,
    OrderPayload,
    OrderType,
    PartialCreateOrderOptions,
)
from py_clob_client_v2.config import get_contract_config
from py_clob_client_v2.constants import AMOY

load_dotenv()

_out = open(os.path.join(os.path.dirname(__file__), "e2e_orders_output.txt"), "w")

_orig_print = print


def log_print(*args, **kwargs):
    _orig_print(*args, **kwargs)
    _out.write(" ".join(str(a) for a in args) + "\n")
    _out.flush()


print = log_print  # noqa: A001

ERC20_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "inputs": [{"name": "", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "allowance",
        "type": "function",
        "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "name": "approve",
        "type": "function",
        "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
    },
]

WRAPPER_ABI = [
    {
        "name": "wrap",
        "type": "function",
        "inputs": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    }
]

NEG_RISK_ADAPTER_ABI = [
    {
        "name": "splitPosition",
        "type": "function",
        "inputs": [
            {"name": "conditionId", "type": "bytes32"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [],
        "stateMutability": "nonpayable",
    }
]

ERC1155_ABI = [
    {
        "name": "isApprovedForAll",
        "type": "function",
        "inputs": [{"name": "account", "type": "address"}, {"name": "operator", "type": "address"}],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
    },
    {
        "name": "setApprovalForAll",
        "type": "function",
        "inputs": [{"name": "operator", "type": "address"}, {"name": "approved", "type": "bool"}],
        "outputs": [],
        "stateMutability": "nonpayable",
    },
    {
        "name": "balanceOf",
        "type": "function",
        "inputs": [{"name": "account", "type": "address"}, {"name": "id", "type": "uint256"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
]

MAX_UINT256 = 2**256 - 1

def _log(label: str, result):
    print(f"\n── {label} ──")
    print(json.dumps(result, indent=2, default=str))


def run(label: str, fn):
    try:
        result = fn()
        _log(label, result)
        return result
    except Exception as e:
        _log(label, {"error": str(e)})
        return None


def get_gas(w3: Web3):
    gas_price = int(w3.eth.gas_price * 1.3)
    return {"gasPrice": gas_price, "gas": 500_000}


def split_collateral(w3: Web3, account, chain_id: int, condition_id: str, amount: float):
    contracts = get_contract_config(chain_id)
    usdc = w3.eth.contract(address=Web3.to_checksum_address(contracts.collateral), abi=ERC20_ABI)
    adapter = w3.eth.contract(
        address=Web3.to_checksum_address(contracts.neg_risk_adapter), abi=NEG_RISK_ADAPTER_ABI
    )
    amount_wei = int(amount * 1e6)
    usdc_bal = usdc.functions.balanceOf(account.address).call()
    print(f"USDC.e balance for split: {usdc_bal / 1e6:.6f}")
    split_amt = min(amount_wei, usdc_bal)
    if split_amt == 0:
        print("No USDC.e available — skipping split")
        return
    allowance = usdc.functions.allowance(account.address, contracts.neg_risk_adapter).call()
    if allowance < split_amt:
        print("Approving USDC.e for NegRiskAdapter...")
        tx = usdc.functions.approve(
            Web3.to_checksum_address(contracts.neg_risk_adapter), MAX_UINT256
        ).build_transaction(
            {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address), **get_gas(w3)}
        )
        signed = account.sign_transaction(tx)
        w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))
    condition_bytes = bytes.fromhex(condition_id.removeprefix("0x"))
    print(f"Splitting {split_amt / 1e6:.6f} USDC.e → YES/NO tokens for condition {condition_id[:12]}...")
    tx = adapter.functions.splitPosition(condition_bytes, split_amt).build_transaction(
        {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address), **get_gas(w3)}
    )
    signed = account.sign_transaction(tx)
    w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))
    print("Split done.")


def ensure_token_approvals(w3: Web3, account, chain_id: int, neg_risk: bool):
    contracts = get_contract_config(chain_id)
    exchange = contracts.neg_risk_exchange_v2 if neg_risk else contracts.exchange_v2

    ctf = w3.eth.contract(
        address=Web3.to_checksum_address(contracts.conditional_tokens), abi=ERC1155_ABI
    )
    if not ctf.functions.isApprovedForAll(account.address, exchange).call():
        print("Approving CTF tokens for exchange...")
        tx = ctf.functions.setApprovalForAll(Web3.to_checksum_address(exchange), True).build_transaction(
            {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address), **get_gas(w3)}
        )
        signed = account.sign_transaction(tx)
        w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))

    if neg_risk:
        try:
            adapter = w3.eth.contract(
                address=Web3.to_checksum_address(contracts.neg_risk_adapter), abi=ERC1155_ABI
            )
            if not adapter.functions.isApprovedForAll(account.address, exchange).call():
                print("Approving NegRiskAdapter tokens for exchange...")
                tx = adapter.functions.setApprovalForAll(
                    Web3.to_checksum_address(exchange), True
                ).build_transaction(
                    {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address), **get_gas(w3)}
                )
                signed = account.sign_transaction(tx)
                w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))
        except Exception:
            pass

    print("Token approvals verified.")


def get_token_balance(w3: Web3, account, chain_id: int, token_id: str, neg_risk: bool = False) -> float:
    contracts = get_contract_config(chain_id)
    token_contract = contracts.neg_risk_adapter if neg_risk else contracts.conditional_tokens
    erc1155 = w3.eth.contract(address=Web3.to_checksum_address(token_contract), abi=ERC1155_ABI)
    bal = erc1155.functions.balanceOf(account.address, int(token_id)).call()
    return bal / 1e6


def ensure_pmct(
    w3: Web3, account, chain_id: int, pmct_address: str, wrapper_address: str, split_reserve: float = 0
) -> float:
    contracts = get_contract_config(chain_id)

    pmct = w3.eth.contract(address=Web3.to_checksum_address(pmct_address), abi=ERC20_ABI)
    usdc = w3.eth.contract(address=Web3.to_checksum_address(contracts.collateral), abi=ERC20_ABI)
    wrapper = w3.eth.contract(address=Web3.to_checksum_address(wrapper_address), abi=WRAPPER_ABI)

    pmct_bal = pmct.functions.balanceOf(account.address).call()
    print(f"\nPMCT balance: {pmct_bal / 1e6:.6f}")

    usdc_bal = usdc.functions.balanceOf(account.address).call()
    print(f"USDC.e balance: {usdc_bal / 1e6:.6f}")

    reserve_wei = int(split_reserve * 1e6)
    wrap_amount = max(0, usdc_bal - reserve_wei)

    if wrap_amount == 0:
        print(f"No USDC.e to wrap (reserving {split_reserve} for split)")
    else:
        allowance = usdc.functions.allowance(account.address, wrapper_address).call()
        if allowance < wrap_amount:
            print("Approving USDC.e for wrapper...")
            tx = usdc.functions.approve(
                Web3.to_checksum_address(wrapper_address), MAX_UINT256
            ).build_transaction(
                {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address), **get_gas(w3)}
            )
            signed = account.sign_transaction(tx)
            w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))

        print(f"Wrapping {wrap_amount / 1e6:.6f} USDC.e → PMCT (reserving {split_reserve} for split)...")
        tx = wrapper.functions.wrap(
            Web3.to_checksum_address(contracts.collateral), account.address, wrap_amount
        ).build_transaction(
            {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address), **get_gas(w3)}
        )
        signed = account.sign_transaction(tx)
        w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))

        pmct_bal = pmct.functions.balanceOf(account.address).call()
        print(f"PMCT balance after wrap: {pmct_bal / 1e6:.6f}")

    return pmct_bal / 1e6


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    rpc_url = os.environ.get("RPC_URL")
    pk = os.environ["PK"]
    chain_id = int(os.environ.get("CHAIN_ID", AMOY))
    host = os.environ.get("CLOB_API_URL", "http://localhost:8080")
    token_id = os.environ["TOKEN_ID"]
    builder_code = os.environ.get("BUILDER_CODE")
    pmct_address = os.environ.get("COLLATERAL_TOKEN_ADDRESS")
    wrapper_address = os.environ.get("WRAPPER_ADDRESS")

    w3 = Web3(Web3.HTTPProvider(rpc_url)) if rpc_url else None
    account = Web3().eth.account.from_key(pk)
    print(f"Address: {account.address}, chainId: {chain_id}")

    pk2 = os.environ.get("PK2")
    client2: Optional[ClobClient] = None
    account2 = None
    w2_pending_orders: list = []

    if pk2:
        account2 = Web3().eth.account.from_key(pk2)
        print(f"Counterparty: {account2.address}")
        auth_client2 = ClobClient(host=host, chain_id=chain_id, key=pk2)
        creds2 = auth_client2.derive_api_key()
        if not (creds2 and creds2.api_key):
            creds2 = auth_client2.create_api_key()
        client2 = ClobClient(host=host, chain_id=chain_id, key=pk2, creds=creds2)

    auth_client = ClobClient(host=host, chain_id=chain_id, key=pk)
    creds = auth_client.derive_api_key()
    if not (creds and creds.api_key):
        creds = auth_client.create_api_key()
    print(f"API key: {creds.api_key}")

    client = ClobClient(
        host=host,
        chain_id=chain_id,
        key=pk,
        creds=creds,
        builder_config=BuilderConfig(builder_code=builder_code) if builder_code else None,
    )

    book = client.get_order_book(token_id)
    condition_id = book["market"]
    tick_size = book["tick_size"]
    neg_risk = book["neg_risk"]
    tick = float(tick_size)

    client.get_clob_market_info(condition_id)

    order_size_env = os.environ.get("ORDER_SIZE")
    min_order_size = float(book["min_order_size"])
    order_size_usdc = float(order_size_env) if order_size_env else min_order_size

    options = PartialCreateOrderOptions(tick_size=tick_size, neg_risk=neg_risk)

    split_reserve = order_size_usdc * 4
    pmct_balance = 0.0
    if w3 and pmct_address and wrapper_address:
        pmct_balance = ensure_pmct(w3, account, chain_id, pmct_address, wrapper_address, split_reserve)
    else:
        print("RPC_URL / COLLATERAL_TOKEN_ADDRESS / WRAPPER_ADDRESS not set — skipping PMCT check")

    if w3:
        ensure_token_approvals(w3, account, chain_id, neg_risk)

    if w3 and account2:
        ensure_token_approvals(w3, account2, chain_id, neg_risk)
        if pmct_address:
            contracts = get_contract_config(chain_id)
            exchange = contracts.neg_risk_exchange_v2 if neg_risk else contracts.exchange_v2
            pmct2 = w3.eth.contract(address=Web3.to_checksum_address(pmct_address), abi=ERC20_ABI)
            allowance = pmct2.functions.allowance(account2.address, exchange).call()
            if allowance == 0:
                print("Approving PMCT for counterparty...")
                tx = pmct2.functions.approve(
                    Web3.to_checksum_address(exchange), MAX_UINT256
                ).build_transaction(
                    {"from": account2.address, "nonce": w3.eth.get_transaction_count(account2.address), **get_gas(w3)}
                )
                signed = account2.sign_transaction(tx)
                w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))

    token_bal = get_token_balance(w3, account, chain_id, token_id, neg_risk) if w3 else 0.0
    tokens_needed = (order_size_usdc / (1 - tick)) * 4
    if w3 and token_bal < tokens_needed:
        split_amt = round(tokens_needed - token_bal, 6)
        split_collateral(w3, account, chain_id, condition_id, split_amt)
        time.sleep(3)
        token_bal = get_token_balance(w3, account, chain_id, token_id, neg_risk)

    cond_params = BalanceAllowanceParams(asset_type=AssetType.CONDITIONAL, token_id=token_id)
    print("Updating CLOB balance for PK...")
    client.update_balance_allowance(cond_params)
    client.update_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
    if client2:
        print("Updating CLOB balance for PK2...")
        client2.update_balance_allowance(cond_params)
        client2.update_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))

    best_ask = float(book["asks"][0]["price"]) if book.get("asks") else None
    best_bid = float(book["bids"][0]["price"]) if book.get("bids") else None

    print(f"\nMarket:    {condition_id}")
    print(f"Token:     {token_id}")
    print(f"TickSize:  {tick_size} | NegRisk: {neg_risk}")
    print(f"Best bid:  {best_bid if best_bid is not None else 'none'} | Best ask: {best_ask if best_ask is not None else 'none'}")
    print(f"Min order: {min_order_size} USDC | Using: {order_size_usdc} USDC")
    print(f"Token balance: {token_bal}")

    safe_buy_price = tick
    safe_sell_price = 1 - tick
    limit_buy_shares = round(order_size_usdc / safe_buy_price, 2)
    limit_sell_shares = round(order_size_usdc / safe_sell_price, 2)

    pending_orders: list = []

    def fresh_bid() -> Optional[float]:
        b = client.get_order_book(token_id)
        return float(b["bids"][0]["price"]) if b.get("bids") else None

    def fresh_ask() -> Optional[float]:
        b = client.get_order_book(token_id)
        return float(b["asks"][0]["price"]) if b.get("asks") else None

    def seed_ask(seed_price: float, seed_shares: float) -> Optional[str]:
        print(f"\n  [seed] GTC SELL {seed_shares} @ {seed_price} to seed ask...")
        result = run(
            "SEED ASK",
            lambda: client.create_and_post_order(
                OrderArgsV2(token_id=token_id, price=seed_price, size=seed_shares, side="SELL"),
                options,
                OrderType.GTC,
            ),
        )
        if result and result.get("orderID"):
            print(f"  [seed] ask seeded: {result['orderID']}")
            return result["orderID"]
        return None

    def seed_bid(seed_price: float, seed_shares: float) -> Optional[str]:
        print(f"\n  [seed] GTC BUY {seed_shares} @ {seed_price} to seed bid...")
        result = run(
            "SEED BID",
            lambda: client.create_and_post_order(
                OrderArgsV2(token_id=token_id, price=seed_price, size=seed_shares, side="BUY"),
                options,
                OrderType.GTC,
            ),
        )
        if result and result.get("orderID"):
            print(f"  [seed] bid seeded: {result['orderID']}")
            return result["orderID"]
        return None

    def w2_seed_bid() -> Optional[str]:
        if not client2:
            return None
        seed_price = round(1 - tick, 3)
        seed_shares = round(order_size_usdc / seed_price, 2)
        print(f"\n  [w2] GTC BUY {seed_shares} @ {seed_price}...")
        try:
            result = client2.create_and_post_order(
                OrderArgsV2(token_id=token_id, price=seed_price, size=seed_shares, side="BUY"),
                options,
                OrderType.GTC,
            )
            if result and result.get("orderID"):
                print(f"  [w2] bid seeded: {result['orderID']}")
                w2_pending_orders.append(result["orderID"])
                time.sleep(2)
                return result["orderID"]
        except Exception as e:
            print(f"  [w2] seed bid failed: {e}")
        return None

    def w2_seed_ask() -> Optional[str]:
        if not client2 or not account2:
            return None
        w2_bal = get_token_balance(w3, account2, chain_id, token_id, neg_risk) if w3 else 0.0
        if w2_bal <= 0:
            time.sleep(5)
            w2_bal = get_token_balance(w3, account2, chain_id, token_id, neg_risk) if w3 else 0.0
        if w2_bal <= 0:
            print("  [w2] no token balance for ask seed")
            return None
        client2.update_balance_allowance(cond_params)
        seed_price = round(1 - tick, 3)
        seed_shares = round(min(order_size_usdc / seed_price, w2_bal), 2)
        print(f"\n  [w2] GTC SELL {seed_shares} @ {seed_price}...")
        try:
            result = client2.create_and_post_order(
                OrderArgsV2(token_id=token_id, price=seed_price, size=seed_shares, side="SELL"),
                options,
                OrderType.GTC,
            )
            if result and result.get("orderID"):
                print(f"  [w2] ask seeded: {result['orderID']}")
                w2_pending_orders.append(result["orderID"])
                time.sleep(2)
                return result["orderID"]
        except Exception as e:
            print(f"  [w2] seed ask failed: {e}")
        return None
    
     # ── 1. Limit BUY ──────────────────────────────────────────────────────────

    result1 = run(
        "1. Limit BUY",
        lambda: client.create_and_post_order(
            OrderArgsV2(token_id=token_id, price=safe_buy_price, size=limit_buy_shares, side="BUY"),
            options,
            OrderType.GTC,
        ),
    )
    if result1 and result1.get("orderID"):
        pending_orders.append(result1["orderID"])

    # ── 2. Marketable Limit BUY ───────────────────────────────────────────────
    if not client2:
        print("\n── 2. Marketable Limit BUY ── SKIPPED (no counterparty)")
    else:
        w2_seed_ask()
        ask2 = fresh_ask()
        if ask2 is None:
            print("\n── 2. Marketable Limit BUY ── SKIPPED (no ask liquidity)")
        else:
            shares2 = round(order_size_usdc / ask2, 2)
            result2 = run(
                "2. Marketable Limit BUY",
                lambda: client.create_and_post_order(
                    OrderArgsV2(token_id=token_id, price=ask2, size=shares2, side="BUY"),
                    options,
                    OrderType.GTC,
                ),
            )
            if result2 and result2.get("status") == "matched" and result2.get("takingAmount"):
                token_bal += float(result2["takingAmount"])
                time.sleep(5)
                client.update_balance_allowance(cond_params)
            elif result2 and result2.get("orderID"):
                pending_orders.append(result2["orderID"])

    # ── 3. Marketable Limit SELL ──────────────────────────────────────────────
    if not client2:
        print("\n── 3. Marketable Limit SELL ── SKIPPED (no counterparty)")
    elif token_bal <= 0:
        print("\n── 3. Marketable Limit SELL ── SKIPPED (no token balance)")
    else:
        w2_seed_bid()
        bid3 = fresh_bid()
        if bid3 is None:
            print("\n── 3. Marketable Limit SELL ── SKIPPED (no bid liquidity)")
        else:
            shares3 = round(min(order_size_usdc / bid3, token_bal), 2)
            result3 = run(
                "3. Marketable Limit SELL",
                lambda: client.create_and_post_order(
                    OrderArgsV2(token_id=token_id, price=bid3, size=shares3, side="SELL"),
                    options,
                    OrderType.GTC,
                ),
            )
            if result3 and result3.get("status") == "matched" and result3.get("makingAmount"):
                token_bal = max(0.0, token_bal - float(result3["makingAmount"]))
                # Give w2 time for on-chain settlement so it has YES tokens to seed step 4.
                time.sleep(10)
                client2.update_balance_allowance(cond_params)
            elif result3 and result3.get("orderID"):
                pending_orders.append(result3["orderID"])

    # ── 4. Market BUY ─────────────────────────────────────────────────────────
    if not client2:
        print("\n── 4. Market BUY ── SKIPPED (no counterparty)")
    else:
        w2_seed_ask()
        ask4 = fresh_ask()
        if ask4 is None:
            print("\n── 4. Market BUY ── SKIPPED (no ask liquidity)")
        else:
            result4 = run(
                "4. Market BUY",
                lambda: client.create_and_post_market_order(
                    MarketOrderArgsV2(token_id=token_id, amount=order_size_usdc, side="BUY", order_type=OrderType.FOK),
                    options,
                    OrderType.FOK,
                ),
            )
            if result4 and result4.get("status") == "matched" and result4.get("takingAmount"):
                token_bal += float(result4["takingAmount"])
                time.sleep(5)
                client.update_balance_allowance(cond_params)

    # ── 5. Market SELL ────────────────────────────────────────────────────────
    if not client2:
        print("\n── 5. Market SELL ── SKIPPED (no counterparty)")
    elif token_bal <= 0:
        print("\n── 5. Market SELL ── SKIPPED (no token balance)")
    else:
        w2_seed_bid()
        bid5 = fresh_bid()
        if bid5 is None:
            print("\n── 5. Market SELL ── SKIPPED (no bid liquidity)")
        else:
            shares5 = round(min(order_size_usdc / bid5, token_bal), 2)
            result5 = run(
                "5. Market SELL",
                lambda: client.create_and_post_market_order(
                    MarketOrderArgsV2(token_id=token_id, amount=shares5, side="SELL", order_type=OrderType.FOK),
                    options,
                    OrderType.FOK,
                ),
            )
            if result5 and result5.get("status") == "matched" and result5.get("makingAmount"):
                token_bal = max(0.0, token_bal - float(result5["makingAmount"]))

    # ── 6. Market BUY with fees ───────────────────────────────────────────────
    if not client2:
        print("\n── 6. Market BUY with fees ── SKIPPED (no counterparty)")
    else:
        w2_seed_ask()
        ask6 = fresh_ask()
        if ask6 is None:
            print("\n── 6. Market BUY with fees ── SKIPPED (no ask liquidity)")
        else:
            result6 = run(
                "6. Market BUY with fees",
                lambda: client.create_and_post_market_order(
                    MarketOrderArgsV2(
                        token_id=token_id,
                        amount=order_size_usdc,
                        side="BUY",
                        order_type=OrderType.FOK,
                        user_usdc_balance=pmct_balance if pmct_balance > 0 else 0,
                    ),
                    options,
                    OrderType.FOK,
                ),
            )
            if result6 and result6.get("status") == "matched" and result6.get("takingAmount"):
                token_bal += float(result6["takingAmount"])
                time.sleep(5)
                client.update_balance_allowance(cond_params)

    # ── 7. Market SELL with fees ──────────────────────────────────────────────
    if not client2:
        print("\n── 7. Market SELL with fees ── SKIPPED (no counterparty)")
    elif token_bal <= 0:
        print("\n── 7. Market SELL with fees ── SKIPPED (no token balance)")
    else:
        w2_seed_bid()
        bid7 = fresh_bid()
        if bid7 is None:
            print("\n── 7. Market SELL with fees ── SKIPPED (no bid liquidity)")
        else:
            shares7 = round(min(order_size_usdc / bid7, token_bal), 2)
            result7 = run(
                "7. Market SELL with fees",
                lambda: client.create_and_post_market_order(
                    MarketOrderArgsV2(
                        token_id=token_id,
                        amount=shares7,
                        side="SELL",
                        order_type=OrderType.FOK,
                        user_usdc_balance=pmct_balance if pmct_balance > 0 else 0,
                    ),
                    options,
                    OrderType.FOK,
                ),
            )
            if result7 and result7.get("status") == "matched" and result7.get("makingAmount"):
                token_bal = max(0.0, token_bal - float(result7["makingAmount"]))

    # ── 8. Market BUY with fees + builder code ────────────────────────────────
    if not builder_code:
        print("\n── 8. Market BUY with fees + builder code ── SKIPPED (no BUILDER_CODE in env)")
    elif not client2:
        print("\n── 8. Market BUY with fees + builder code ── SKIPPED (no counterparty)")
    else:
        w2_seed_ask()
        ask8 = fresh_ask()
        if ask8 is None:
            print("\n── 8. Market BUY with fees + builder code ── SKIPPED (no ask liquidity)")
        else:
            result8 = run(
                "8. Market BUY with fees + builder code",
                lambda: client.create_and_post_market_order(
                    MarketOrderArgsV2(
                        token_id=token_id,
                        amount=order_size_usdc,
                        side="BUY",
                        order_type=OrderType.FOK,
                        builder_code=builder_code,
                        user_usdc_balance=pmct_balance if pmct_balance > 0 else 0,
                    ),
                    options,
                    OrderType.FOK,
                ),
            )
            if result8 and result8.get("status") == "matched" and result8.get("takingAmount"):
                token_bal += float(result8["takingAmount"])
                time.sleep(5)
                client.update_balance_allowance(cond_params)

    # ── 9. Market SELL with fees + builder code ───────────────────────────────
    if not builder_code:
        print("\n── 9. Market SELL with fees + builder code ── SKIPPED (no BUILDER_CODE in env)")
    elif not client2:
        print("\n── 9. Market SELL with fees + builder code ── SKIPPED (no counterparty)")
    elif token_bal <= 0:
        print("\n── 9. Market SELL with fees + builder code ── SKIPPED (no token balance)")
    else:
        w2_seed_bid()
        bid9 = fresh_bid()
        if bid9 is None:
            print("\n── 9. Market SELL with fees + builder code ── SKIPPED (no bid liquidity)")
        else:
            shares9 = round(min(order_size_usdc / bid9, token_bal), 2)
            result9 = run(
                "9. Market SELL with fees + builder code",
                lambda: client.create_and_post_market_order(
                    MarketOrderArgsV2(
                        token_id=token_id,
                        amount=shares9,
                        side="SELL",
                        order_type=OrderType.FOK,
                        builder_code=builder_code,
                        user_usdc_balance=pmct_balance if pmct_balance > 0 else 0,
                    ),
                    options,
                    OrderType.FOK,
                ),
            )
            if result9 and result9.get("status") == "matched" and result9.get("makingAmount"):
                token_bal = max(0.0, token_bal - float(result9["makingAmount"]))

    # ── 10. Limit SELL ────────────────────────────────────────────────────────
    if token_bal < min_order_size:
        print(f"\n── 10. Limit SELL ── SKIPPED (token balance {token_bal:.4f} < min {min_order_size})")
    else:
        limit_sell_size = round(min(limit_sell_shares, token_bal), 2)
        result10 = run(
            "10. Limit SELL",
            lambda: client.create_and_post_order(
                OrderArgsV2(token_id=token_id, price=safe_sell_price, size=limit_sell_size, side="SELL"),
                options,
                OrderType.GTC,
            ),
        )
        if result10 and result10.get("orderID"):
            pending_orders.append(result10["orderID"])

    # ── Cleanup ───────────────────────────────────────────────────────────────
    if pending_orders:
        print(f"\nCancelling {len(pending_orders)} resting limit order(s)...")
        for order_id in pending_orders:
            cancel = client.cancel_order(OrderPayload(orderID=order_id))
            print(f"  Cancelled {order_id}:", json.dumps(cancel, default=str))

    if w2_pending_orders and client2:
        print(f"\nCancelling {len(w2_pending_orders)} counterparty order(s)...")
        for order_id in w2_pending_orders:
            try:
                cancel = client2.cancel_order(OrderPayload(orderID=order_id))
                print(f"  Cancelled {order_id}:", json.dumps(cancel, default=str))
            except Exception as e:
                print(f"  Cancel {order_id} failed (may already be filled): {e}")

    print("\nDone.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise
    finally:
        _out.close()
