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
```python3 ./main.py```
navigate to `localhost:8080/dashboard` to configure!

## config
You must [register your application on the Twitch dev portal](https://dev.twitch.tv/dashboard/apps/create) and a [User authentication token](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#oauth-client-credentials-flow)
currently the bot requires both.

Then you just need the 'username' of the token and the username of the channel you want to join.

## Known Issues
- Tags seem to be funky i.e. "@ashnasbot SeemsGood"
  suspect the 'tag' to be rendered in the text differently to whats seen.
- multiple windows will receive messages in a round-robin fashion rather than duplicates.

## TODO
- Fix credentials to only need oauth
- Enable multiple clients, one per socket