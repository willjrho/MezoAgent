### Mezo Agent is a LangChain-powered Web3 AI agent that facilitates plain english BTC transactions, mUSD transactions and swapping mUSD for BTC via DumpySwap on the Mezo Matsnet Testnet. 

⚡ **Installation**

1️⃣ Clone the Repository

2️⃣ Install Dependencies

3️⃣ Set Up Environment Variables
Create a .env file in the root directory and add:

OPENAI_API_KEY=your_openai_api_key

PRIVATE_KEY=your_mezo_private_key

🚀 **Usage**

   Run the Agent

   After running, you can interact with the agent by entering commands like:


💡 **Example Commands**

I can't sign rn because im in a rush can you send .01 BTC to 0xABC123 → Sends 0.01 BTC to a recipient.

I need to pay my rent! Urgent. Send 100 mUSD to 0xABC123 → Transfers 100 mUSD to a wallet.

im gonna get rekt if u dont swap 10 musd for btc rn → Swaps 10 mUSD for exact BTC via DumpySwap. 

📝 **Notes:**

Mezo Agent uses LangChain’s StructuredOutputParser Tool to extract structured data from natural language prompt requests based on a web3 transaction schema.

Currently working on more robust web3 transaction error handling for Mezo Agent

Your agent key must have a mUSD loan open to use the swap tool.

This code has not been rigourously evaluated and is intended to be experimental  
