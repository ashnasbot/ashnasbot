import json
import logging

import aiohttp

from .. import config

API_BASE = "https://api.twitch.tv"
logger = logging.getLogger(__name__)


class TwitchClient():

    # Use the same session for matching clients, no matter the instance.
    __sessions = {}

    def __init__(self, client_id=None, target_user=None):
        if client_id:
            self.client_id = client_id
        else:
            cfg = config.Config()
            self.client_id = cfg["client_id"]

        self.target_user = target_user
        self.channel_id = None

        logger.info(f"Creating twitch client for {client_id}/{target_user}")


    async def _make_api_request(self, url, params=None):
        headers = {
            "Client-ID": f"{self.client_id}",
            "Accept": "application/vnd.twitchtv.v5+json"
        }
        session = self.__sessions.get(self.client_id, None)

        if not session or session.closed:
            logger.info("Starting client session")
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
            return resp["data"][0]["id"]
        except:
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
        if self.channel_id == None:
            await self.get_own_channel_id()

        url = f"/kraken/channels/{self.channel_id}/follows"

        logger.debug("Retrieving new followers")
        recent_followers = await self._make_api_request(url, {'limit': 10})
        new_follows = []
        existing_follows = {}

        follow_file = "data/followers.json"

        try:
            with open(follow_file, "rt") as f:
                existing_follows = json.load(f)
        except:
            logger.warn("Cannot read followers cache")

        for follower in recent_followers['follows']:
            user = follower['user']
            if user['_id'] not in existing_follows:
                logger.info(user['display_name'], "is a new follower")
                existing_follows[user['_id']] = user['display_name']
                new_follows.append(user['display_name'])

        try:
            with open(follow_file, "wt") as f:
                json.dump(existing_follows, f)
        except:
            logger.error("Cannot write followers cache")

        return new_follows


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
            # Get additional sub tiers too
            sub_badges = {}
            url = f"https://badges.twitch.tv/v1/badges/channels/{channel_id}/display"
            sub_badges = await self._make_api_request(url)

            if sub_badges and "subscriber" in sub_badges["badge_sets"]:
                for months, urls in sub_badges["badge_sets"]["subscriber"]["versions"].items():
                    badges[f"subscriber{months}"] = urls["image_url_2x"]

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