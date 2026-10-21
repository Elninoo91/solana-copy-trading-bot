import os
import asyncio
import aiohttp
from collections import Counter
from dotenv import load_dotenv

load_dotenv()

HELIUS_KEY = os.getenv("HELIUS_API_KEY")
if not HELIUS_KEY:
    raise ValueError("Missing HELIUS_API_KEY in .env file!")

HELIUS_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"

async def fetch_early_buyers(token_mint, limit=30):
    """
    Queries Helius RPC for the earliest transactions of a token mint 
    and extracts the initiating buyer wallets.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [
            token_mint,
            {"limit": limit}
        ]
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(HELIUS_RPC_URL, json=payload) as res:
            data = await res.json()
            signatures = data.get("result", [])
            if not signatures:
                return []

        # Reverse signatures to analyze from earliest available to newest
        signatures.reverse()

        early_buyers = []
        for sig_info in signatures[:15]:
            sig = sig_info.get("signature")
            tx_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTransaction",
                "params": [
                    sig,
                    {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
                ]
            }
            
            try:
                async with session.post(HELIUS_RPC_URL, json=tx_payload) as tx_res:
                    tx_data = await tx_res.json()
                    result = tx_data.get("result")
                    if result:
                        account_keys = result.get("transaction", {}).get("message", {}).get("accountKeys", [])
                        for key_info in account_keys:
                            if isinstance(key_info, dict) and key_info.get("signer"):
                                early_buyers.append(key_info.get("pubkey"))
                                break
            except Exception as e:
                pass
            
            await asyncio.sleep(0.1) # Avoid RPC rate limits

    return list(set(early_buyers))

async def analyze_top_snipers(successful_token_mints):
    """
    Scans a list of successful token mints and identifies 
    frequently recurring early buyers across multiple runners.
    """
    all_early_wallets = []

    for mint in successful_token_mints:
        print(f"Scanning on-chain history for token: {mint}")
        buyers = await fetch_early_buyers(mint)
        print(f"  Found {len(buyers)} early buyer wallets.")
        all_early_wallets.extend(buyers)

    wallet_counts = Counter(all_early_wallets)
    
    print("\n=== Top Identified Smart Money Wallets ===")
    if not wallet_counts:
        print("No buyer addresses returned. Ensure token mint addresses are valid.")
        return

    found_match = False
    for wallet, count in wallet_counts.most_common(10):
        if count >= 2:
            print(f"Smart Money Wallet: {wallet} | Early Buys: {count}")
            found_match = True

    if not found_match:
        print("No wallets met the threshold of appearing across multiple tokens yet. Try adding more token mints!")

if __name__ == "__main__":
    # Expand this list with multiple successful historical token mint addresses
    sample_successful_tokens = [
        "CzLSujWj52wCPTeUqV461xBgKNcByGpuVKvGdi6fpump", # GOAT
        "ED5nyyWEzpPPiWimP8vYm7sD7TD3LAt3Q3gRTWHzPJBY", # MOODENG
        # Add more token mint addresses here as strings inside quotes
    ]

    if not sample_successful_tokens:
        print("⚠️ Please open wallet_scanner.py and add token mint addresses to 'sample_successful_tokens'.")
    else:
        asyncio.run(analyze_top_snipers(sample_successful_tokens))