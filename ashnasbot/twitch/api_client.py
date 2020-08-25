import json
import logging
from pathlib import Path
import urllib.parse

import aiohttp
from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session

from . import db
from .. import config

API_BASE = "https://api.twitch.tv"
logger = logging.getLogger(__name__)

token = None

class TwitchClient():

    # Use the same session for matching clients, no matter the instance.
    __sessions = {}

    def __init__(self, client_id=None, target_user=None):
        global token
        cfg = config.Config()
        self.client_id = cfg["client_id"]
        logger.debug(f"Creating twitch API client for {self.client_id} {target_user}")

        self.target_user = target_user
        self.channel_id = None


        if not token:
            logger.warning("No token - retriving new token")
            body = urllib.parse.urlencode({'client_id': self.client_id, 'client_secret': cfg["secret"]})
            client = BackendApplicationClient(client_id=cfg["client_id"])
            oauth = OAuth2Session(client=client)
            token = oauth.fetch_token(token_url='https://id.twitch.tv/oauth2/token', body=body)

        self.oauth = token["access_token"]

    async def _make_api_request(self, url, params=None):
        headers = {
            "Client-ID": f"{self.client_id}",
            "Accept": "application/vnd.twitchtv.v5+json",
        }

        if "helix" in url:
            headers["Authorization"] = f"Bearer {self.oauth}"

        session = self.__sessions.get(self.client_id, None)

        if not session or session.closed:
            logger.info("Starting new client API session")
            session = aiohttp.ClientSession()
            self.__sessions[self.client_id] = session

        if not url.startswith("http"):
            url = API_BASE + url

        async with session.get(url,
                        params=params,
                        headers=headers) as resp:
            # TODO: check status (too many requests? etc)
            return await resp.json()

    async def get_own_channel_id(self):
        url = "/kraken/users"
        params = {'login': f'{self.target_user}'}

        logger.debug("Getting id for self (%s)", self.target_user)

        resp = await self._make_api_request(url, params)
        self.channel_id = resp["users"][0]["_id"]

    async def get_channel_id(self, channel):
        url = f"/helix/users?login={channel}"

        logger.debug("Getting id for %s", channel)

        resp = await self._make_api_request(url)
        try:
            logger.debug(resp)
            return resp["data"][0]["id"]
        except Exception as e:
            logger.warning(f"Get Channel ID failed {e}")
            return None

    async def get_user_info(self, user):
        url = "/kraken/users"

        logger.debug("Getting user info for %s", user)
        resp = await self._make_api_request(url, params={'id': user})
        try:
            return resp["users"][0]
        except:
            logger.warning("User %s not found", user)
            return {}


    async def get_new_followers(self):
        emit = True
        if self.channel_id == None:
            await self.get_own_channel_id()
            emit = False

        url = f"/kraken/channels/{self.channel_id}/follows"

        logger.debug("Retrieving new followers")
        recent_followers = await self._make_api_request(url, {'limit': 10})
        new_follows = []

        tbl_name = self.target_user + "_follows"

        if not db.exists(tbl_name):
            db.create(tbl_name, primary="name")
            emit = False
        
        tbl = db.get(tbl_name)
        existing_follows = [e["id"] for e in tbl]

        for follower in recent_followers['follows']:
            user = follower['user']
            if int(user["_id"]) not in existing_follows:
                new_follows.append({"username": user['display_name'], "id": user["_id"]})
                if emit:
                    logger.info("%s is a new follower", user['display_name'], )

        if new_follows:
            db.update_multi(tbl_name, new_follows, primary="username", keys=["username"])

        if emit:
            return [u["username"] for u in new_follows]
        else:
            return []


    async def get_badges_for_channel(self, channel):
        logger.debug("Getting badges for %s", channel)
        channel_id = await self.get_channel_id(channel)
        if not channel_id:
            return {}

        logger.debug("Getting badges for %s", channel_id)
        url = f"/kraken/chat/{channel_id}/badges"

        resp = await self._make_api_request(url)

        badges = {}

        for name, urls in resp.items():
            if urls:
                try:
                    badges[name] = urls["alpha"]
                except:
                    badges[name] = urls["image"]

        if badges:
            sub_badges = {}
            url = f"https://badges.twitch.tv/v1/badges/channels/{channel_id}/display"
            sub_badges = await self._make_api_request(url)

            if sub_badges and "badge_sets" in sub_badges:
                for badge_set in sub_badges["badge_sets"]:
                    for val, urls in sub_badges["badge_sets"][badge_set]["versions"].items():
                        badges[f"{badge_set}{val}"] = urls["image_url_2x"]

        return badges

    async def get_cheermotes(self):
        url = "/kraken/bits/actions"
        params = {'included_sponsored': 1}

        logger.debug("Getting global cheermotes")
        cheermotes = {}
        resp = await self._make_api_request(url, params)
                
        try:
            for cheer in resp["actions"]:
                prefix = cheer["prefix"]
                tiers = {}
                for teir in cheer["tiers"]:
                    img = teir["images"]["dark"]["animated"]["2"]
                    value = teir["id"]
                    tiers[value] = img
                cheermotes[prefix] = tiers
        except:
            logger.warning("Failed to get cheermotes")
        
        return cheermotes

    async def get_clip(self, clip):
        url = f"/kraken/clips/{clip}"
        logger.debug("Getting clip details for slug: %s", clip)
        return await self._make_api_request(url)
