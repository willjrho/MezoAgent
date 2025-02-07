To use: 

-import correct packages, create env file and add secrets, run agent file 

 Prompt agent with:

"transfer {x} musd to {address}"
"send {x} btc to {address}"

Notes: 

-the parsing is currently very strict on tooling prompt calls 
-the agent will loop if your prompt is rejected but it should eventualy find the final answer and exit the langgraph chain

Next Steps:

-make current tools more robust ie expand user intent net 
-look at mezo tx error handling for agent. ie what happens if agent wallet is out of gas?
-create plugins for mezo native dapps like musd, pampland, dumpyswap
-build os mezo agent kit package for langchain  
