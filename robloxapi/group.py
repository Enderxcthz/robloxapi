import json
import logging
import re
import asyncio
from bs4 import BeautifulSoup
from .utils.errors import *
from .utils.classes import *
from .joinrequest import *
from .groupmember import *
from .auth import *


class Group:
    def __init__(self, request, group_id, group_name, description, member_count, shout, owner_id=None, owner_username=None):
        self.request = request
        self.id = group_id
        self.name = group_name
        self.description = description
        self.owner = {
            'id': owner_id,
            'name': owner_username
        }
        self.member_count = member_count
        self.shout = shout

    async def exile(self, user_id: int) -> int:
        r = await self.request.request(url=f'https://groups.roblox.com/v1/groups/{self.id}/users/{user_id}', method='POST')
        return r.status_code

    async def set_rank(self, user_id: int, rank_id: int) -> int:
        data = json.dumps({
            'roleId': rank_id
        })
        r = await self.request.request(url=f'https://groups.roblox.com/v1/groups/{self.id}/users/{user_id}', method="PATCH", data=data)
        return r.status_code

    async def promote(self, user_id: int) -> int:
        return await self.change_rank(user_id, 1)

    async def demote(self, user_id: int) -> int:
        return await self.change_rank(user_id, -1)

    async def change_rank(self, user_id: int, change: int) -> int:
        roles = await self.get_group_roles()
        role = await self.get_role_in_group(user_id)
        user_role = -1
        for r in roles:
            user_role = user_role + 1
            if r.id == role.id:
                break
        new_user_role = user_role + change
        print(roles[new_user_role].rank)
        if len(roles) < new_user_role or int(roles[new_user_role].rank) == 255:
            raise RoleError("The role is over 255 or does not exist")
        return await self.set_rank(user_id, roles[new_user_role].id)

    async def set_rank_by_id(self, user_id: int, role_id: int) -> int:
        roles = await self.get_group_roles()
        choose = None
        for role in roles:
            if role.rank == role_id:
                choose = role
        if not choose:
            raise NotFound(f'Role {role_id} does not exist.')
        return await self.set_rank(user_id, choose.id)

    async def get_wall(self, limit=10):
        r = await self.request.request(url=f'https://groups.roblox.com/v2/groups/{self.id}/wall/posts?limit={limit}', method='GET')

    async def get_group_roles(self) -> list:
        r = await self.request.request(url=f'https://groups.roblox.com/v1/groups/{self.id}/roles', method='GET')
        roles = []
        for role in r.json().get('roles'):
            roles.append(Role(role['id'], role['name'], role['rank'], role['memberCount']))
        return roles

    async def get_role_in_group(self, user_id):
        r = await self.request.request(url=f'https://groups.roblox.com/v1/users/{user_id}/groups/roles', method='GET')
        data = r.json()
        user_role = None
        for group in data['data']:
            if group['group']['id'] == self.id:
                user_role = group
                break
        if not user_role:
            raise NotFound('The user is not in that group.')
        return Role(user_role['role']['id'], user_role['role']['name'], user_role['role']['rank'], user_role['role']['memberCount'])

    async def post_shout(self, message: str) -> Shout:
        data = {'message': message}
        r = await self.request.request(url=f'https://groups.roblox.com/v1/groups/{self.id}/status', method='PATCH', data=json.dumps(data))
        shout = r.json()
        return Shout(message, shout['poster']['username'], shout['poster']['userId'], shout['created'], shout['updated'])

    async def get_funds(self):
        r = await self.request.request(url=f'https://economy.roblox.com/v1/groups/{self.id}/currency', method='GET')
        return r.json().get('robux')

    # TODO: Use https://groups.roblox.com/v1/groups/{groupId}/join-requests
    async def get_join_requests(self):
        r = await self.request.request(url=f'https://www.roblox.com/groups/{self.id}/joinrequests-html', method='GET')
        soup = BeautifulSoup(r.text, 'html.parser')
        container = soup.find('div', {'id': 'JoinRequestsList'}).table.find_all('tr')  # what
        del container[0]
        del container[-1]
        requests = []
        for request in container:
            request_id = request.find('span', {"class": "btn-control btn-control-medium accept-join-request"})['data-rbx-join-request']
            roblox_avatar = request.td.span.img['src']
            roblox_name = request.find('a').text
            roblox_id = re.findall(r'\b\d+\b', request.find('a')['href'])
            requests.append(JoinRequest(self.request, request_id, roblox_name, roblox_id, roblox_avatar))
        return requests

    async def get_members(self, cursor='', members=[]):
        r = await self.request.request(url=f"https://groups.roblox.com/v1/groups/{self.id}/users?limit=100&sortOrder=Desc&cursor={cursor}", method="GET")
        response = r.json()
        for user in response['data']:
            members.append(GroupMember(self.request, user["user"]["userId"], user["user"]["username"], self.id, Role(user['role']['id'], user['role']['name'], user['role']['rank'], user['role']['memberCount'])))
        if not response['nextPageCursor']:
            return members
        else:
            return await self.get_members(cursor=response['nextPageCursor'], members=members)

    async def join(self, captcha: str):
        auth = Captcha(self.request, captcha, pkey="63E4117F-E727-42B4-6DAA-C8448E9B137F")
        token = ''
        data, status = await auth.create_task()
        if status == 200:
            while True:
                r, s = await auth.check_task(data["request"])
                if r['request'] != "CAPCHA_NOT_READY":
                    token = r['request']
                    break
                await asyncio.sleep(1.5)
        data = json.dumps({
            'captchaProvider': 'PROVIDER_ARKOSE_LABS',
            'captchaToken': token
        })
        r = await self.request.request(url=f'https://groups.roblox.com/v1/groups/{self.id}/users', data=data, method="POST")
        return r.status_code

    async def leave(self):
        r = await self.request.request(url="https://groups.roblox.com/v1/groups/3788537/users/109503558", method="DELETE")
        return r.status_code