import os
import re
from dotenv import load_dotenv
from web3 import Web3
from langchain.tools import Tool
from langchain.agents import initialize_agent
from langchain.llms import OpenAI
from langchain.agents import AgentType
from langchain_openai import ChatOpenAI
from langchain.output_parsers import StructuredOutputParser, ResponseSchema
from langchain.prompts import PromptTemplate
import json
import time

# Load environment variables
load_dotenv()

#Check for keys
OpenAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OpenAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in environment variables!")

PRIVATE_KEY = os.getenv("PRIVATE_KEY")

if not PRIVATE_KEY:
    raise ValueError("PRIVATE_KEY not found in environment variables!")

# Mezo Testnet RPC
RPC_URL = "https://rpc.test.mezo.org"
web3 = Web3(Web3.HTTPProvider(RPC_URL))

#Create Account Object
account = web3.eth.account.from_key(PRIVATE_KEY)
sender_address = account.address

#mUSD Contract Setup
MUSD_ADDRESS = "0x637e22A1EBbca50EA2d34027c238317fD10003eB"  
ERC20_ABI = json.loads(
    '[{"constant": false, "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],'
    '"name": "approve", "outputs": [{"name": "", "type": "bool"}], "stateMutability": "nonpayable", "type":"function"},'
    '{"constant": true, "inputs": [{"name": "owner", "type": "address"}],'
    '"name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "stateMutability": "view", "type": "function"},'
    '{"constant": true, "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],'
    '"name": "allowance", "outputs": [{"name": "remaining", "type": "uint256"}], "stateMutability": "view", "type": "function"}]'
)

musd_contract = web3.eth.contract(address=MUSD_ADDRESS, abi=ERC20_ABI)

#wBTC and router 
WRAPPED_BTC_ADDRESS = "0xA460F83cdd9584E4bD6a9838abb0baC58EAde999" 
ROUTER_ADDRESS = "0xC2E61936a542D78b9c3AA024fA141c4C632DF6c1"    

#Load router ABI 
with open("new_router_abi.json", "r") as abi_file:
    router_abi = json.load(abi_file)

#Router contract connection 
router_contract = web3.eth.contract(address=ROUTER_ADDRESS, abi=router_abi)

#Define structured output schema for swaps 
swap_response_schemas = [
    ResponseSchema(name="amount", description="The amount of mUSD to swap."),
    ResponseSchema(name="from_currency", description="The token to swap from (should always be 'mUSD')."),
    ResponseSchema(name="to_currency", description="The token to receive (should always be 'BTC')."),
    ResponseSchema(name="router_address", description="The Dumpy Swap router address for executing the swap.")
]

#Create swap output parser
swap_output_parser = StructuredOutputParser.from_response_schemas(swap_response_schemas)

#Define swap prompt template to parse swap prompts 
swap_prompt_template = PromptTemplate(
    template="""
    Extract swap transaction details from this request:
    {input}

    - The token to swap from should always be 'mUSD'.
    - The token to receive should always be 'BTC'.
    - The router address should always be '0xC2E61936a542D78b9c3AA024fA141c4C632DF6c1'.
    
    {format_instructions}
    """,
    input_variables=["input"],
    partial_variables={"format_instructions": swap_output_parser.get_format_instructions()},
)


#Parse swap prompts 
def extract_swap_details(prompt: str):
    """
    Uses LLM to extract structured swap transaction details from user input.
    """
    formatted_prompt = swap_prompt_template.format(input=prompt)
    response = llm.invoke(formatted_prompt)

    try:
        extracted_data = swap_output_parser.parse(response.content)
        return extracted_data
    except Exception as e:
        return f"Failed to extract swap details: {str(e)}"
    
#Swap approval helper function
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

def swap_musd_for_wrapped_btc(prompt: str) -> str:
    """
    Parses a prompt sent by the agent, extracts swap details using the LLM, 
    and executes a swap from mUSD to Wrapped BTC via Dumpy Swap.
    """
    print(f"📥 Received swap request: {prompt}")

    # ✅ Step 1: Extract swap transaction details using LLM
    transaction_details = extract_swap_details(prompt)
    
    if isinstance(transaction_details, str):  # Handle parsing errors
        return transaction_details

    # ✅ Step 2: Extract parsed swap details
    amount_musd = float(transaction_details["amount"])
    from_currency = transaction_details["from_currency"].lower()
    to_currency = transaction_details["to_currency"].lower()
    router_address = transaction_details["router_address"]

    # ✅ Step 3: Validate that swap is mUSD → BTC
    if from_currency != "musd" or to_currency != "btc":
        return "❌ This function only supports swapping mUSD for BTC."

    print(f"🔄 Swapping {amount_musd} mUSD for BTC via {router_address}")

    # ✅ Step 4: Convert values to Wei (18 decimals for mUSD and BTC)
    amount_musd_wei = int(amount_musd * 10**18)
    min_wrapped_btc_wei = int(0.000000000000001 * 10**18)  # Minimal value to prevent failure
    deadline = int(time.time()) + 600  # 10-minute transaction deadline

    # ✅ Step 5: Check sender's balance
    sender_balance = musd_contract.functions.balanceOf(sender_address).call()
    sender_balance_musd = sender_balance / 10**18

    if sender_balance < amount_musd_wei:
        return f"❌ Insufficient balance! You have {sender_balance_musd} mUSD, but you need {amount_musd} mUSD."

    # ✅ Step 6: Approve mUSD spending if needed
    approve_if_needed(musd_contract, amount_musd_wei)

    # ✅ Step 7: Define swap path (mUSD → Wrapped BTC)
    path = [MUSD_ADDRESS, WRAPPED_BTC_ADDRESS]

    # ✅ Step 8: Get nonce and gas price
    nonce = web3.eth.get_transaction_count(sender_address)
    gas_price = web3.eth.gas_price

    try:
        # ✅ Step 9: Build the swap transaction
        swap_tx = router_contract.functions.swapExactTokensForTokens(
            amount_musd_wei,  # Amount of mUSD to swap
            min_wrapped_btc_wei,  # Minimum Wrapped BTC to receive
            path,  # Swap path
            sender_address,  # Recipient (sender receives the Wrapped BTC)
            deadline  # Deadline for the transaction
        ).build_transaction({
            "from": sender_address,
            "nonce": nonce,
            "gasPrice": gas_price,
        })

        # ✅ Step 10: Estimate gas and adjust with a buffer
        estimated_gas = web3.eth.estimate_gas(swap_tx)
        swap_tx["gas"] = estimated_gas + 10000  # Add buffer

        print(f"Estimated gas: {estimated_gas}, using gas limit: {swap_tx['gas']}")

    except Exception as e:
        print(f"⚠️ Gas estimation failed: {e}. Using default gas limit of 250000.")
        swap_tx["gas"] = 250000  # Default gas if estimation fails

    try:
        # ✅ Step 11: Sign and send transaction
        signed_swap_tx = web3.eth.account.sign_transaction(swap_tx, PRIVATE_KEY)
        tx_hash = web3.eth.send_raw_transaction(signed_swap_tx.raw_transaction)

        print(f"✅ Swap transaction sent! TX Hash: {tx_hash.hex()}")

        # ✅ Step 12: Wait for confirmation
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        print("✅ Swap transaction confirmed!")
        print(f"  Transaction Hash: {receipt.transactionHash.hex()}")
        print(f"  Gas Used: {receipt.gasUsed}")
        print(f"  Status: {'Success' if receipt.status == 1 else 'Failed'}")

        return f"✅ Swap successful! {amount_musd} mUSD swapped for BTC on Dumpy Swap. TX Hash: {tx_hash.hex()}"

    except Exception as e:
        print(f"❌ Swap transaction failed: {str(e)}")
        return f"❌ Swap transaction failed: {str(e)}"
#Define Structured Output Parser Schema 
response_schemas = [
    ResponseSchema(name="amount", description="The amount of cryptocurrency to transfer."),
    ResponseSchema(name="currency", description="The cryptocurrency to transfer (BTC, mUSD, ect.)"),
    ResponseSchema(name="recipient", description="The recipient's Mezo address."),
]

output_parser = StructuredOutputParser.from_response_schemas(response_schemas=response_schemas)

#Define LLM and Prompt for Parsing Transactions
llm = ChatOpenAI(temperature=0, openai_api_key=OpenAI_API_KEY)

prompt_template = PromptTemplate(
    template = "Extract transaction details from this request:\n{input}\n{format_instructions}",
    input_variables=["input"],
    partial_variables={"format_instructions": output_parser.get_format_instructions()},
)

def extract_transaction_details(prompt:str):
    formatted_prompt = prompt_template.format(input=prompt)
    response = llm.invoke(formatted_prompt)

    try:
        extracted_data = output_parser.parse(response.content)
        return extracted_data
    except Exception as e:
        return f"Failed to extract transaction details: {str(e)}"
    
#BTC Transaction Function w/ Structured Parsing
def mezo_agent_transaction_btc(prompt: str) -> str:
    transaction_details = extract_transaction_details(prompt)

    if isinstance(transaction_details, str):
        return transaction_details
    
    amount = float(transaction_details["amount"])
    currency = transaction_details["currency"].lower()
    recipient = transaction_details["recipient"]

    if currency != "btc":
        return "This function only handles BTC transactions."
    
    amount_wei = web3.to_wei(amount, "ether")
    nonce = web3.eth.get_transaction_count(sender_address)
    gas_price = web3.eth.gas_price
    gas_limit = web3.eth.estimate_gas({"to": recipient, "value": amount_wei, "from": sender_address})

    tx = {
        "to": recipient,
        "value": amount_wei,
        "gas": gas_limit,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": 31611,
    }

    try:
        signed_tx = account.sign_transaction(tx)
        tx_hash = web3.eth.send_raw_transaction(signed_tx.raw_transaction)
        return f"✅ BTC transaction successful! Hash: {tx_hash.hex()}"
    except Exception as e:
        return f"❌ Transaction failed: {str(e)}"

#mUSD Transaction Function w/ Structured Parsing
def mezo_agent_transaction_musd(prompt: str) -> str:
    transaction_details = extract_transaction_details(prompt)

    if isinstance(transaction_details, str):  # Error handling
        return transaction_details

    amount = float(transaction_details["amount"])
    currency = transaction_details["currency"].lower()
    recipient = transaction_details["recipient"]

    if currency != "musd":
        return "This function only handles mUSD transactions."

    amount_musd_wei = int(amount * 10**18)
    nonce = web3.eth.get_transaction_count(sender_address)
    gas_price = web3.eth.gas_price

    try:
        txn = musd_contract.functions.transfer(recipient, amount_musd_wei).build_transaction({
            "from": sender_address,
            "nonce": nonce,
            "gas": 50000,
            "gasPrice": gas_price,
        })

        signed_txn = web3.eth.account.sign_transaction(txn, account.key)
        tx_hash = web3.eth.send_raw_transaction(signed_txn.raw_transaction)

        return f"✅ mUSD Transaction successful! Hash: {tx_hash.hex()}"
    except Exception as e:
        return f"❌ Transaction failed: {str(e)}"


#Define Mezo Agent LangChain Tools 
mezo_agent_transaction_tool_btc = Tool(
    name="Mezo BTC Transaction Tool",
    func=mezo_agent_transaction_btc,
    description="Send BTC on Mezo Matsnet. Example: 'Send 0.01 BTC to 0xABC123...'."
)

mezo_agent_transaction_tool_musd = Tool(
    name="Mezo mUSD Transaction Tool",
    func=mezo_agent_transaction_musd,
    description="Transfer mUSD on Mezo Matsnet. Example: 'Transfer 100 mUSD to 0xABC123...'."
)

mezo_agent_musd_to_btc_dumpy_tool = Tool(
    name="Mezo mUSD to BTC Dumpy Swap Tool",
    func=swap_musd_for_wrapped_btc,
    description="Swap mUSD for Wrapped BTC using the Dumpy Swap router."
)

#Initialize Mezo Baller Agent
agent = initialize_agent(
    tools=[mezo_agent_transaction_tool_btc, mezo_agent_transaction_tool_musd, mezo_agent_musd_to_btc_dumpy_tool],
    llm=llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True
)

#Run Mezo Agent
print("Mezo Agent Ready! Type your request:")

user_input = input("> ")
response = agent.run(user_input)
print(response)
