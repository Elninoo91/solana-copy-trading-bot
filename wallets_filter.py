import os
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()

HELIUS_KEY = os.getenv("HELIUS_API_KEY")
if not HELIUS_KEY:
    raise ValueError("Missing HELIUS_API_KEY in .env file!")

HELIUS_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_KEY}"

BURNER_WALLETS = [
    "EH34x9kgcyHeSed1dPaqQNBwLkxHc3eWo344R9rmmpS5",
    "8YCxJkYSGYsEryfnZo2UHNEyJeN5gq7w4Nm6RonNUTbb",
    "Apbe7Pq6t1dH8CHedD6SdosacBoZzxRRA4yjaAvBWpJr",
    "E4Mx3yQtKzneLv7HTAmv95pNWBynp2vUkpNA2UDdKfd9",
    "Djrs98vijhNgv1eHPyJhZHLJs9iUP6LkpDG84phurfEJ",
    "F1ruWR5JrHQv9K5Xf2mqrPxDZm3GPUiueadgvf6h3fo5",
    "9D3MwCCWnTfst2z3ewzeZ5fGqzCCQ3nCzs77jStndRGF",
    "8PRC1PMEFRt1ApHYvVnW7hu2Tprpx6asm5BBKafhiNTa",
    "3c7Bz6b689k1zzu8LtofmUDMP3fJpmYHUdt9kaLdko6v",
    "7nFDr1j9YUi2HTupUTBqNyyGRcaHbhV3soT9WPbNxcjB",
    "5L7aqweEkQWzogyyqi1xs2oU2ePseSXQnpnxYrg2aBUD",
    "6YPFWR6W6okZTJizxjJY4UCHDJ3qAh9NSzcrQhNLnQUB",
    "5cUAHhwixCtjzjUcqGJXv6C25WwDo9WJy6zSTMwc5WZp",
    "6MwjTEbAg3svS5ipYYos5tUGLSU9q6qCRmm7ystGcX4G",
    "ByekrBF3JF1i8Rg4AHqcuM8mkQGnP9b9GFvwNGpUbdXm",
    "7pgqkaHDD6mx499gM3PdZpq22Pbjmtfu2ZzFsCP1qdBC",
    "9v5AJ8rNf2hujUW9omjQUhUwPAXGEwBzKENERAsuzRCH",
    "BUJtjVKAGUWRTu9MuT9Xx3CqdaGgkQ3H9pSHJM552X75",
    "HmFKsNwjEuugdY1VU6mMiSprWMGeAf9ok2XrE9fjCNzg",
    "91h2e7BrQQyBUY9Wx2Fm6ZzAVRcK7nBKGmdb4sa6AAea",
    "FFUKcL3oexnLR7eRnBiVw1F1m4e9wwn8p7XKMg3g4Kyx",
    "CaTeyM8FkPNzhyiTHvML6UrQepqmjJdbPiNQozZTHCNA",
    "ENkuyhAZTkYcL5aTwUUmJW8gA3u7d74Qug4YgpL4t2cp",
    "6dnsUxJSmjzWnFhaSDv4WDS9nsgHjwGaSsnXsc8qxgBQ",
    "H2v6GnLGFmXwBz1WCpj8R6SXdQaaf9NnVVXbfS5AjJA8",
    "D3fNSYEWKtZWWjrLmi8V5hmZpw9Rz6ZAA6C9m3fRyuwu",
    "GV6LPgAgLggNY5JSzSRjTnTD9PPJP9crhU5M8C3fVyu6",
    "C6RC7mgqMovNcGcHEbhLBnzuBKkRAeSZs4xo9hb1o2h3",
    "Cv6LD3whmERdLgQtazdS8T1QAUoDEQFSUDmEotm5MwNV",
    "GUumMSrVQcnxfcrvPMERS6C3p1JCawR2asXhdm3tTVGf",
    "6eawgvcYor9W3W38T1N9HtqPHuQiPVKG8vQ4tBE2MnKs",
    "2sP7bkmA8Pg2yRszRqt2k2CHhWD5LXBcMWtZMywbis9F",
    "2eCVX8mhGX6vStGJ2qkQJDDeyn2Hkvy36AXVzDrJy6wp",
    "DayGtZntb57LTxEmp1Urgszo3j3tCm8AsPzKWPS7oZXd",
    "2RhacMNmhwWwtL4ej5aZeedBMGcXjLKZTFJCwCmaxTS6",
    "GZGsvnRCsPNCUq1PsZXp5ojm5Ue5mg1wHwrAKkShTjQU",
    "G5tEVQBbeHNup3vsh94PaTxHMVNKBgqp1yzEBXA4gxNo",
    "7as6RdU5Luxe3d1b6Tp5momaBc8g29pbZAY5xNcATTpo",
    "DWFAorWkoGpkZ7fkhPHXypEC87TQ53o3yDBJSndMeath",
    "6CygDxGUQzAZ1aEzA6CYRBoSmNwWyQNnCaGeVnGNcRGp",
    "6i5zPeqL88XQwU7fSXG3MrDJxnSefZKQfk2ZvgVAKjAK",
    "9TNjrggwKoXcyKsu2amKkFy8G4EqB22oe9S9Xae1x99",
    "9S19tNJpnCx7VuV1R9tq2SKx7zzPFif9med8XiwMJRaC",
    "AvQHnet5aWcDYqf4cJMNrZReXfrGX43v2oBKqVsMptsa",
    "Pbb1KmwvLF3NjCYQ69Z7aEvjufcVs1N2J4mC2fQTVoN",
    "3iBBVbmzPmcYxdesPSwvfbCfJ2kAyN58awnL7eMNxc7n",
    "HD5hymEiHxTRd6Yo7iNtnp9GnySMYKvEM9pMqPgV4pYW",
    "66jdMugVwyTKMkepHzDypaMcdRaXAx8hDt21yyyVQJbA",
    "9tZEbZuCiYJUp1tuqeEJjpq2nbpuiyAWbMXC29M4WtWg",
    "HLAvp2JwTYGq7i1DtGmXyLRX3Sfc3J4sWK8LAYW6VcNm",
    "2RSme8ZN47Uj64ZswjEupNZ7Mt9WLKDhkUZCcmRZenY2",
    "3C9WuyRXr2f4DVkxTLoKqEQ2jntpYa4X1p4XLMJD7UP4",
    "bqv2ZkF67MhKaVBivK6b6J1vrpLbjpJiDEpXAR9vv6o",
    "9jyJ52CynttW3EqncHN3tRho6dgAUdgiV4fBUPKFdAin",
    "6RCthnApxW5G983diKYPH4FndPTc3Yi9JPHuUbavBcy5",
    "D6z3xwSLhfMA8dKmoeq8iNtHbLKYEvQmM1iiYXEazAfr",
    "5Z3CEFVvaCrXvoNWfy4PiXuTZ3JGzx9U9WsdpEgLorUf",
    "HeYEZu42pZkZbn6T7zguCL6sXpGckrJvpvsgaoA3hRdo"
]

async def check_wallet_activity(session, wallet):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignaturesForAddress",
        "params": [wallet, {"limit": 5}]
    }
    
    try:
        async with session.post(HELIUS_RPC_URL, json=payload) as res:
            data = await res.json()
            signatures = data.get("result", [])
            if signatures:
                return wallet, True, len(signatures)
    except Exception:
        pass
    return wallet, False, 0

async def filter_and_save_wallets():
    print(f"Filtering {len(BURNER_WALLETS)} burner wallets for recent activity...")
    
    active_wallets = []
    
    async with aiohttp.ClientSession() as session:
        tasks = [check_wallet_activity(session, wallet) for wallet in BURNER_WALLETS]
        results = await asyncio.gather(*tasks)
        
        for wallet, is_active, count in results:
            if is_active:
                print(f"  [ACTIVE] {wallet} ({count} recent txs)")
                active_wallets.append(wallet)
            else:
                print(f"  [DEAD/DORMANT] {wallet}")
                
    filename = "vetted_burners.txt"
    with open(filename, "w") as f:
        for w in active_wallets:
            f.write(f"{w}\n")
            
    print(f"\nSaved {len(active_wallets)} active wallets to '{filename}' successfully!")

if __name__ == "__main__":
    asyncio.run(filter_and_save_wallets())



