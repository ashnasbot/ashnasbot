# AshnasBot
A simple twitch integration project to play with some python, very basic.

## Install
(TODO: test these instructions & add windows)  
Requires python 3.6+ you can get it at https://www.python.org/downloads/

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

Then you just need the 'username' of the token and the username of the channel you want to join.

navigate to `http://localhost/static/simple/chat.html` and enter a username to get chat!

TODO: Document alerts
TODO: Example config.json

## Known Issues
- No way to enable/disable alerts
- some substitutions not supported e.g. "<3"

## Licence
Unless stated here, code and assets are my own and free to use however you like.
I'd love to hear where my work ends up if you do use it though.

Includes the excellent Reactor7 font by Cava
(CC-by-nc-sa) http://caveras.net

## TODO
- Fix credentials to only need oauth
- bits emotes
- chat commands
- bot replies
- cleanup ff7 css
- use CDN for all fonts
