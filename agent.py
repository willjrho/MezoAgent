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
account = web3.eth.account.from_key(PRIVATE_KEY)
sender_address = account.address

#mUSD Contract Setup
MUSD_ADDRESS = "0x637e22A1EBbca50EA2d34027c238317fD10003eB"  
ERC20_ABI = json.loads('[{"constant": false, "inputs": [{"name": "recipient", "type": "address"},{"name": "amount", "type": "uint256"}],"name": "transfer","outputs": [{"name": "", "type": "bool"}],"stateMutability": "nonpayable","type":"function"}]')
musd_contract = web3.eth.contract(address=MUSD_ADDRESS, abi=ERC20_ABI)

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

#Initialize Mezo Baller Agent
agent = initialize_agent(
    tools=[mezo_agent_transaction_tool_btc, mezo_agent_transaction_tool_musd],
    llm=llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True
)


#Run Mezo Agent
print("Mezo Agent Ready! Type your request:")

user_input = input("> ")
response = agent.run(user_input)
print(response)
