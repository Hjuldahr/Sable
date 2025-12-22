# Sable
A Dynamic Discord Chat Agent

## Tech Stack
- Async SQLite (aiosqlite)
- Discord API (discord)
- Local Quantized Mistral LLM (mistral-7b-instruct-v0.1.Q4_K_M.gguf)
- Python3 (python 3.12.*)

## Installation
### Discord Bot
1. Go to [Discord Developers](https://discord.com/developers/applications)\
2. Use *New Application*, or select the application if it already exists.\
3. Write down the *Client ID* under *OAuth2*.\
4. Write down the bot *Token* under *Bot*. (Use 'Reset Token' if you can't see it)

### .env File
Create a *.env* file under the project's root directory\
```
BOT_ID=Insert Client ID Here
DISCORD_BOT_TOKEN=Insert Bot Token Here
```
The resulting .env should match the above format with the values substituted as indicated.

### Python Environment
Download then install [Python 3.12.*](https://www.python.org/downloads/release/python-31210/)\
Open your preferred developement terminal then execute:\
`pip install aiosqlite`\
`pip install llama-cpp-python`\
`pip install discord.py`\
or\
`pip install -r requirements.txt`

### LLM
Download the [Mistral LLM](https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.1-GGUF/resolve/main/mistral-7b-instruct-v0.1.Q4_K_M.gguf) then move it to [model\\...](model\.gitkeep)

### Initialization
Run App.py\
_This will generate data\database.db file if it does not existt_

## Disclaimer & Usage
This project is for personal, educational, or experimental use only. It is not intended for commercial usage or monetization.

If you intend to adapt or redistribute this project, please fork the repository or credit the original creator in code comments and documentation.

This project is currently under developement and is without any warranty. Use at own risk.

Users are responsible for ensuring their use of this project complies with Discord’s ToS.

This project may include third-party APIs; please follow their respective licenses.