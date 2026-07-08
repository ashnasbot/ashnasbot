import asyncio
from enum import Enum
import json
import logging
import websockets.exceptions
from websockets.asyncio.client import connect as ws_connect

from .data import create_follower, Event, EventType
from . import redemptions
from .api_client import TwitchClient
from .. import llm

logger = logging.getLogger(__name__)


class MESSAGE_TYPES(str, Enum):
    KEEPALIVE = "session_keepalive"
    NOTIFY = "notification"
    RECONNECT = "session_reconnect"


# Require broadcaster_user_id + user_id; token must belong to user_id (scope: user:read:chat)
_CHAT_SUBSCRIPTIONS = [
    ("channel.chat.message", "1"),
    ("channel.chat.notification", "1"),
    ("channel.chat.message_delete", "1"),
    ("channel.chat.clear", "1"),
]

# Require broadcaster_user_id only; token must be the broadcaster's (scope: channel:read:redemptions).
_BROADCASTER_SUBSCRIPTIONS = [
    ("channel.channel_points_custom_reward_redemption.add", "1"),
    ("channel.update", "2"),
]


class EventSubClient():

    RECONNECT_MAX_BACKOFF = 120  # seconds

    def __init__(self, alert_callback, chat_callback, bot_token=None, bot_user_id=None):
        self.connection = None
        self.keep_alive_timeout_seconds = 10
        self.stop_event = asyncio.Event()
        self.session = {}
        self.api_client = TwitchClient(None, None)
        self.bot_token = bot_token
        self.bot_user_id = str(bot_user_id) if bot_user_id else None
        self.alert_callback = alert_callback
        self.chat_callback = chat_callback
        # (kind, channel_id) -> token, replayed after a reconnect
        self._subscriptions = {}

    async def connect(self):
        self.connection = await ws_connect(
            'wss://eventsub.wss.twitch.tv/ws', ping_interval=None)
        welcome_buf = await asyncio.wait_for(self.connection.recv(), timeout=15)
        logger.debug(welcome_buf)
        welcome_msg = json.loads(welcome_buf)
        self.id = welcome_msg["payload"]["session"]["id"]
        self.keep_alive_timeout_seconds = welcome_msg["payload"]["session"]["keepalive_timeout_seconds"]
        return self.connection

    async def close(self):
        """Shut the client down for good (no reconnect)."""
        self.stop_event.set()
        if self.connection:
            await self.connection.close()

    async def _notify(self, text):
        evt = Event(EventType.SYSTEM)
        evt.tags = {"system-msg": text}
        await self.alert_callback(evt)

    async def _resubscribe(self):
        """Replay all recorded subscriptions onto the current (fresh) session."""
        for (kind, channel_id), token in list(self._subscriptions.items()):
            if kind == "chat":
                await self.subscribe(channel_id, broadcaster_token=token)
            else:
                await self.subscribe_broadcaster(channel_id, token)

    async def _reconnect(self):
        """Reconnect and resubscribe, retrying forever with capped exponential backoff.

        The client is useless without a connection, so keep trying until it
        works or the client is closed. Returns False only when closed.
        """
        delay = 1
        attempt = 0
        while not self.stop_event.is_set():
            attempt += 1
            try:
                await self.connect()
                await self._resubscribe()
                logger.info("EventSub reconnected after %d attempt(s)", attempt)
                await self._notify("Reconnected to Twitch")
                return True
            except Exception as e:
                logger.warning("EventSub reconnect attempt %d failed (%s) — retrying in %ds",
                               attempt, e, delay)
                try:
                    await asyncio.wait_for(self.stop_event.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                delay = min(delay * 2, self.RECONNECT_MAX_BACKOFF)
        return False

    async def receive_message(self):
        """Receive & process server messages, reconnecting on connection loss."""
        self.receive_task = asyncio.current_task()
        while not self.stop_event.is_set():
            connection = self.connection
            try:
                message = await asyncio.wait_for(
                    connection.recv(), timeout=self.keep_alive_timeout_seconds + 5)
                await self.handle_message(message)
            except asyncio.TimeoutError:
                if self.stop_event.is_set():
                    return
                logger.error("EventSub keepalive timeout — reconnecting")
                await self._notify("Connection to Twitch timed out — reconnecting")
                if not await self._reconnect():
                    return
            except websockets.exceptions.ConnectionClosed as e:
                if self.stop_event.is_set():
                    logger.info("EventSub connection closed")
                    return
                if self.connection is not connection:
                    # Twitch-directed reconnect swapped the socket under us; carry on
                    continue
                logger.error("EventSub connection lost: %s", e)
                await self._notify("Connection to Twitch lost — reconnecting")
                if not await self._reconnect():
                    return
            except Exception:
                logger.exception("EventSub failure")

    async def handle_message(self, message):
        event = json.loads(message)
        msg_type = event["metadata"]["message_type"]

        if msg_type == MESSAGE_TYPES.KEEPALIVE:
            return

        if msg_type == MESSAGE_TYPES.RECONNECT:
            await self._handle_reconnect(event)
            return

        if msg_type != MESSAGE_TYPES.NOTIFY:
            return

        subscription_type = event["payload"]["subscription"]["type"]
        logger.debug(event)
        payload = event["payload"]["event"]

        if subscription_type == "channel.chat.message":
            evt = self.handle_chat_message(payload)
            if evt:
                await self.chat_callback(evt)

        elif subscription_type == "channel.chat.notification":
            evt = self.handle_notification(payload)
            if evt:
                await self.alert_callback(evt)

        elif subscription_type == "channel.chat.message_delete":
            evt = self.handle_message_delete(payload)
            if evt:
                await self.alert_callback(evt)

        elif subscription_type == "channel.chat.clear":
            evt = self.handle_chat_clear(payload)
            if evt:
                await self.alert_callback(evt)

        elif subscription_type == "channel.follow":
            evt = create_follower(payload["user_name"], payload["broadcaster_user_login"])
            await self.alert_callback(evt)

        elif subscription_type == "channel.channel_points_custom_reward_redemption.add":
            evt = self.handle_redemption(payload)
            if evt:
                await self.alert_callback(evt)

        elif subscription_type == "channel.update":
            game = payload.get("category_name", "")
            if game.lower() in ("", "retro"):
                game = ""
            llm.set_stream_context(game or None)
            logger.info("Stream context updated: game=%s", game or "(none)")

        else:
            logger.warning(f"unknown subscription type '{subscription_type}'")

    async def subscribe(self, channel_id, broadcaster_token=None):
        """Subscribe to chat events on this WebSocket session.

        Uses the bot token when configured; falls back to broadcaster_token.
        When no bot token is set (single-user mode) and broadcaster_token is
        supplied, also subscribes to broadcaster-only events so that a single
        connection handles everything.
        """
        if self.bot_token and self.bot_user_id:
            chat_user_id = self.bot_user_id
            chat_token = self.bot_token
        elif broadcaster_token:
            chat_user_id = channel_id
            chat_token = broadcaster_token
        else:
            logger.error("No token available for EventSub chat subscriptions")
            return

        self._subscriptions[("chat", channel_id)] = broadcaster_token

        chat_condition = {"broadcaster_user_id": channel_id, "user_id": chat_user_id}
        logger.debug("Subscribing to chat EventSub for channel %s (user %s)", channel_id, chat_user_id)
        for sub in _CHAT_SUBSCRIPTIONS:
            await self.api_client.subscribe_eventsub(
                self.id, sub, condition=chat_condition,
                channel_id=channel_id, user_token=chat_token)

        info = await self.api_client.get_channel_info(channel_id)
        game = info.get("game_name", "")
        if game and game.lower() != "retro":
            llm.set_stream_context(game)
            logger.info("Stream context set to game: %s", game)

        # Single-user mode: broadcaster handles everything on this one session.
        if not self.bot_token and broadcaster_token:
            await self.subscribe_broadcaster(channel_id, broadcaster_token)

    async def subscribe_broadcaster(self, channel_id, broadcaster_token):
        """Subscribe to follow and redemption events using the broadcaster's token.

        Must be called on a WebSocket session where ALL subscriptions use the
        same broadcaster token — do not mix with a bot-token session or Twitch
        will reject the subscriptions with a 400 'different users' error.
        """
        if not broadcaster_token:
            logger.info("No broadcaster token — follow and redemption subscriptions skipped")
            return

        self._subscriptions[("broadcaster", channel_id)] = broadcaster_token

        follow_condition = {
            "broadcaster_user_id": channel_id,
            "moderator_user_id": channel_id,
        }
        logger.debug("Subscribing to follow EventSub for channel %s", channel_id)
        await self.api_client.subscribe_eventsub(
            self.id, ("channel.follow", "2"), condition=follow_condition,
            channel_id=channel_id, user_token=broadcaster_token)

        broadcaster_condition = {"broadcaster_user_id": channel_id}
        logger.debug("Subscribing to broadcaster EventSub for channel %s", channel_id)
        for sub in _BROADCASTER_SUBSCRIPTIONS:
            await self.api_client.subscribe_eventsub(
                self.id, sub, condition=broadcaster_condition,
                channel_id=channel_id, user_token=broadcaster_token)

    async def _handle_reconnect(self, event):
        """Handle a Twitch-directed session_reconnect: swap the socket in place.

        Subscriptions carry over to the new connection, so no resubscribe is
        needed. The receive loop notices self.connection changed and continues.
        """
        reconnect_url = event["payload"]["session"]["reconnect_url"]
        logger.info("EventSub reconnect requested — connecting to %s", reconnect_url)
        try:
            new_connection = await ws_connect(reconnect_url, ping_interval=None)
            welcome = json.loads(await asyncio.wait_for(new_connection.recv(), timeout=15))
            self.id = welcome["payload"]["session"]["id"]
            self.keep_alive_timeout_seconds = welcome["payload"]["session"]["keepalive_timeout_seconds"]
            old_connection = self.connection
            self.connection = new_connection
            await old_connection.close()
        except Exception as e:
            logger.error("EventSub directed reconnect failed: %s — falling back to fresh connection", e)
            await self._reconnect()

    # ------------------------------------------------------------------ handlers

    def handle_chat_message(self, payload):
        channel = payload["broadcaster_user_login"]
        evt = Event(EventType.TWITCHCHATMESSAGE)
        evt.channel = channel
        evt.nickname = payload["chatter_user_name"]
        evt.message = payload["message"]["text"]
        evt.tags = {
            "display-name": payload["chatter_user_name"],
            "user-id": payload["chatter_user_id"],
            "id": payload["message_id"],
            "room-id": payload["broadcaster_user_id"],
            "color": payload.get("color", ""),
            "_fragments": payload["message"]["fragments"],
            "_badges_raw": payload.get("badges", []),
        }
        if payload.get("cheer"):
            evt.tags["bits"] = payload["cheer"]["bits"]
        if payload.get("reply"):
            reply = payload["reply"]
            evt.tags["reply-parent-msg-id"] = reply["parent_message_id"]
            evt.tags["reply-parent-user-login"] = reply["parent_user_login"]
            evt.tags["reply-parent-display-name"] = reply.get("parent_user_name", reply["parent_user_login"])
            evt.tags["reply-parent-msg-body"] = reply.get("parent_message_body", "")
        if payload.get("channel_points_custom_reward_id"):
            evt.tags["custom-reward-id"] = payload["channel_points_custom_reward_id"]
        return evt

    def handle_notification(self, payload):
        notice_type = payload.get("notice_type")
        channel = payload["broadcaster_user_login"]

        if notice_type in ("sub", "resub"):
            sub_data = payload.get(notice_type, {})
            tier_map = {"1000": "a tier 1 sub", "2000": "a tier 2 sub",
                        "3000": "a tier 3 sub", "Prime": "Twitch Prime"}
            plan = tier_map.get(sub_data.get("sub_tier", "1000"), "a sub")
            months = sub_data.get("cumulative_months", 1)
            nickname = payload["chatter_user_name"]
            text = f"{nickname} just subscribed with {plan} for {months} months!"
            evt = Event(EventType.SUB)
            evt.channel = channel
            evt.nickname = nickname
            evt.tags = {
                "display-name": nickname,
                "system-msg": text,
                "msg-param-cumulative-months": months,
            }
            logger.info("EVENTSUB: %s", text)
            return evt

        elif notice_type == "sub_gift":
            sub_data = payload.get("sub_gift", {})
            gifter = payload["chatter_user_name"]
            recipient = sub_data.get("recipient_user_name", "someone")
            text = f"{gifter} gifted a subscription to {recipient}!"
            evt = Event(EventType.SUBGIFT)
            evt.channel = channel
            evt.nickname = recipient
            evt.tags = {
                "display-name": gifter,
                "msg-param-recipient-display-name": recipient,
                "system-msg": text,
            }
            logger.info("EVENTSUB: %s", text)
            return evt

        elif notice_type == "raid":
            raid_data = payload.get("raid", {})
            raider = raid_data.get("user_name", payload.get("chatter_user_name", ""))
            viewer_count = raid_data.get("viewer_count", 0)
            text = f"{raider} is raiding with a party of {viewer_count}!"
            evt = Event(EventType.RAID)
            evt.channel = channel
            evt.nickname = raider
            evt.tags = {
                "display-name": raider,
                "msg-param-displayName": raider,
                "msg-param-viewerCount": viewer_count,
                "system-msg": text,
            }
            logger.info("EVENTSUB: %s", text)
            return evt

        else:
            logger.info("EVENTSUB: unhandled notification type '%s'", notice_type)
            return None

    def handle_message_delete(self, payload):
        evt = Event(EventType.CLEARMSG)
        evt.channel = payload["broadcaster_user_login"]
        evt.id = payload["message_id"]
        evt.tags = {
            "login": payload.get("target_user_login", ""),
            "target-msg-id": payload["message_id"],
        }
        evt._command = "CLEARMSG"
        return evt

    def handle_chat_clear(self, payload):
        evt = Event(EventType.CLEARCHAT)
        evt.channel = payload["broadcaster_user_login"]
        evt.tags = {"room-id": payload["broadcaster_user_id"]}
        evt._command = "CLEARCHAT"
        return evt

    def handle_redemption(self, content):
        reward = content["reward"]
        nickname = content["user_name"]
        channel = content["broadcaster_user_login"]
        title = reward["title"]
        cost = reward["cost"]

        tags = {
            "title": title,
            "cost": cost,
            "reward-title": title,
            "display-name": nickname,
            "system-msg": f"{nickname} redeemed {title}",
        }
        user_input = content.get("user_input", "")

        out_msg = Event(EventType.REDEMPTION)
        out_msg.nickname = nickname
        out_msg.message = user_input
        out_msg.tags = tags
        out_msg.extra.append("quoted")
        out_msg.channel = channel

        if reward.get("image"):
            out_msg.logo = reward["image"]["url_2x"]
        redemptions.handle_channel_redemption(out_msg)

        logger.info(f"EVENTSUB: {tags['system-msg']}")
        return out_msg
