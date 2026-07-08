
MAX_CACHED_USERS = 1000


class Users():

    def __init__(self, http_client):
        self.http_client = http_client
        self.users = {}

    async def get_picture(self, user):
        """Return the user's profile image URL, or None if lookup fails.

        Failed lookups are not cached, so transient API errors recover.
        """
        info = self.users.get(user)

        if not info:
            info = await self.http_client.get_user_info(user)
            if info:
                if len(self.users) >= MAX_CACHED_USERS:
                    self.users.pop(next(iter(self.users)))
                self.users[user] = info

        return info.get('profile_image_url') if info else None
