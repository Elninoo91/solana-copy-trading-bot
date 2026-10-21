import os
import base64
import aiohttp

from dotenv import load_dotenv
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient
from solders.rpc.config import RpcSendTransactionConfig as TxOpts
load_dotenv()

HELIUS_KEY = os.getenv("HELIUS_API_KEY")
PRIVATE_KEY_STR = os.getenv("BOT_PRIVATE_KEY")

if not HELIUS_KEY or not PRIVATE_KEY_STR:
    raise ValueError("Missing HELIUS_API_KEY or BOT_PRIVATE_KEY in .env file!")

SOLANA_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"

JUPITER_QUOTE_API = os.getenv(
    "JUPITER_QUOTE_API",
    "https://api.jup.ag/swap/v1/quote",
)
JUPITER_SWAP_API = os.getenv(
    "JUPITER_SWAP_API",
    "https://api.jup.ag/swap/v1/swap",
)

WSOL_MINT = "So11111111111111111111111111111111111111112"
SLIPPAGE_BPS = int(os.getenv("SLIPPAGE_BPS", "100"))
MAX_RETRIES = int(os.getenv("SWAP_MAX_RETRIES", "2"))
PRIORITY_FEE_LAMPORTS = int(os.getenv("PRIORITY_FEE_LAMPORTS", "500000"))


def load_keypair(private_key):
    private_key = private_key.strip()

    if private_key.startswith("["):
        import json
        return Keypair.from_bytes(bytes(json.loads(private_key)))

    try:
        import base58
        return Keypair.from_bytes(base58.b58decode(private_key))
    except Exception:
        return Keypair.from_base58_string(private_key)


BOT_KEYPAIR = load_keypair(PRIVATE_KEY_STR)


async def _get_quote(session, input_mint, output_mint, amount):
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(amount),
        "slippageBps": str(SLIPPAGE_BPS),
        "onlyDirectRoutes": "false",
    }

    async with session.get(
        JUPITER_QUOTE_API,
        params=params,
    ) as response:
        response.raise_for_status()
        data = await response.json()

    if data.get("error"):
        raise RuntimeError(f"Jupiter quote error: {data['error']}")

    if not data.get("outAmount"):
        raise RuntimeError("Jupiter returned no usable route.")

    return data


async def _build_and_send_swap(session, quote_data):
    payload = {
        "quoteResponse": quote_data,
        "userPublicKey": str(BOT_KEYPAIR.pubkey()),
        "wrapAndUnwrapSol": True,
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": PRIORITY_FEE_LAMPORTS,
    }

    async with session.post(
        JUPITER_SWAP_API,
        json=payload,
    ) as response:
        response.raise_for_status()
        swap_data = await response.json()

    if swap_data.get("error"):
        raise RuntimeError(f"Jupiter swap error: {swap_data['error']}")

    encoded = swap_data.get("swapTransaction")
    if not encoded:
        raise RuntimeError("Jupiter returned no serialized transaction.")

    raw_tx = VersionedTransaction.from_bytes(base64.b64decode(encoded))
    signed_tx = VersionedTransaction(raw_tx.message, [BOT_KEYPAIR])

    # Direct JSON-RPC call over HTTP (bypasses AsyncClient bugs)
    rpc_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendTransaction",
        "params": [
            base64.b64encode(bytes(signed_tx)).decode("utf-8"),
            {
                "encoding": "base64",
                "skipPreflight": False,
                "maxRetries": MAX_RETRIES,
            },
        ],
    }

    async with session.post(SOLANA_RPC_URL, json=rpc_payload) as response:
        response.raise_for_status()
        res_data = await response.json()

    if "error" in res_data:
        raise RuntimeError(f"Solana RPC error: {res_data['error']}")

    return res_data["result"]

async def execute_copy_buy(token_mint_address, amount_in_sol=0.03):
    if not token_mint_address:
        raise ValueError("Token mint address is empty.")

    if amount_in_sol <= 0:
        raise ValueError("amount_in_sol must be greater than zero.")

    lamports = int(amount_in_sol * 1_000_000_000)

    timeout = aiohttp.ClientTimeout(total=12)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        quote = await _get_quote(
            session,
            WSOL_MINT,
            token_mint_address,
            lamports,
        )

        print(
            f"LIVE BUY: {amount_in_sol:.4f} SOL -> "
            f"{token_mint_address}"
        )

        tx_sig = await _build_and_send_swap(session, quote)

    print(f"BUY SUBMITTED: https://solscan.io/tx/{tx_sig}")
    return tx_sig


async def execute_copy_sell(
    token_mint_address,
    token_amount_base_units=None,
):
    """
    Sell a copied token position into SOL.

    If token_amount_base_units is omitted, query the wallet's token account
    balance and sell the full available balance for this mint.
    """
    if not token_mint_address:
        raise ValueError("Token mint address is empty.")

    timeout = aiohttp.ClientTimeout(total=12)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        if token_amount_base_units is None:
            token_amount_base_units = await get_token_balance(
                session,
                token_mint_address,
            )

        token_amount_base_units = int(token_amount_base_units or 0)

        if token_amount_base_units <= 0:
            raise RuntimeError(
                f"No token balance available to sell for {token_mint_address}"
            )

        quote = await _get_quote(
            session,
            token_mint_address,
            WSOL_MINT,
            token_amount_base_units,
        )

        print(f"LIVE SELL: {token_mint_address} -> SOL")

        tx_sig = await _build_and_send_swap(session, quote)

    print(f"SELL SUBMITTED: https://solscan.io/tx/{tx_sig}")
    return tx_sig


async def get_token_balance(session, mint_address):
    """Use Helius RPC to find the bot wallet's raw token balance for a mint."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            str(BOT_KEYPAIR.pubkey()),
            {"mint": mint_address},
            {"encoding": "jsonParsed"},
        ],
    }

    async with session.post(
        SOLANA_RPC_URL,
        json=payload,
        timeout=aiohttp.ClientTimeout(total=8),
    ) as response:
        response.raise_for_status()
        data = await response.json()

    total = 0

    for account in ((data.get("result") or {}).get("value") or []):
        try:
            amount = int(
                account["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"]
            )
            total += amount
        except (KeyError, TypeError, ValueError):
            continue

    return total


if __name__ == "__main__":
    print(f"Bot wallet: {BOT_KEYPAIR.pubkey()}")
    print("executor.py loaded successfully.")
