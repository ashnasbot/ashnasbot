from . import av
import sys
import html

STATIC_CDN = "https://static-cdn.jtvnw.net/"

ACTION="action"

BADGES = {
    'admin': STATIC_CDN + "chat-badges/admin-alpha.png",
    'bits': STATIC_CDN + "badges/v1/09d93036-e7ce-431c-9a9e-7044297133f2/1",
    'broadcaster': STATIC_CDN + "chat-badges/broadcaster-alpha.png",
    'global_mod': STATIC_CDN + "badges/v1/9384c43e-4ce7-4e94-b2a1-b93656896eba/1",
    'moderator': STATIC_CDN + "chat-badges/mod-alpha.png",
    'subscriber': STATIC_CDN + "badges/v1/5d9f2208-5dd8-11e7-8513-2ff4adfae661/1",
    'staff': STATIC_CDN + "chat-badges/staff-alpha.png",
    'turbo': STATIC_CDN + "chat-badges/turbo-alpha.png",
    'partner': STATIC_CDN + "badges/v1/d12a2e27-16f6-41d0-ab77-b780518f00a3/1",
    'premium': STATIC_CDN + "badges/v1/a1dd5073-19c3-4911-8cb4-c464a7bc1510/1",
    'vip': STATIC_CDN + "badges/v1/b817aba4-fad8-49e2-b88a-7cc744dfa6ec/1"
}

EMOTE_URL_TEMPLATE = "<img src=\"" + STATIC_CDN + \
"""emoticons/v1/{eid}/1.0" class="emote" />"""
#can't add title as the replace is greedy
#alt="{alt}"
#title="{alt}"

def render_emotes(message, emotes):
    try:
        replacements = {}
        for emote in emotes.split("/"):
            eid, pos = emote.split(':')
            occurances = pos.split(',')
            # Grab the 1st occurance, as we'll replace the rest by string.
            start, end = occurances[0].split('-')
            substr = message[int(start):int(end) + 1]
            cls_attr = ""
            # TODO: do html-aware so we can handle attributes
            replace_str = EMOTE_URL_TEMPLATE.format(eid=eid, alt=substr)

            replacements[substr] = replace_str

        # Tactically timed html escape
        message = html.escape(message)

        for f, r in sorted(replacements.items(), key=lambda e:len(e[1]), reverse=True):
            # find = "\s+{}|{}\s+)".format(f, r)
            # message = re.sub(find, r, message)
            message = message.replace(f, r)

    except Exception as e:
        print(e)
        raise
    
    return message

BADGE_URL_TEMPLATE = """<img 
class="badge"
src="{url}"
alt="{alt}"
title="{alt}"
/>"""


def render_badges(badges):

    rendered = []

    for badgever in badges.split(','):
        badge, _ = badgever.split('/')
        url = BADGES.get(badge, None)
        if not url:
            continue
        rendered.append(BADGE_URL_TEMPLATE.format(url=url, alt=badge))

    return rendered

def handle_message(event):
    etags = event.tags
    raw_msg = ""
    try:
        raw_msg = event.message
    except:
        pass
    if event.type == "RAID":
        raw_msg = f"{etags['msg-param-displayName']} is raiding with a party of " \
                  f"{etags['msg-param-viewerCount']}"
    if event.type == "HOST":
        raw_msg = f"{etags['msg-param-displayName']} is raiding with a party of " \
                  f"{etags['msg-param-viewerCount']}"

    msg_tags = []
    msg_type = event.type

    if raw_msg.startswith('\u0001'):
        msg_tags.append(ACTION)

    if raw_msg.startswith('!'):
        print(f"{etags['display-name']} COMMAND: {raw_msg}")
        ret = None
        args = raw_msg.split(" ")
        command = args.pop(0)
        cmd = COMMANDS.get(command, None)
        if callable(cmd):
            ret = cmd(*args)
        #TODO: render responses in chat

        return {}

    nickname = etags['display-name']
    if etags['badges']:
        badges = render_badges(etags['badges'])
    else:
        badges = []

    if etags['emotes']:
        message = render_emotes(raw_msg, etags['emotes'])
    else:
        message = html.escape(raw_msg)

    # Post render message actions
    if ACTION in msg_tags:
        message = message.replace('\u0001', "")
        message = message[7:]

    return {
            'badges': badges,
            'nickname': nickname,
            'message' : message,
            'id' : etags['id'],
            'tags' : etags,
            'extra' : msg_tags,
            'type' : msg_type
            }

COMMANDS = {
    '!hey': lambda *args: av.play_random_sound('OOT_Navi_')
}
