import os
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()

HELIUS_KEY = os.getenv("HELIUS_API_KEY")
if not HELIUS_KEY:
    raise ValueError("Missing HELIUS_API_KEY in .env file!")

HELIUS_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"

async def trace_wallet_funder(wallet_address):
    """
    Fetches the transaction history of a trader wallet and inspects 
    its oldest transaction to identify the source of initial SOL funding.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [
            wallet_address,
            {"limit": 1000}
        ]
    }
    
    async with aiohttp.ClientSession() as session:
        print(f"Fetching transaction history for: {wallet_address}")
        async with session.post(HELIUS_RPC_URL, json=payload) as res:
            data = await res.json()
            signatures = data.get("result", [])
            
            if not signatures:
                print("❌ No transactions found for this address.")
                return None
            
            # The oldest transaction is at the very end of the list
            oldest_sig_info = signatures[-1]
            sig = oldest_sig_info.get("signature")
            
            print(f"Analyzing oldest transaction signature: {sig}")
            
            tx_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTransaction",
                "params": [
                    sig,
                    {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
                ]
            }
            
            async with session.post(HELIUS_RPC_URL, json=tx_payload) as tx_res:
                tx_data = await tx_res.json()
                result = tx_data.get("result")
                
                if not result:
                    print("❌ Could not retrieve transaction details.")
                    return None
                
                account_keys = result.get("transaction", {}).get("message", {}).get("accountKeys", [])
                meta = result.get("meta", {})
                pre_balances = meta.get("preBalances", [])
                post_balances = meta.get("postBalances", [])
                
                if pre_balances and post_balances and account_keys:
                    for i, key_info in enumerate(account_keys):
                        pubkey = key_info.get("pubkey") if isinstance(key_info, dict) else key_info
                        if pubkey != wallet_address:
                            diff = post_balances[i] - pre_balances[i]
                            if diff < 0: # Balance decreased (the sender/funder)
                                print(f"\n🔍 Discovered Master/Funder Wallet: {pubkey}")
                                return pubkey
                                
                print("❌ Could not determine funding source from balance changes.")
                return None

if __name__ == "__main__":
    # Insert a trader's wallet address copied from DexScreener/GMGN
    target_wallet = "CFPu3CJjrj6tXwQCDH14e75UwcgX5mRng6SXzwxticZ6"
    
    if "ENTER" in target_wallet:
        print("CFPu3CJjrj6tXwQCDH14e75UwcgX5mRng6SXzwxticZ6")
    else:
        asyncio.run(trace_wallet_funder(target_wallet))