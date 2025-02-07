import os
import re
from dotenv import load_dotenv
from web3 import Web3
from langchain.tools import Tool
from langchain.agents import initialize_agent
from langchain.llms import OpenAI
from langchain.agents import AgentType
from langchain_openai import ChatOpenAI
import json

# Load environment variables
load_dotenv()

# Mezo Testnet RPC
RPC_URL = "https://rpc.test.mezo.org"
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

if not PRIVATE_KEY:
    raise ValueError("PRIVATE_KEY not found in environment variables!")

web3 = Web3(Web3.HTTPProvider(RPC_URL))
account = web3.eth.account.from_key(PRIVATE_KEY)
sender_address = account.address

MUSD_ADDRESS = "0x637e22A1EBbca50EA2d34027c238317fD10003eB"  

# ERC-20 ABI (Minimal for transfers)
ERC20_ABI = json.loads('[{"constant": false, "inputs": [{"name": "recipient", "type": "address"},{"name": "amount", "type": "uint256"}],"name": "transfer","outputs": [{"name": "", "type": "bool"}],"stateMutability": "nonpayable","type":"function"}]')

# Create mUSD contract instance
musd_contract = web3.eth.contract(address=MUSD_ADDRESS, abi=ERC20_ABI)


def send_mezo_transaction(prompt: str) -> str:
    """
    Parses a prompt and sends a transaction on the Mezo Matsnet Testnet.
    Example prompt: "Send 0.01 BTC to 0x123456..."
    """
    match = re.search(r"send (\d*\.?\d*) BTC to (0x[a-fA-F0-9]{40})", prompt, re.IGNORECASE)
    if not match:
        return "Invalid format. Use 'Send <amount> BTC to <Mezo Address>'." #Add a break in the langgraph loop here

    amount, recipient = match.groups()
    amount_wei = web3.to_wei(float(amount), "ether")

    nonce = web3.eth.get_transaction_count(sender_address)
    gas_price = web3.eth.gas_price

    tx = {
        "to": recipient,
        "value": amount_wei,
        "gas": 21000,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": 31611,  # Mezo Testnet Chain ID
    }

    signed_tx = account.sign_transaction(tx)
    tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)  

    return f"✅ Btc transaction successful! Hash: {tx_hash.hex()}"

def transfer_musd(prompt: str) -> str:
    """
    Parses a prompt and transfers mUSD from the user's wallet to a recipient.
    Example prompt: "Transfer 100 mUSD to 0xABC..."
    """
    match = re.search(r"transfer (\d*\.?\d*) musd to (0x[a-fA-F0-9]{40})", prompt, re.IGNORECASE)
    if not match:
        return "Invalid format. Use 'Transfer <amount> mUSD to <Mezo Address>'."  #Add a break in the langgraph loop here 

    amount_musd, recipient = match.groups()
    amount_musd_wei = int(float(amount_musd) * 10**18)  # Convert mUSD to 18 decimals

    nonce = web3.eth.get_transaction_count(sender_address)
    gas_price = web3.eth.gas_price

    # Build mUSD transfer transaction
    txn = musd_contract.functions.transfer(recipient, amount_musd_wei).build_transaction({
        "from": sender_address,
        "nonce": nonce,
        "gas": 50000,
        "gasPrice": gas_price,
    })

    signed_txn = web3.eth.account.sign_transaction(txn, PRIVATE_KEY)
    tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)

    return f"✅ mUSD Transaction successful! Hash: {tx_hash.hex()}"


# Define the btc transaction tool
transaction_tool = Tool(
    name="Mezo Transaction Sender",
    func=send_mezo_transaction,
    description="Send BTC on Mezo Matsnet. Example: 'Send 0.01 BTC to 0xABC123...'."
)

# Difine the musd transaction tool
musd_transfer_tool = Tool(
    name="mUSD Transfer",
    func=transfer_musd,
    description="Transfer mUSD to a Mezo address. Example: 'Transfer 100 mUSD to 0xABC123...'."
)

# Initialize Mezo Baller Agent 
llm = ChatOpenAI(temperature=0)  

agent = initialize_agent(
    tools=[transaction_tool, musd_transfer_tool],
    llm=llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True
)

# Run the agent with a natural language prompt
print("Mezo Agent Ready! Type your request:")

user_input = input("> ")
response = agent.run(user_input)
print(response)
