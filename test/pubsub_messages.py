"""Example testdata for pubsub messages of various types."""
RESUB = {
  "type": "MESSAGE",
  "data": {
    "topic": "channel-subscribe-events-v1.44322889",
    "message": {
      "user_name": "tww2",
      "display_name": "TWW2",
      "channel_name": "mr_woodchuck",
      "user_id": "13405587",
      "channel_id": "89614178",
      "time": "2015-12-19T16:39:57-08:00",
      "sub_plan": "1000",
      "sub_plan_name": "Channel Subscription (mr_woodchuck)",
      "cumulative_months": 9,
      "streak_months": 3,
      "context": "resub",
      "is_gift": False,
      "sub_message": {
        "message": "A Twitch baby is born! KappaHD",
        "emotes": [
          {
            "start": 23,
            "end": 7,
            "id": 2867
          }
        ]
      }
    }
  }
}
SUBGIFT = {
    "type": "MESSAGE",
    "data": {
        "topic": "channel-subscribe-events-v1.44322889",
        "message": {
            "user_name": "tww2",
            "display_name": "TWW2",
            "channel_name": "mr_woodchuck",
            "user_id": "13405587",
            "channel_id": "89614178",
            "time": "2015-12-19T16:39:57-08:00",
            "sub_plan": "1000",
            "sub_plan_name": "Channel Subscription (mr_woodchuck)",
            "months": 9,
            "context": "subgift",
            "is_gift": True,
            "sub_message": {
                "message": "",
                "emotes": None
            },
            "recipient_id": "19571752",
            "recipient_user_name": "forstycup",
            "recipient_display_name": "forstycup"
        }
    }
}
SUBGIFTANON = {
  "type": "MESSAGE",
  "data": {
    "topic": "channel-subscribe-events-v1.44322889",
    "message": {
      "channel_name": "mr_woodchuck",
      "channel_id": "89614178",
      "time": "2015-12-19T16:39:57-08:00",
      "sub_plan": "1000",
      "sub_plan_name": "Channel Subscription (mr_woodchuck)",
      "months": 9,
      "context": "anonsubgift",
      "is_gift": True,
      "sub_message": {
        "message": "",
        "emotes": None
      },
      "recipient_id": "13405587",
      "recipient_user_name": "tww2",
      "recipient_display_name": "TWW2"
    }
  }
}
SUBMULTIMONTH = {
   "type": "MESSAGE",
   "data": {
     "topic": "channel-subscribe-events-v1.44322889",
     "message": {
       "user_name": "tww2",
       "display_name": "TWW2",
       "channel_name": "mr_woodchuck",
       "user_id": "13405587",
       "channel_id": "89614178",
       "time": "2015-12-19T16:39:57-08:00",
       "sub_plan": "1000",
       "sub_plan_name": "Channel Subscription (mr_woodchuck)",
       "months": 4,
       "context": "sub",
       "is_gift": False,
       "sub_message": {
         "message": "",
         "emotes": None
       },
       "recipient_id": "19571752",
       "recipient_user_name": "forstycup",
       "recipient_display_name": "forstycup",
       "multi_month_duration": 6
     }
   }
 }
REDEMPTION = {
    'type': 'MESSAGE',
    'data': {
      'topic': 'channel-points-channel-v1.114409148',
      'message': {
          "type": "reward-redeemed",
          "data": {
              "timestamp": "2019-11-12T01:29:34.98329743Z",
              "topic": "channel-points-channel-v1.8972342345",
              "redemption": {
                  "id": "9203c6f0-51b6-4d1d-a9ae-8eafdb0d6d47",
                  "user": {
                      "id": "30515034",
                      "login": "davethecust",
                      "display_name": "davethecust"
                  },
                  "channel_id": "30515034",
                  "redeemed_at": "2019-12-11T18:52:53.128421623Z",
                  "reward": {
                      "id": "6ef17bb2-e5ae-432e-8b3f-5ac4dd774668",
                      "channel_id": "30515034",
                      "title": "hit a gleesh walk on stream",
                      "prompt": "cleanside's finest \n",
                      "cost": 10,
                      "is_user_input_required": True,
                      "is_sub_only": False,
                      "image": None,
                      "background_color": "#00C7AC",
                      "is_enabled": True,
                      "is_paused": False,
                      "is_in_stock": True,
                      "max_per_stream": {"is_enabled": False, "max_per_stream": 0},
                      "should_redemptions_skip_request_queue": True
                  },
                  "user_input": "yeooo",
                  "status": "FULFILLED"
              }
          }
      }
    }
}
REDEMPTION2 = {
  'type': 'MESSAGE',
  'data': {
    'topic': 'channel-points-channel-v1.114409148',
    'message': {
      "type": "reward-redeemed",
      "data": {
        "timestamp": "2022-08-29T13:57:06.244328577Z",
        "redemption": {
          "id": "7af66bfa-6708-4c40-98de-3c151f7167e9",
          "user": {
            "id": "114409148",
            "login": "ashnas",
            "display_name": "Ashnas"
          },
          "channel_id": "114409148",
          "redeemed_at": "2022-08-29T13:57:06.244328577Z",
          "reward": {
            "id": "ea46d0c8-8a89-4a3d-b719-a8e8eeaaef1f",
            "channel_id": "114409148",
            "title": "Roll a d20",
            "prompt": "Important life decision? Let me roll a completely fair dice for you.",
            "cost": 1500,
            "is_user_input_required": False,
            "is_sub_only": False,
            "image": {
              "url_1x": "https://static-cdn.jtvnw.net/custom-reward-images/114409148/ea46d0c8-8a89-4a3d-b719-a8e8eeaaef1f/0f24dd4f-3964-467c-90e2-3f5229866626/custom-1.png",
              "url_2x": "https://static-cdn.jtvnw.net/custom-reward-images/114409148/ea46d0c8-8a89-4a3d-b719-a8e8eeaaef1f/0f24dd4f-3964-467c-90e2-3f5229866626/custom-2.png",
              "url_4x": "https://static-cdn.jtvnw.net/custom-reward-images/114409148/ea46d0c8-8a89-4a3d-b719-a8e8eeaaef1f/0f24dd4f-3964-467c-90e2-3f5229866626/custom-4.png"
            },
            "default_image": {
              "url_1x": "https://static-cdn.jtvnw.net/custom-reward-images/default-1.png",
              "url_2x": "https://static-cdn.jtvnw.net/custom-reward-images/default-2.png",
              "url_4x": "https://static-cdn.jtvnw.net/custom-reward-images/default-4.png"
            },
            "background_color": "#8205B3",
            "is_enabled": True,
            "is_paused": False,
            "is_in_stock": True,
            "max_per_stream": {
              "is_enabled": False,
              "max_per_stream": 0
            },
            "should_redemptions_skip_request_queue": False,
            "template_id": None,
            "updated_for_indicator_at": "2020-10-14T22:17:36.027705788Z",
            "max_per_user_per_stream": {
              "is_enabled": False,
              "max_per_user_per_stream": 0
            },
            "global_cooldown": {
              "is_enabled": False,
              "global_cooldown_seconds": 0
            },
            "redemptions_redeemed_current_stream": None,
            "cooldown_expires_at": None
          },
          "status": "UNFULFILLED"
        }
      }
    }
  }
}
