"""Captured EventSub WebSocket messages for tests."""

CUSTOM_REDEMPTION = {
    'metadata': {
        'message_id': 'pyoYx2kWz7HP7j05jvANKEupYH-6NRoN9k9qPUsXN9g=',
        'message_type': 'notification',
        'message_timestamp': '2025-06-17T18:51:19.436221126Z',
        'subscription_type': 'channel.channel_points_custom_reward_redemption.add',
        'subscription_version': '1'
    },
    'payload': {
        'subscription': {
            'id': 'b696ba78-6706-4873-bc30-495c3fd69294',
            'status': 'enabled',
            'type': 'channel.channel_points_custom_reward_redemption.add',
            'version': '1',
            'condition': {
                'broadcaster_user_id': '114409148',
                'reward_id': ''
            },
            'transport': {
                'method': 'websocket',
                'session_id': 'AgoQbBhfEwUKSaOqCcBmVdRSAhIGY2VsbC1j'
            },
            'created_at': '2025-06-17T18:50:51.398050513Z',
            'cost': 0
        },
        'event': {
            'broadcaster_user_id': '114409148',
            'broadcaster_user_login': 'ashnas',
            'broadcaster_user_name': 'Ashnas',
            'id': 'a1cea0a7-d1cc-4f02-b831-0eaf5204dfc3',
            'user_id': '114409148',
            'user_login': 'ashnas',
            'user_name': 'Ashnas',
            'user_input': '',
            'status': 'unfulfilled',
            'redeemed_at': '2025-06-17T18:51:19.414687838Z',
            'reward': {
                'id': 'd81d2db3-a458-4466-ab8d-ae96704a95e3',
                'title': 'Send Jewels to Gem',
                'prompt': ("Maybe he'll give us a herb?\n"
                           "This might make a noise, but really this is just a way to dump "
                           "points and look swag doing it."),
                'cost': 5000
            }
        }
    }
}
