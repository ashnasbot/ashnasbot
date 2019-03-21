import json

import aiohttp

API_BASE = "https://api.twitch.tv"


class TwitchClient():

    def __init__(self, client_id, target_user):
        self.client_id = client_id
        self.target_user = target_user
        print("###", client_id, target_user)

        self._apis = {
            "login": {
                "url": "/kraken/users",
                "params": {'login': f'{self.target_user}'}
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
        

    def get_api(self, api_name):
        if api_name in self._apis:
            return self._apis[api_name]

        return None

    async def make_api_request(self, api):
        api_req = self.get_api(api)
        headers = {
            "Client-ID": f"{self.client_id}",
            "Accept": "application/vnd.twitchtv.v5+json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(API_BASE + api_req["url"],
                         params=api_req['params'],
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
                print(user['display_name'], "is a new follower")
                follow_file[user['_id']] = user['display_name']
                new_follows.append(user['display_name'])

        with open("data/followers.json", "wt") as f:
            json.dump(follow_file, f)

        return new_follows

