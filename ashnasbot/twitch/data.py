STATIC_CDN = "https://static-cdn.jtvnw.net/"

ACTION="action"

BADGES = {
    'admin': STATIC_CDN + "chat-badges/admin-alpha.png",
    'bits1': STATIC_CDN + "/badges/v1/73b5c3fb-24f9-4a82-a852-2f475b59411c/2",
    'bits100': STATIC_CDN + "badges/v1/09d93036-e7ce-431c-9a9e-7044297133f2/2",
    'bits1000': STATIC_CDN + "badges/v1/0d85a29e-79ad-4c63-a285-3acd2c66f2ba/2",
    'bits5000': STATIC_CDN + "badges/v1/57cd97fc-3e9e-4c6d-9d41-60147137234e/2",
    'bits10000': STATIC_CDN + "badges/v1/68af213b-a771-4124-b6e3-9bb6d98aa732/2",
    'bits25000': STATIC_CDN + "badges/v1/64ca5920-c663-4bd8-bfb1-751b4caea2dd/2",
    'broadcaster': STATIC_CDN + "chat-badges/broadcaster-alpha.png",
    'global_mod': STATIC_CDN + "badges/v1/9384c43e-4ce7-4e94-b2a1-b93656896eba/2",
    'moderator': STATIC_CDN + "chat-badges/mod-alpha.png",
    'subscriber': STATIC_CDN + "badges/v1/5d9f2208-5dd8-11e7-8513-2ff4adfae661/2",
    'staff': STATIC_CDN + "chat-badges/staff-alpha.png",
    'turbo': STATIC_CDN + "chat-badges/turbo-alpha.png",
    'partner': STATIC_CDN + "badges/v1/d12a2e27-16f6-41d0-ab77-b780518f00a3/2",
    'premium': STATIC_CDN + "badges/v1/a1dd5073-19c3-4911-8cb4-c464a7bc1510/2",
    'vip': STATIC_CDN + "badges/v1/b817aba4-fad8-49e2-b88a-7cc744dfa6ec/2"
}

SUB_TIERS = [0, 3, 6, 9, 12, 18, 24, 30]

EMOTE_URL_TEMPLATE = "<img src=\"" + STATIC_CDN + \
"""emoticons/v1/{eid}/2.0" class="emote" 
alt="{alt}"
title="{alt}"
/>"""

CHEERMOTE_URL_TEMPLATE = "<img src=\"{url}\" class=\"emote\"" + \
"""alt="{alt}"
title="{alt}"
/>"""

CHEERMOTE_TEXT_TEMPLATE = """<span class="cheertext-{color}">{text}</span> """

BADGE_URL_TEMPLATE = """<img class="badge" src="{url}"
alt="{alt}"
title="{alt}"
/>"""

BITS_COLORS = [
    (1, 'gray'),
    (100, 'purple'),
    (1000, 'green'),
    (5000, 'blue'),
    (10000, 'red'),
]
BITS_INDICIES = [1, 100, 1000, 5000, 10000]