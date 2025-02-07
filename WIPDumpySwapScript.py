import os
import json
from dotenv import load_dotenv
from web3 import Web3
import time

# Load environment variables (private key, RPC URL)
load_dotenv()

# Mezo Testnet RPC Connection
RPC_URL = "https://rpc.test.mezo.org"
web3 = Web3(Web3.HTTPProvider(RPC_URL))

# User Wallet
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
if not PRIVATE_KEY:
    raise ValueError("PRIVATE_KEY not found in environment variables!")

account = web3.eth.account.from_key(PRIVATE_KEY)
sender_address = account.address

# Dumpy Router Contract (Basic)
UNISWAP_V2_ROUTER = "0xe3eB6Aa5CFB0BdA17C22128A58830EBC8Ecb74C3"

# Token Addresses (Mezo Testnet)
MUSD_ADDRESS = "0x637e22A1EBbca50EA2d34027c238317fD10003eB"  
BTC_ADDRESS = "0x7b7C000000000000000000000000000000000000"  

# Load Dumpy V2 Router ABI
with open("new_router_abi.json") as f:
    uniswap_abi = json.load(f)

router_contract = web3.eth.contract(address=UNISWAP_V2_ROUTER, abi=uniswap_abi)

# ERC-20 ABI (Minimal for approvals & balance checks)
ERC20_ABI = json.loads('[{"constant": false, "inputs": [{"name": "spender", "type": "address"},{"name": "amount", "type": "uint256"}],"name": "approve","outputs": [{"name": "", "type": "bool"}],"stateMutability": "nonpayable","type":"function"}, {"constant": true, "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],"name": "allowance","outputs": [{"name": "remaining", "type": "uint256"}],"stateMutability": "view","type":"function"}]')

# Create mUSD contract instance
musd_contract = web3.eth.contract(address=MUSD_ADDRESS, abi=ERC20_ABI)


# Approve Dumpy V2 Router to Spend mUSD 
def approve_if_needed(token_contract, token_address, amount_wei):
    """
    Checks if the Uniswap V2 Router has enough allowance to spend the tokens.
    If not, it approves the router.
    """
    allowance = token_contract.functions.allowance(sender_address, UNISWAP_V2_ROUTER).call()
    
    if allowance < amount_wei:
        print(f"🔹 Approval required: {allowance} < {amount_wei}")
        
        nonce = web3.eth.get_transaction_count(sender_address)
        gas_price = web3.eth.gas_price

        txn = token_contract.functions.approve(UNISWAP_V2_ROUTER, amount_wei).build_transaction({
            "from": sender_address,
            "nonce": nonce,
            "gas": 50000,
            "gasPrice": gas_price,
        })

        signed_txn = web3.eth.account.sign_transaction(txn, PRIVATE_KEY)
        tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)
        web3.eth.wait_for_transaction_receipt(tx_hash)

        print(f"✅ Approval successful! Transaction hash: {tx_hash.hex()}")
    else:
        print(f"✅ Router already has enough allowance: {allowance} >= {amount_wei}")


# Swap mUSD for BTC on Dumpy Router Basic 
def swap_musd_for_wbtc(amount_musd, min_wbtc_out):
    """
    Swaps mUSD for BTC on Dumpy.
    """
    amount_musd_wei = int(amount_musd * 10**18)  
    min_out_wei = int(min_wbtc_out * 10**18)  
    deadline = int(time.time()) + 600  # 10 minutes from now

    # Ensure the router has approval
    approve_if_needed(musd_contract, MUSD_ADDRESS, amount_musd_wei)

    # Swap on dumpy 
    path = [MUSD_ADDRESS, BTC_ADDRESS] #path issue?

    txn = router_contract.functions.swapExactTokensForTokens(
        amount_musd_wei,  # Amount In (mUSD)
        min_out_wei,  # Min Amount Out (BTC) - Adjust for slippage
        path,  # Swap Path
        sender_address,
        deadline
    ).build_transaction({
        "from": sender_address,
        "nonce": web3.eth.get_transaction_count(sender_address),
        "gas": 250000,
        "gasPrice": web3.eth.gas_price,
    })

    signed_txn = web3.eth.account.sign_transaction(txn, PRIVATE_KEY)
    tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)

    print(f"✅ Swap transaction sent! TX Hash: {tx_hash.hex()}")

    # Wait for the transaction to be mined & get the receipt
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

    # Print transaction receipt details
    print("\n🔍 **Transaction Receipt:**")
    print(f"  📌 Transaction Hash: {receipt.transactionHash.hex()}")
    print(f"  ⛽ Gas Used: {receipt.gasUsed}")
    print(f"  ✅ Status: {'Success' if receipt.status == 1 else 'Failed'}")
    
    if receipt.status == 0:
        transaction = web3.eth.get_transaction(tx_hash)
        try:
            if transaction.input:
                decoded_input = router_contract.decode_function_input(transaction.input)
                print(f"  📄 Function: {decoded_input}")
        except Exception as e:
            print(f"  ❌ Error decoding function input: {e}")
    else: 
        print("Tx successful")


    if receipt.logs:
        print(f"  📜 Logs: {receipt.logs}") #returns nothing hits the else condition everytime
    else:
        print("  🚫 No logs emitted by this transaction.") 

    return receipt



swap_musd_for_wbtc(15, 0.000000000000001)  
