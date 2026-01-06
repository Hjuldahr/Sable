# Sable
_A Dynamic Discord Chat Agent_

Sable is a for-fun Discord chat agent powered by a locally hosted, quantized LLM.\
It’s designed for experimentation, learning, and personal server use.

## Tech Stack
- **Python:** 3.12.*
- **Database:** Async SQLite (aiosqlite)
- **Discord API:** discord.py
- **LLM:** Local Quantized Mistral (mistral-7b-instruct-v0.1.Q4_K_M.gguf)
- **Inference:** llama-cpp-python

## Installation
### 1. Discord App Setup
- Go to **Discord Developers**: https://discord.com/developers/applications
- Create a **New Application** or select an existing one.
- Under **OAuth2**, copy the **Client ID** (optional).
- Under **Bot**, copy the **Bot Token** (use Reset Token if hidden).
> ⚠️ Do not share your bot token. Save it securely (e.g., in a .txt file).

### 2. Discord Bot Installation
- Under **Installation**, copy the provided **Install Link**.
- Open the link and select your **server**.
- Approve **permission requests**.
- Bot appears in the **server** with an `APP` indicator and matching role.
> Initial status: **Offline** ⚫

### 3. Environment Variables (.env)
- Create a **.env** file in the **project root**:
```
MASTER_ID=Your_Discord_ID
BOT_ID=Your_Client_ID
DISCORD_BOT_TOKEN=Your_Bot_Token
```
- IDs can be copied using **Developer Mode**: **⚙ (User Settings)** → **⋯ Advanced**.
- **DISCORD_BOT_TOKEN** comes from Step 1.

### 4. Python Environment
- Install **Python 3.12.\*** from https://www.python.org/downloads/release/python-31210/\
- Install **dependencies**:
`pip install aiosqlite aiofiles llama-cpp-python discord.py python-dotenv markitdown nltk urlextract`
- Or via **requirements.txt**: 
`pip install -r requirements.txt`
### 5. Language Model
- Download **Mistral 7B Instruct (GGUF, Q4_K_M)**:\
Source: https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.1-GGUF/blob/main/mistral-7b-instruct-v0.1.Q4_K_M.gguf\
Direct: [Click here to download](https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.1-GGUF/resolve/main/mistral-7b-instruct-v0.1.Q4_K_M.gguf)
- Move file to **model/** (directory tracked with .gitkeep).

### 6. Initialization 
Run: `python Client.py`
Creates: data/database.db (deleting resets DB).

## Starting the Bot
Run: `python Client.py`
  
**Performs:**
1. Load .env
2. Connect to SQLite
3. Initialize DB schema if needed
4. Load Mistral LLM and tokenizer
5. Start thread pool executor
6. Connect to Discord
> Bot status: **Online** 🟢

## Stopping the Bot
- Press `Ctrl + C` or close terminal.

## Disclaimer & Usage
- For personal, educational, or experimental use only.
- Not intended for commercial use.
- Fork or attribute clearly if redistributed.
- Active development; use at your own risk.
- Comply with Discord's Terms of Service and community guidelines.
- May include third-party libraries; review licenses.