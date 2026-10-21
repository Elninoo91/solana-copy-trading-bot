import os
import asyncio
import json
import time
import aiohttp
import websockets
from dotenv import load_dotenv

from auto_executor import execute_copy_buy, execute_copy_sell

load_dotenv()

HELIUS_KEY = os.getenv("HELIUS_API_KEY")
if not HELIUS_KEY:
    raise ValueError("Missing HELIUS_API_KEY in .env file!")

HELIUS_WSS_URL = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"
HELIUS_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"

# ---------- Configuration ----------
BURNER_FILE = os.getenv("BURNER_FILE", "vetted_burners.txt")
BUY_AMOUNT_SOL = float(os.getenv("BUY_AMOUNT_SOL", "0.03"))
DRY_RUN_START = os.getenv("DRY_RUN", "true").lower() in {"1", "true", "yes", "on"}
AUTO_LIVE = os.getenv("AUTO_LIVE", "true").lower() in {"1", "true", "yes", "on"}
REQUIRED_BUY_VALIDATIONS = int(os.getenv("REQUIRED_BUY_VALIDATIONS", "20"))
REQUIRED_SELL_VALIDATIONS = int(os.getenv("REQUIRED_SELL_VALIDATIONS", "10"))
MIN_SOL_RESERVE = float(os.getenv("MIN_SOL_RESERVE", "0.10"))
MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "5"))
SEEN_SIGNATURE_TTL = int(os.getenv("SEEN_SIGNATURE_TTL", "3600"))
STATE_FILE = os.getenv("STATE_FILE", "bot_state.json")
WSOL_MINT = "So11111111111111111111111111111111111111112"


def load_burners():
    if not os.path.exists(BURNER_FILE):
        raise FileNotFoundError(
            f"{BURNER_FILE} not found. Put one Solana wallet address per line."
        )
    with open(BURNER_FILE, "r", encoding="utf-8") as f:
        wallets = [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]
    return list(dict.fromkeys(wallets))


def load_state():
    default = {
        "buy_validations": 0,
        "sell_validations": 0,
        "live_enabled": False,
        "positions": {},
    }
    if not os.path.exists(STATE_FILE):
        return default
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        default.update(state)
        return default
    except Exception as exc:
        print(f"Could not read {STATE_FILE}: {exc}")
        return default


def save_state(state):
    temp_file = f"{STATE_FILE}.tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(temp_file, STATE_FILE)


def live_mode(state):
    if not AUTO_LIVE:
        return not DRY_RUN_START
    return bool(state.get("live_enabled", False))


def maybe_enable_live(state):
    if not AUTO_LIVE or state.get("live_enabled"):
        return False
    buys_ok = state["buy_validations"] >= REQUIRED_BUY_VALIDATIONS
    sells_ok = state["sell_validations"] >= REQUIRED_SELL_VALIDATIONS

    if buys_ok and sells_ok:
        state["live_enabled"] = True
        save_state(state)
        print("\n" + "=" * 60)
        print("AUTO-LIVE ENABLED")
        print(
            f"Validated buys: {state['buy_validations']} | "
            f"validated sells: {state['sell_validations']}"
        )
        print("The next eligible signal may use real SOL.")
        print("=" * 60 + "\n")
        return True
    return False


async def get_transaction(session, signature, retries=10, delay=0.5):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            signature,
            {
                "encoding": "jsonParsed",
                "commitment": "confirmed",  # HTTP RPC requires confirmed
                "maxSupportedTransactionVersion": 0,
            },
        ],
    }

    for attempt in range(retries):
        try:
            async with session.post(
                HELIUS_RPC_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as response:
                response.raise_for_status()
                data = await response.json()

                if "error" in data:
                    print(f"RPC Error for {signature}: {data['error']}")
                    return None

                if data.get("result") is not None:
                    return data["result"]
                
        except Exception:
            pass 

        await asyncio.sleep(delay)

    print(f"Lookup timed out for {signature} after {retries} attempts.")
    return None


def token_balance_map(balances):
    result = {}
    for balance in balances or []:
        mint = balance.get("mint")
        owner = balance.get("owner", "")
        amount = int((balance.get("uiTokenAmount") or {}).get("amount", "0"))
        if mint:
            result[(owner, mint)] = result.get((owner, mint), 0) + amount
    return result


def wallet_balance_delta_lamports(tx, wallet):
    meta = tx.get("meta") or {}
    message = (tx.get("transaction") or {}).get("message") or {}
    keys = message.get("accountKeys") or []
    pre = meta.get("preBalances") or []
    post = meta.get("postBalances") or []

    for index, key in enumerate(keys):
        pubkey = key.get("pubkey") if isinstance(key, dict) else key
        if pubkey == wallet and index < len(pre) and index < len(post):
            return pre[index] - post[index]
    return 0


def detect_token_change(tx, wallet):
    meta = tx.get("meta") or {}
    if meta.get("err") is not None:
        return None

    pre = token_balance_map(meta.get("preTokenBalances"))
    post = token_balance_map(meta.get("postTokenBalances"))

    candidate_mints = {
        mint
        for owner, mint in set(pre) | set(post)
        if owner == wallet and mint != WSOL_MINT
    }

    inflows = []
    outflows = []

    for mint in candidate_mints:
        before = pre.get((wallet, mint), 0)
        after = post.get((wallet, mint), 0)
        delta = after - before
        if delta > 0:
            inflows.append((mint, delta))
        elif delta < 0:
            outflows.append((mint, abs(delta)))

    sol_delta = wallet_balance_delta_lamports(tx, wallet)

    if len(inflows) == 1 and not outflows and sol_delta > 0:
        mint, amount = inflows[0]
        return ("buy", mint, amount)

    if len(outflows) == 1 and not inflows and sol_delta < 0:
        mint, amount = outflows[0]
        return ("sell", outflows[0][0], amount)

    return None


async def get_wallet_sol_balance(session):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [{"address": os.getenv("BOT_PUBLIC_KEY")}],
    }
    try:
        async with session.post(
            HELIUS_RPC_URL,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=5),
        ) as response:
            data = await response.json()
            lamports = (data.get("result") or {}).get("value")
            if lamports is not None:
                return lamports / 1_000_000_000
    except Exception:
        pass
    return None


async def process_signal(session, state, tx, wallet):
    if not tx:
        return

    signal = detect_token_change(tx, wallet)
    if not signal:
        return

    side, mint, token_amount = signal

    if side == "buy":
        state["buy_validations"] += 1
        print(
            f"BUY DETECTED | validations={state['buy_validations']} | "
            f"wallet={wallet} | mint={mint}"
        )

        if not live_mode(state):
            state["positions"].setdefault(
                mint,
                {
                    "source_wallet": wallet,
                    "simulated_amount": 0,
                    "source_last_buy_amount": token_amount,
                },
            )
            state["positions"][mint]["simulated_amount"] += token_amount

        became_live = maybe_enable_live(state)
        save_state(state)

        if live_mode(state):
            if len(state["positions"]) >= MAX_OPEN_POSITIONS and mint not in state["positions"]:
                print("LIVE BUY SKIPPED: maximum open positions reached.")
                return

            balance = await get_wallet_sol_balance(session)

            if balance is not None:
                available = balance - MIN_SOL_RESERVE
                if available < BUY_AMOUNT_SOL:
                    print(
                        f"LIVE BUY SKIPPED: only {balance:.4f} SOL available; "
                        f"reserve is {MIN_SOL_RESERVE:.4f} SOL."
                    )
                    return

            try:
                tx_sig = await execute_copy_buy(mint, amount_in_sol=BUY_AMOUNT_SOL)
                if tx_sig:
                    state["positions"][mint] = {
                        "source_wallet": wallet,
                        "source_last_buy_amount": token_amount,
                        "bot_buy_sol": BUY_AMOUNT_SOL,
                        "bot_buy_tx": tx_sig,
                    }
                    save_state(state)
            except Exception as exc:
                print(f"LIVE BUY FAILED for {mint}: {exc}")

    elif side == "sell":
        state["sell_validations"] += 1
        print(
            f"SELL DETECTED | validations={state['sell_validations']} | "
            f"wallet={wallet} | mint={mint}"
        )

        position = state["positions"].get(mint)

        if not live_mode(state):
            save_state(state)
            maybe_enable_live(state)
            save_state(state)
            return

        if not position:
            print(f"LIVE SELL SKIPPED: no copied position recorded for {mint}.")
            maybe_enable_live(state)
            save_state(state)
            return

        try:
            tx_sig = await execute_copy_sell(mint)
            if tx_sig:
                state["positions"].pop(mint, None)
                save_state(state)
        except Exception as exc:
            print(f"LIVE SELL FAILED for {mint}: {exc}")


async def fetch_and_process(session, state, signature, wallets):
    """Background task to fetch and process a transaction without blocking the WebSocket."""
    tx = await get_transaction(session, signature)
    if tx:
        await asyncio.gather(
            *[process_signal(session, state, tx, wallet) for wallet in wallets],
            return_exceptions=True,
        )


async def listen_to_burners():
    wallets = load_burners()
    if not wallets:
        print("No wallets to monitor.")
        return

    state = load_state()

    print(f"Loaded {len(wallets)} monitored wallets.")
    print(
        f"Auto-live={AUTO_LIVE}; "
        f"buy validations={state['buy_validations']}/{REQUIRED_BUY_VALIDATIONS}; "
        f"sell validations={state['sell_validations']}/{REQUIRED_SELL_VALIDATIONS}"
    )

    if not AUTO_LIVE:
        print(f"Manual DRY_RUN={DRY_RUN_START}")
    else:
        print(f"Current mode={'LIVE' if live_mode(state) else 'DRY RUN'}")

    seen = {}

    while True:
        try:
            async with websockets.connect(
                HELIUS_WSS_URL,
                ping_interval=20,
                ping_timeout=20,
                max_size=2**22,
            ) as websocket, aiohttp.ClientSession() as session:

                print("Connected to Helius WebSocket.")

                for idx, wallet in enumerate(wallets, start=1):
                    await websocket.send(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": idx,
                                "method": "logsSubscribe",
                                "params": [
                                    {"mentions": [wallet]},
                                    {"commitment": "processed"},
                                ],
                            }
                        )
                    )

                print("Monitoring for buys and sells...")

                async for raw in websocket:
                    data = json.loads(raw)

                    if "result" in data and "id" in data:
                        continue

                    params = data.get("params")
                    if not params:
                        continue

                    value = (params.get("result") or {}).get("value") or {}
                    signature = value.get("signature")
                    err = value.get("err")

                    if not signature or err is not None:
                        continue

                    now = time.time()

                    if len(seen) > 5000:
                        cutoff = now - SEEN_SIGNATURE_TTL
                        seen = {sig: ts for sig, ts in seen.items() if ts >= cutoff}

                    if signature in seen:
                        continue

                    seen[signature] = now
                    
                    print(f"Signature received: {signature}")

                    # ---------------------------------------------------------
                    # THE FIX: Spawn a background task so the WebSocket loop 
                    # instantly moves on to catch the next incoming signature.
                    # ---------------------------------------------------------
                    asyncio.create_task(fetch_and_process(session, state, signature, wallets))

        except (websockets.exceptions.ConnectionClosed, asyncio.TimeoutError) as exc:
            print(f"WebSocket disconnected: {exc}. Reconnecting in 3 seconds...")
            await asyncio.sleep(3)

        except Exception as exc:
            print(f"Listener error: {exc}. Reconnecting in 3 seconds...")
            await asyncio.sleep(3)


if __name__ == "__main__":
    try:
        asyncio.run(listen_to_burners())
    except KeyboardInterrupt:
        print("\nBot stopped by user.")