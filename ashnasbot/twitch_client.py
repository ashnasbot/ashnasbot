import requests
import json


API_BASE = "https://api.twitch.tv"


class TwitchClient():

    def __init__(self, client_id, target_user):
        self.client_id = client_id
        self.target_user = target_user

        self._apis = {
            "login": {
                "url": "/kraken/users",
                "params": {'login': f'{self.target_user}'}
                }
            }

        self.channel_id = self.get_channel_id()

        self._apis = {
            **self._apis,
            "followers": {
                "url": f"/kraken/channels/{self.channel_id}/follows",
                "params": {'limit': 10}
                }
            }

    def get_channel_id(self):
        resp = self.make_api_request('login')
        return resp["users"][0]["_id"]
        

    def get_api(self, api_name):
        if api_name in self._apis:
            return self._apis[api_name]

        return None

    def make_api_request(self, api):
        api_req = self.get_api(api)
        headers = {
            "Client-ID": f"{self.client_id}",
            "Accept": "application/vnd.twitchtv.v5+json"
        }

        r = requests.get(API_BASE + api_req["url"],
                         params=api_req['params'],
                         headers=headers
                        )

        return r.json()


    def get_new_followers(self):
        followers = self.make_api_request('followers')
        new_follows = []

        with open("data/followers.json", "rt") as f:
            follow_file = json.load(f)

        for follower in followers['follows']:
            user = follower['user']
            if user['_id'] not in follow_file:
                print(user['display_name'], "is a new follower")
                follow_file[user['_id']] = user['display_name']
                new_follows.append(user['display_name'])

        with open("data/followers.json", "wt") as f:
            json.dump(follow_file, f)

        return new_follows

