# Sable
_A Dynamic Discord Chat Agent_

Sable is a for-fun Discord chat agent powered by a locally hosted, quantized LLM.  
It is designed for experimentation, learning, and personal server use.

## Tech Stack
- **Python**: 3.12.\*
- **Database**: Async SQLite (`aiosqlite`)
- **Discord API**: `discord.py`
- **LLM**: Local Quantized Mistral (`mistral-7b-instruct-v0.1.Q4_K_M.gguf`)
- **Inference**: `llama-cpp-python`

## Installation
### 1. Discord App Setup
1.  Go to **Discord Developers**  
    [https://discord.com/developers/applications](https://discord.com/developers/applications)
2.  Create a **New Application** (or select an existing one).
3.  Under **OAuth2**, copy the **Client ID**.
4.  Under **Bot**, copy the **Bot Token**\
(use **Reset Token** if it’s hidden).

>⚠️ **Do not share your bot token.**
### 2. Discord Bot Setup
1. Under **Installation**, copy the **Install Link** (Discord provided link, not Custom)
2. Follow the **Install Link**
3. Select the **Discord Server** you want to install the **Discord App**.
4. Approve the permission requests and accept.
5. The **App** you created earlier should now be visible on the **Server** as a user with an `APP` indicator next to it and a User Role matching the **App's** name.\
(The Bot's status should appear as `Offline` at this stage)

### 3. Environment Variables (.env)
***
Create a `.env` file in the project root:
```
BOT_ID=Insert_Client_ID_Here
DISCORD_BOT_TOKEN=Insert_Bot_Token_Here
```
Ensure the variable names match exactly.
### 4. Python Environment
***
Download and install **Python 3.12.\***  
[https://www.python.org/downloads/release/python-31210/](https://www.python.org/downloads/release/python-31210/)

From your development terminal:

`pip install aiosqlite`\
`pip install llama-cpp-python`\
`pip install discord.py`\
`pip install dotenv`\
`pip install markitdown`

Or install everything at once:

`pip install -r requirements.txt`

### 5. Language Model
***
Download the Mistral model:

- **Model**: Mistral 7B Instruct (GGUF, Q4\_K\_M)
- **Source**: [https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.1-GGUF/blob/main/mistral-7b-instruct-v0.1.Q4_K_M.gguf](https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.1-GGUF/blob/main/mistral-7b-instruct-v0.1.Q4_K_M.gguf)
- **Direct**: [Click here to download](https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.1-GGUF/resolve/main/mistral-7b-instruct-v0.1.Q4_K_M.gguf)
    
Move the file into:

`model/`

(The directory is tracked via `.gitkeep`.)
### 6. Initialization
***
Run the application:

`python Client.py`

On first launch, this will automatically create:

`data/database.db`

if it does not already exist.

## Starting the Bot
Run the application:

`python Client.py` 

This will attempt to perform the following:
1. Load the .env
2. Connect to SQLite
3. Initialize the SQLite database and schema as needed
4. Load the Mistral LLM and tokenizer into memory
5. Start a thread pool executor
6. Connect to the Discord Bot\
(If this worked, the Bot's Status will be `Online` instead of `Offline`)

## Stopping the Bot
Press `Ctrl + C` or close the terminal session (less recommended)

## Disclaimer & Usage
- This project is intended for **personal, educational, or experimental use only**.\
It is **not designed for commercial use or monetization**.
- If you adapt or redistribute this project, please **fork the repository** or provide **clear creator attribution** in documentation and/or code comments.
- This project is **under active development** and is provided **“as-is”**, without warranty of any kind.\
**Use at your own risk.**
- You are responsible for ensuring your usage complies with **Discord’s Terms of Service** and Community Guidelines.
- This project may include **third-party libraries or APIs**.\
Please review and comply with their respective licenses.