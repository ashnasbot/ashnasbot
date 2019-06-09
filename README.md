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

navigate to `http://localhost/static/ff7/chat.html?channel=username` to get chat!

TODO: Document alerts

## Known Issues
- Websocket sometimes gets confused - breaks eventloop

## TODO
- Fix credentials to only need oauth
- alerts betterer
- bits emotes
- chat commands
- bot replies
