import os
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()

HELIUS_KEY = os.getenv("HELIUS_API_KEY")
if not HELIUS_KEY:
    raise ValueError("Missing HELIUS_API_KEY in .env file!")

HELIUS_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"

async def map_funder_cluster(master_wallet):
    """
    Scans a master wallet's outgoing transaction history to find 
    all child/burner wallets it has funded.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [
            master_wallet,
            {"limit": 100} # Adjust limit as needed to scan more history
        ]
    }
    
    async with aiohttp.ClientSession() as session:
        print(f"Scanning history for master funder: {master_wallet}")
        async with session.post(HELIUS_RPC_URL, json=payload) as res:
            data = await res.json()
            signatures = data.get("result", [])
            
            if not signatures:
                print("❌ No transactions found for this master address.")
                return
            
            child_wallets = set()
            
            for sig_info in signatures:
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
                            meta = result.get("meta", {})
                            pre_balances = meta.get("preBalances", [])
                            post_balances = meta.get("postBalances", [])
                            
                            if pre_balances and post_balances and account_keys:
                                for i, key_info in enumerate(account_keys):
                                    pubkey = key_info.get("pubkey") if isinstance(key_info, dict) else key_info
                                    # Look for accounts that received SOL from the master wallet
                                    if pubkey != master_wallet:
                                        diff = post_balances[i] - pre_balances[i]
                                        if diff > 0: # Balance increased (the recipient/child wallet)
                                            child_wallets.add(pubkey)
                except Exception as e:
                    pass
                
                await asyncio.sleep(0.1) # Rate limit protection

            print(f"\n🔍 Discovered {len(child_wallets)} Associated Child/Burner Wallets:")
            for wallet in child_wallets:
                print(f"  - {wallet}")

if __name__ == "__main__":
    # Insert the master funder address you just discovered
    master_address = "25eWhbfuyERqRUADXs4h3hAhGpL8wRotUGEyKQenav5y"
    asyncio.run(map_funder_cluster(master_address))