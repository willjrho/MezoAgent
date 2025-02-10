import os
import json
import time
from dotenv import load_dotenv
from web3 import Web3

# -----------------------------------------------------------------------------
# Setup and Configuration
# -----------------------------------------------------------------------------

# Load environment variables from .env file (ensure PRIVATE_KEY is defined there)
load_dotenv()

# Connect to Mezo Testnet RPC
RPC_URL = "https://rpc.test.mezo.org"
web3 = Web3(Web3.HTTPProvider(RPC_URL))
if not web3.is_connected():
    raise ConnectionError("Failed to connect to the RPC URL.")

# Retrieve the private key
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
if not PRIVATE_KEY:
    raise ValueError("PRIVATE_KEY not found in environment variables!")

# Create an account object from the private key
account = web3.eth.account.from_key(PRIVATE_KEY)
sender_address = account.address
print(f"Using wallet: {sender_address}")

# Token and Router Addresses
ROUTER_ADDRESS = "0xC2E61936a542D78b9c3AA024fA141c4C632DF6c1"    # New router address
MUSD_ADDRESS = "0x637e22A1EBbca50EA2d34027c238317fD10003eB"      # mUSD Token Address
WRAPPED_BTC_ADDRESS = "0xA460F83cdd9584E4bD6a9838abb0baC58EAde999" # Wrapped BTC Token Address

# Load the router ABI from file (ensure new_router_abi.json is in the same directory)
with open("new_router_abi.json", "r") as abi_file:
    router_abi = json.load(abi_file)

# Create a contract instance for the router
router_contract = web3.eth.contract(address=ROUTER_ADDRESS, abi=router_abi)

# -----------------------------------------------------------------------------
# ERC-20 Minimal ABI (for approve and allowance)
# -----------------------------------------------------------------------------
ERC20_ABI = json.loads(
    '[{"constant": false, "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],'
    '"name": "approve", "outputs": [{"name": "", "type": "bool"}], "stateMutability": "nonpayable", "type": "function"},'
    '{"constant": true, "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],'
    '"name": "allowance", "outputs": [{"name": "remaining", "type": "uint256"}], "stateMutability": "view", "type": "function"}]'
)

# Create a contract instance for the mUSD token
musd_contract = web3.eth.contract(address=MUSD_ADDRESS, abi=ERC20_ABI)

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

def approve_if_needed(token_contract, amount_wei):
    """
    Checks if the router has enough allowance to spend tokens.
    If not, sends an approval transaction.
    """
    current_allowance = token_contract.functions.allowance(sender_address, ROUTER_ADDRESS).call()
    if current_allowance < amount_wei:
        print(f"Current allowance ({current_allowance}) is less than required ({amount_wei}). Approving...")
        nonce = web3.eth.get_transaction_count(sender_address)
        gas_price = web3.eth.gas_price
        
        approve_tx = token_contract.functions.approve(ROUTER_ADDRESS, amount_wei).build_transaction({
            "from": sender_address,
            "nonce": nonce,
            "gas": 50000,  # Typical gas limit for an ERC-20 approval
            "gasPrice": gas_price,
        })
        
        signed_tx = web3.eth.account.sign_transaction(approve_tx, PRIVATE_KEY)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            raise Exception("Approval transaction failed.")
        print(f"Approval successful. TX Hash: {tx_hash.hex()}")
    else:
        print("Sufficient allowance already set.")

def swap_musd_for_wrapped_btc(amount_musd, min_wrapped_btc):
    """
    Swaps mUSD for Wrapped BTC using the router.
    
    :param amount_musd: Amount of mUSD to swap (in human-readable form).
    :param min_wrapped_btc: Minimum acceptable Wrapped BTC to receive (in human-readable form).
    :return: Transaction receipt.
    """
    # Convert amounts to Wei (assuming 18 decimals for both tokens)
    amount_musd_wei = int(amount_musd * 10**18)
    min_wrapped_btc_wei = int(min_wrapped_btc * 10**18)
    deadline = int(time.time()) + 600  # Deadline set to 10 minutes from now
    
    # Approve router to spend mUSD if needed
    approve_if_needed(musd_contract, amount_musd_wei)
    
    # Define the swap path: mUSD -> Wrapped BTC (adjust if an intermediary is needed)
    path = [MUSD_ADDRESS, WRAPPED_BTC_ADDRESS]
    
    nonce = web3.eth.get_transaction_count(sender_address)
    gas_price = web3.eth.gas_price
    
    # Build the swap transaction
    swap_tx = router_contract.functions.swapExactTokensForTokens(
        amount_musd_wei,        # mUSD amount
        min_wrapped_btc_wei,     # Minimum Wrapped BTC to receive (to protect against slippage)
        path,                   # Swap path
        sender_address,         # Recipient of Wrapped BTC
        deadline                # Transaction deadline
    ).build_transaction({
        "from": sender_address,
        "nonce": nonce,
        "gasPrice": gas_price,
    })
    
    # Estimate gas usage and add a small buffer
    try:
        estimated_gas = web3.eth.estimate_gas(swap_tx)
        swap_tx["gas"] = estimated_gas + 10000
        print(f"Estimated gas: {estimated_gas}, using gas limit: {swap_tx['gas']}")
    except Exception as e:
        print(f"Gas estimation failed: {e}. Using default gas limit of 250000.")
        swap_tx["gas"] = 250000
    
    signed_swap_tx = web3.eth.account.sign_transaction(swap_tx, PRIVATE_KEY)
    tx_hash = web3.eth.send_raw_transaction(signed_swap_tx.raw_transaction)
    print(f"Swap transaction sent. TX Hash: {tx_hash.hex()}")
    
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    print("Swap transaction receipt:")
    print(f"  Transaction Hash: {receipt.transactionHash.hex()}")
    print(f"  Gas Used: {receipt.gasUsed}")
    print(f"  Status: {'Success' if receipt.status == 1 else 'Failed'}")
    
    return receipt

# -----------------------------------------------------------------------------
# Main Execution
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    # Swap 15 mUSD for Wrapped BTC (with a very small minimum amount to avoid revert).
    # Adjust min_wrapped_btc as needed for your slippage tolerance.
    try:
        swap_receipt = swap_musd_for_wrapped_btc(15, 0.000000000000001)
    except Exception as err:
        print(f"An error occurred during the swap: {err}")
