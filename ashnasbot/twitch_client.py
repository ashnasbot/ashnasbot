import json
import logging

import aiohttp

from . import config

API_BASE = "https://api.twitch.tv"
logger = logging.getLogger(__name__)


class TwitchClient():

    # TODO: Refactor to be a generic client
    def __init__(self, client_id=None, target_user=None):
        self.config = config.Config()
        if client_id:
            self.client_id = client_id
        else:
            self.client_id = self.config["client_id"]

        self.target_user = target_user

        logger.info(f"starting twitch client for {client_id}/{target_user}")

        self._apis = {
            "login": {
                "url": "/kraken/users",
                "params": {'login': f'{self.target_user}'}
                },
            "users": {
                "url": "/kraken/users",
                "params": {'id':None}
            }
            }

        self.channel_id = None

        self._apis = {
            **self._apis,
            "followers": {
                "url": f"/kraken/channels/{self.channel_id}/follows",
                "params": {'limit': 10}
                }
            }

    async def get_channel_id(self):
        resp = await self.make_api_request('login')
        self.channel_id = resp["users"][0]["_id"]
        self._apis["followers"] = {
            "url": f"/kraken/channels/{self.channel_id}/follows",
            "params": {'limit': 10}
        }

    async def get_other_channel_id(self, channel):
        logger.debug("Getting id for %s", channel)
        api_req = {
            "url": f"/helix/users?login={channel}",
            "params": {}
        }

        resp = await self.make_api_request_2(api_req, params=None)
        return resp["data"][0]["id"]

    async def get_user_info(self, user):
        resp = await self.make_api_request('users', params={'id': user})
        try:
            return resp["users"][0]
        except:
            return {}
        

    def get_api(self, api_name):
        if api_name in self._apis:
            return self._apis[api_name]

        return None

    async def make_api_request(self, api, params=None):
        api_req = self.get_api(api)
        headers = {
            "Client-ID": f"{self.client_id}",
            "Accept": "application/vnd.twitchtv.v5+json"
        }
        if params:
            req_params = {**api_req['params'], **params}
        else:
            req_params = api_req['params']

        async with aiohttp.ClientSession() as session:
            async with session.get(API_BASE + api_req["url"],
                         params=req_params,
                         headers=headers) as resp:
                return await resp.json()

    async def make_api_request_2(self, api_req, params=None):
        headers = {
            "Client-ID": f"{self.client_id}",
            "Accept": "application/vnd.twitchtv.v5+json"
        }
        if params:
            req_params = {**api_req['params'], **params}
        else:
            req_params = api_req['params']

        async with aiohttp.ClientSession() as session:
            async with session.get(API_BASE + api_req["url"],
                         params=req_params,
                         headers=headers) as resp:
                return await resp.json()

    async def get_new_followers(self):
        if self.channel_id == None:
            await self.get_channel_id()

        recent_followers = await self.make_api_request('followers')
        new_follows = []

        with open("data/followers.json", "rt") as f:
            follow_file = json.load(f)

        for follower in recent_followers['follows']:
            user = follower['user']
            if user['_id'] not in follow_file:
                logger.info(user['display_name'], "is a new follower")
                follow_file[user['_id']] = user['display_name']
                new_follows.append(user['display_name'])

        with open("data/followers.json", "wt") as f:
            json.dump(follow_file, f)

        return new_follows

    async def get_badges_for_channel(self, channel):
        logger.debug("Getting badges for %s", channel)
        channel_id = await self.get_other_channel_id(channel)
        logger.debug("Getting badges for %s", channel_id)
        api_req = {
            "url": f"/kraken/chat/{channel_id}/badges",
            "params": {}
        }
        resp = await self.make_api_request_2(api_req)

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
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    sub_badges = await resp.json()
            if sub_badges:
                for months, urls in sub_badges["badge_sets"]["subscriber"]["versions"].items():
                    badges[f"subscriber{months}"] = urls["image_url_2x"]

        return badges

    async def get_cheermotes(self):
        resp = json.load(open("bits.json"))

        cheermotes = {}

        for cheer in resp["actions"]:
            prefix = cheer["prefix"]
            tiers = {}
            for teir in cheer["tiers"]:
                img = teir["images"]["dark"]["animated"]["2"]
                value = teir["id"]
                tiers[value] = img
            cheermotes[prefix] = tiers
        return cheermotes





