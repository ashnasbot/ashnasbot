# AshnasBot
A simple twitch integration project to play with some python, very basic.

## Running
### exe
Just download and run `ashnasbot.exe` not install needed.
- run `ashnasbot.exe` in a terminal - it will create the required files.
- use `CRTL`+`C` to quit and set the config.
- Install required [views](https://github.com/ashnasbot/ashnasbot-views) into the directory.
- run `ashnasbot.exe` again.

### dev
The dev version has far more testing and is likely more up-to-date.

#### Install
Requires python 3.6+ you can get it at https://www.python.org/downloads/

These docs are untested, venv has issues on certain windows installs.
```
python3 -m pip install --upgrade pip
python3 -m pip install --user virtualenv
```
```
git clone https://github.com/ashnasbot/ashnasbot.git
cd ashnasbot/views
git submodule init
git submodule update
cd ..

python3 -m virtualenv env
# Windows
env\Scripts\activate.bat
# Linux
env\Scripts\activate
pip install -r requirements.txt
```

```python3 ./__main__.py```

## config
You must [register your application on the Twitch dev portal](https://dev.twitch.tv/dashboard/apps/create) to get a client id and a secret
The bot requires both client_id/secret AND a user oauth token for accessing APIs and interacting with chat respectively.

[TMI](https://twitchapps.com/tmi/) is a 3rd party service that offers an easy way to get a token.
Then you just need the 'username' of the bot account you got the auth token for.

config.json
```json
{
    "client_id": "abcdef0123456789",
    "oauth": "oauth:abcdefghijklmnopqrstuvwxyz", 
    "secret": "abcdef0123456789",
    "username": "my_bot_user",
    "user_id": 275857969,
    "log_level": "INFO"
}
```
- **client_id**: Required - App/client id from the develop portal see https://dev.twitch.tv/docs/v5#getting-a-client-id
- **oauth**: Required - Oauth Token for API access see https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/ and twitchapps.com/tokengen
- **username**: Required - Username of your bot account
- **secret**: Optional - Client Secret - used for authenticating (for pubsub)
- **user_id**: Deprecated - The 'ID' of the given user
- **log_level**: Required - `"INFO"` if unsure
- **bttv**: Optional - `true` or `false` show bttv emotes in chat

### Usage
In a browser source navigate to `http://localhost:8080/chat` select a style and enter a username to get chat!
Hover over the top of the window to show the session config window.

### Session Config
Each session keeps its own config, configured in the browser menu, hit submit commit these values.
 -  **Allow commands**: Allow the bot to process and respond to !commands
 -  **Pull Avatars**: Hide avatars (Twitch rate-limites API requests so this must be disabled on really busy channels)
 -  **Show Chat Notifications**: Show Sub and other messages in chat
 -  **Sounds**: Play sound effects on e.g. Subs
 -  **Follow Hosts**: Allows the bot to enter host target chats
 -  **Show menu on load**: Shows the config menu when the page is loaded - hover over the top of the page to show
 -  **PubSub**: Experimental - uses pubsub api to get events and channel point redemptions

## Known Issues
- some substitutions not supported e.g. "<3" as this isn't classed as an 'emote'
- no channel cheermotes

## Licence
Unless stated here, code and assets are my own and free to use however you like.
I'd love to hear where my work ends up if you do use it though.