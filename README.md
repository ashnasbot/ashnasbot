# AshnasBot
A simple twitch integration project to play with some python, very basic.

## Install
Requires python 3.6+ you can get it at https://www.python.org/downloads/

These docs are untested, venv has issues on certain windows installs.
```
python3 -m pip install --upgrade pip
python3 -m pip install --user virtualenv
```
```
git clone https://github.com/ashnasbot/ashnasbot.git
cd ashnasbot

python3 -m virtualenv env
source env/bin/activate
pip install -r requirements.txt
```

## Running
```python3 ./__main__.py```
navigate to `localhost:8080/dashboard` to configure!

## config
You must [register your application on the Twitch dev portal](https://dev.twitch.tv/dashboard/apps/create) and a [User authentication token](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#oauth-client-credentials-flow)
currently the bot requires both.

Then you just need the 'username' of the bot you got the auth token for.

navigate to `http://localhost:8080/static/simple/chat.html` and enter a username to get chat!

config.json
```json
{
    "client_id": "abcdef0123456789",
    "oauth": "oauth:abcdefghijklmnopqrstuvwxyz", 
    "username": "ashnasbot",
    "user_id": 275857969,
    "log_level": "INFO"
}
```

### Session Config
The browser provides its own per-client config, hit submit or reload to set these values.
 -  **Allow commands**: Allow the bot to process and respond to !commands
 -  **Pull Avatars**: Hide avatars (Twitch rate-limites API requests so this must be disabled on really busy channels)
 -  **Show Chat Notifications**: Show Sub and other messages in chat
 -  **Sounds**: Play sound effects on e.g. Subs - this is WIP
 -  **Follow Hosts**: Allows the bot to enter host target chats
 -  **Show menu on load**: Shows the config menu when the page is loaded - hover over the top of the page to show

## Known Issues
- some substitutions not supported e.g. "<3" as this isn't classed as an 'emote'

### Observer
- non-UTF-8 messages break the transport

## Licence
Unless stated here, code and assets are my own and free to use however you like.
I'd love to hear where my work ends up if you do use it though.

Includes the excellent Reactor7 font by Cava
(CC-by-nc-sa) http://caveras.net