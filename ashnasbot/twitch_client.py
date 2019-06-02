import json
import logging

import aiohttp

API_BASE = "https://api.twitch.tv"
logger = logging.getLogger(__name__)


class TwitchClient():

    # TODO: Refactor to be a generic client
    def __init__(self, client_id, target_user):
        self.client_id = client_id
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

