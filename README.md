# AshnasBot
A simple twitch integration project to play with some python, very basic.

## Running

Requires Python 3.11+

```
git clone https://github.com/ashnasbot/ashnasbot.git
cd ashnasbot
git submodule init
git submodule update

python3 -m virtualenv env
# Windows
env\Scripts\activate.bat
# Linux
source env/bin/activate

pip install -r requirements.txt
```

```
python3 ./__main__.py
```

## Config
[Register your application on the Twitch dev portal](https://dev.twitch.tv/dashboard/apps/create) to get a client id and secret.

Create `config.json` in the project root (the server will generate a blank one on first run):

```json
{
    "client_id": "abcdef0123456789",
    "secret": "abcdef0123456789",
    "username": "my_bot_user",
    "log_level": "INFO"
}
```
- **client_id**: Required - App client ID from the developer portal
- **secret**: Required - App client secret from the developer portal
- **username**: Required - Username of the bot account
- **log_level**: Required - `"INFO"` if unsure
- **bttv**: Optional - `true` or `false` to show BTTV emotes in chat
- **chat_model**: Optional - HuggingFace model ID for the chatbot (default: `"Qwen/Qwen3.5-2B"`)
- **chat_model_quant**: Optional - Quantization mode: `"fp8"`, `"int8"`, `"int4"`, or `null` for none (default: `"fp8"`)

### Auth
Once running, authenticate via the browser:

- `http://localhost:8080/bot_auth` — authorise the bot account (grants chat read/write)
- `http://localhost:8080/user_auth` — authorise the broadcaster account (grants redemptions, follows, predictions)

Tokens are stored automatically and refresh in the background.

### Usage
Navigate to `http://localhost:8080` in a browser to open the dashboard, select a view and enter a channel name.

### Session Config
Each session keeps its own config, configured in the browser menu.
 -  **Allow commands**: Allow the bot to process and respond to !commands
 -  **Pull Avatars**: Some views show profile pictures (disable on busy channels to avoid rate limits)
 -  **Show Chat Notifications**: Show Sub and other alert messages in chat
 -  **Sounds**: Play sound effects on e.g. Subs
 -  **Show menu on load**: Shows the config menu when the page loads

## Known Issues
- Some substitutions not supported e.g. `<3` (not classed as an emote)
- No channel cheermotes
- Setting channel on 'base' returns a 404 (install & select a view first)

## Licence
Unless stated here, code and assets are my own and free to use however you like.
I'd love to hear where my work ends up if you do use it though.
