
class Users():

    def __init__(self, http_client):
        self.http_client = http_client
        self.users = {}

    async def get_picture(self, user):

        if user in self.users:
            info = self.users[user]

        else:
            info = await self.http_client.get_user_info(user)
            self.users[user] = info
        
        print(info)

        return info['logo']
            
            
