"use strict";
import { createApp} from 'https://unpkg.com/vue@3/dist/vue.esm-browser.js'
import component_chatwindow from './chat-window.js'
import component_config from './config.js'
import component_views from './views.js'
import component_animations from './animation.js'
import component_pokey from './pokey.js'

var websocketLocation;

// This serves only to stop random things knocking the websocket
// can filter though proxy
var cookies = document.cookie;
document.cookie = 'secretvalue=true;path=/';
if (document.location.protocol == "https:") {
    websocketLocation = "wss://" + location.hostname + ":443/wsapp"
} else {
    console.warn("Using unsecured websocket")
    websocketLocation = "ws://" + location.hostname + ":8765"
}

var channel = "";

function checkToken() {
    /* token = token
       null = invalid
       false = none */
    var token_channel = null;
    var oauth;

    if (typeof cookies === 'undefined') {
        return Promise.resolve(false);
    }

    try {
        oauth = cookies
            .split('; ')
            .find(row => row.startsWith('token'))
            .split('=')[1];
    } catch(err) {
        console.log("No auth")
        return Promise.resolve(false);
    }
    try {
        token_channel = cookies
            .split('; ')
            .find(row => row.startsWith('user'))
            .split('=')[1];
    } catch { }

    channel = getChannel();
    if (token_channel) {
        if (channel == token_channel) {
            return Promise.resolve(oauth);
        } else {
            console.warn("Token is for a different channel — clearing stale token");
            document.cookie = `token=; Max-Age=0; path=/; domain=${location.hostname}`;
            return Promise.resolve(false);
        }
    }
    return Promise.resolve(oauth);
}

async function getAuth() {
    const auth = await checkToken().then(oauth => {
        if (!oauth) {
            return false;
        }
        return fetch('https://id.twitch.tv/oauth2/validate', {headers: {'Authorization': 'OAuth ' + oauth}})
            .then(response => {
                if (!response.ok) {
                    if (response.status == 401) {
                        console.warn("Token invalid (expired?) - refresh")
                        document.cookie = `token=; Max-Age=0; path=/; domain=${location.hostname}`;
                    }
                    throw new Error('oauth validation failed');
                }
                return response.json();
            })
            .then(authStatus => {
                let token_channel = authStatus["login"];
                if (channel == token_channel) {
                    console.log(`OAuth Token valid for ${channel}`);
                    return oauth;
                } else {
                    console.warn(`OAuth Token invalid for ${channel}`);
                    return false;
                }
            })
            .catch(error => {
                console.warn('Failed to authorize token:', error);
                return false;
            });
    });
    return auth;
}

function getFeature() {
    const url = window.location.pathname;
    var feature = url.split('/')[3]
    return feature ? feature.replace(/\.html$/, '') : feature;
}

function getTheme() {
    const url = window.location.pathname;
    var theme = url.split('/')[2]
    return theme;
}

function getChannel() {
    if (channel != "") {
        return channel;
    }
    const urlParams = new URLSearchParams(window.location.search);
    channel = urlParams.get('channel');
    return channel;
}

const el = document.querySelector("#app");
const cmds = el.attributes.client.value.split(',');
const app = createApp(
{
    props: {
        client: {
            type: Array,
            required: true
        }
    },
    data: function() {
        return {
            alert: "",
            auth: getAuth(),
            backoff: 1000,
            channel: getChannel(),
            config: {},
            curChannel: "",
            feature: getFeature(),
            incoming: [],
            reconnectTimer: null,
            scene: null,
            theme: getTheme(),
            token: null,
            tokenRefreshTimer: null,
        }
    },
    methods: {
        updateCfg: function(data) {
            this.config = data;
        },
        getToken: function() {
            getAuth().then(auth => {
                if (auth) {
                    // Token still valid — reschedule the next check
                    this.token = auth;
                    this.tokenRefreshTimer = window.setTimeout(() => { this.getToken(); }, 14500000);
                    return;
                }
                // Token expired — ask the server to refresh using its stored refresh token
                fetch(`/api/token/refresh?channel=${encodeURIComponent(this.channel)}`)
                    .then(resp => {
                        if (!resp.ok) throw new Error('refresh failed');
                        return resp.json();
                    })
                    .then(data => {
                        // Server refreshed and set the cookie; update in-memory token too
                        document.cookie = `token=${data.access_token}; max-age=${data.expires_in}; path=/; secure`;
                        document.cookie = `user=${this.channel}; max-age=${data.expires_in * 24}; path=/; secure`;
                        this.token = data.access_token;
                        this.tokenRefreshTimer = window.setTimeout(() => { this.getToken(); }, 14500000);
                    })
                    .catch(() => {
                        // Server can't refresh either — only redirect if there's a menu (not OBS overlays)
                        if (!document.getElementsByClassName("menu")[0]) return;
                        document.location = `/user_auth?feature=${this.feature}&channel=${this.channel}&theme=${this.theme}`;
                    });
            });
        },
        getClientConfig: function() {
            var clientConfig = this.config;
            for (var i = 0; i < cmds.length; i++) {
                clientConfig[cmds[i]] = this.channel;
            }
            clientConfig["channel"] = this.channel;
            if (this.token) {
                clientConfig["auth"] = this.token;
            }
            clientConfig["for"] = document.title;
            return JSON.stringify(clientConfig);
        },
        loadData: function(event) {
            this.incoming.push(event);
        },
        unload: function () {
            if ("chatsocket" in this) {
                this.chatsocket.onclose = null;
                this.chatsocket.close();
            }
        },
        socket_open: function () {
            console.log("Connected to backend")
            if (this.$refs.menu) {
                this.$refs.menu.channelAuthed = !!(this.config["pubsub"] && this.token);
            }
            this.backoff = 1000;
            this.chatsocket.send(this.getClientConfig());
            this.chatsocket.onmessage = this.loadData;
            this.chatsocket.onclose = this.socket_close;

            // Schedule token validation — clear any previous timer first so
            // multiple reconnects don't stack up separate redirect timers
            clearTimeout(this.tokenRefreshTimer);
            this.tokenRefreshTimer = window.setTimeout(() => { this.getToken(); }, 14500000);
        },
        socket_close: function () {
            this.scheduleReconnect();
        },
        scheduleReconnect: function() {
            // A dropped socket fires both onerror and onclose — schedule once.
            if (this.reconnectTimer) {
                return;
            }
            this.backoff = Math.min(this.backoff * 1.5, 60000);
            this.reconnectTimer = setTimeout(() => {
                this.reconnectTimer = null;
                this.connect();
            }, this.backoff);
        },
        connect: function() {
            if (this.chatsocket) {
                if (this.chatsocket.readyState <= 1 /* connecting or open */) {
                    console.warn("Connect called while already connected");
                    return;
                }
            }

            try {
                this.chatsocket = new WebSocket(websocketLocation);
                this.chatsocket.onerror = () => { this.scheduleReconnect(); };
                this.chatsocket.onopen = this.socket_open
            }
            catch(error) {
                if (this.backoff == 1000) {
                    console.log("Failed to connect - retrying");
                    console.log(error);
                }
                this.scheduleReconnect();
            }
        },
    },
    watch: {
        'config': {
            handler: function (newConfig) {
                localStorage.config = JSON.stringify(newConfig);
            },
            deep: true
        },
        incoming: {
            handler(events) {
                if (events.length == 0) {
                    return;
                }
                if (events.length > 1) {
                    console.log("Processing " + events.length + " events at once!");
                }
                for (const event of events) {
                    let msg = JSON.parse(event.data);
                    if (this.$refs.alerthandler) {
                        this.$refs.alerthandler.do_alert(msg);
                    }
                    if (this.$refs.pokey && (msg.type === "SUB" || msg.type === "SUBGIFT")) {
                        this.$refs.pokey.addSegment();
                    }
                    if (this.$refs.pokey && msg.type === "TWITCHCHATMESSAGE") {
                        const name = msg.tags && msg.tags["display-name"];
                        if (name) this.$refs.pokey.greet(name);
                    }
                    switch(msg.type) {
                        case "BANNED":
                            alert("Banned from " + msg.channel)
                            this.chatsocket.onclose = null;
                            this.chatsocket.close();
                            break;
                        case "REDEMPTION":
                            break;
                        case "BITS":
                            msg.type = "TWITCHCHATMESSAGE";
                        case "HOSTED":
                        case "RAID":
                        case "FOLLOW":
                        case "SUBGIFT":
                        case "SUB":
                        case "TWITCHCHATUSERNOTICE":
                            if (!this.config["alert"]) {
                                console.log(msg);
                                break;
                            }
                            // No Break: flow through
                        case "SYSTEM":
                            if (msg.message == "ERR_BADAUTH") {
                                this.getToken()
                            }
                        case "TWITCHCHATMESSAGE":
                            if (this.$refs.chatwindow)
                            {
                                this.$refs.chatwindow.add_msg(msg)
                            }
                            break;
                        case "BOTINFO":
                            if (this.$refs.pokey) {
                                this.$refs.pokey.ignore(msg.username);
                            }
                            break;
                        case "POKEYSPEAK":
                            if (this.$refs.pokey) {
                                this.$refs.pokey.say(msg.message);
                            }
                            break;
                        case "CLEARMSG":
                            if (this.$refs.chatwindow)
                            {
                                this.$refs.chatwindow.clear(msg.id);
                            }
                            break;
                        case "CLEARCHAT":
                            if (this.$refs.chatwindow)
                            {
                                if (msg["user"]) {
                                    this.$refs.chatwindow.clear(null, msg["user"], msg["room"]);
                                } else {
                                    this.$refs.chatwindow.clear();
                                }
                            }
                            break;
                        case "HOST":
                            const follow = this.config["hosts"];
                            console.log("Hosting: " + msg.message + " follow: " + follow);
                            if (!follow) {
                                break;
                            }
                            if ('URLSearchParams' in window) {
                                var searchParams = new URLSearchParams(window.location.search);
                                searchParams.set("channel", msg.message);
                                window.location.search = searchParams.toString();
                            }
                            break;
                        default:
                            console.log(msg);
                    };
                }
                this.incoming.length = 0;
            },
            deep: true
        },
    },
    created: function () {
        window.addEventListener('beforeunload', this.unload);
    },
    mounted: function () {
        var show_menu;
        if (localStorage.config) {
            this.config = JSON.parse(localStorage.config);
            show_menu = this.config["menu"];
        } else {
            show_menu = false;
        }
        if (!this.channel) {
            console.warn("No channel specified");
            return;
        }
        if (this.config["pubsub"]) {
            this.auth.then(auth => {
                if (auth) {
                    this.token = auth;
                } else {
                    console.log("No valid auth for this channel — connect without auth");
                }
                this.connect();
            });
        } else {
            this.connect();
        }

        if (document.getElementsByClassName("menu")[0]) {
            if(show_menu) {
                document.getElementsByClassName("menu")[0].style.opacity = "1";

                this.menu_timeout = setTimeout(function() {
                    document.getElementsByClassName("menu")[0].style.opacity = "0";
                }, 10000);
            }

            window.addEventListener("keypress", function() {
                document.getElementsByClassName("menu")[0].style.opacity = "1";
                clearTimeout(this.menu_timeout);
                this.menu_timeout = setTimeout(function() {
                    document.getElementsByClassName("menu")[0].style.opacity = "0";
                }, 3000);
            }.bind(this));
        }

        this.curChannel = getChannel();
        if ("obsstudio" in window) {
            window.obsstudio.getCurrentScene((scene) => {
                this.scene = scene;
            });
        }
    },

    beforeUnmount: function(){
        if (this.chatsocket) {
            this.chatsocket.close();
        }
    }
},
{
    client: cmds
}
);

app.component(
    'chat-window', component_chatwindow
).component(
    'config-menu', component_config
).component(
    'view-select', component_views
).component(
    'media-content', component_animations.mediaContent
).component(
    'banner', component_animations.banner
).component(
    'pokey-widget', component_pokey
)
app.mount("#app")

export default app;
