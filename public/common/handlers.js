"use strict";
import { createApp} from 'https://unpkg.com/vue@3/dist/vue.esm-browser.js'
import component_chatwindow from './chat-window.js'
import component_config from './config.js'
import component_sound from './sounds.js'
import component_views from './views.js'
import component_animations from './animation.js'

var alternator = true;
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

var config = {
}

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
            // TODO: Reauth method (aka logout button)
            console.warn("Token not for channel")
            return Promise.resolve(null);
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
    // "chat.html"
    const url = window.location.pathname;
    var feature = url.split('/')[3]
    return feature;
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
            backoff: null,
            channel: getChannel(),
            config: {},
            curChannel: "",
            feature: getFeature(),
            incoming: [],
            scene: null,
            status: "Unknown",
            theme: getTheme(),
            token: null,
        }
    },
    methods: {
        updateCfg: function(data) {
            this.config = data;
        },
        getToken: function() {
            // Note: this may not return!
            if (checkToken() === null) {
                return;
            }
            document.location = `/user_auth?feature=${this.feature}&channel=${this.channel}&theme=${this.theme}`;
        },
        getClientConfig: function() {
            const channel = getChannel();
            const el = document.querySelector("#app");
            const cmds = el.attributes.client.value.split(',');
            var clientConfig = this.config;
            for (var i = 0; i < cmds.length; i++) {
                clientConfig[cmds[i]] = channel;
            }
            clientConfig["channel"] = channel
            if (this.token) {
                clientConfig["auth"] = this.token;
            }
            clientConfig["for"] = document.title;
            return JSON.stringify(clientConfig);
        },
        loadData: function(event) {
            if (!Array.isArray(this.incoming)) {
                this.incoming = [event];
            } else {
                this.incoming.push(event);
            }
        },
        unload: function (event) {
            if ("chatsocket" in this) {
                this.chatsocket.onclose = null;
                this.chatsocket.close();
            }
        },
        socket_open: function () {
            console.log("Connected to backend")
            this.status = "Connected"
            if (this.config["pubsub"]) {
                checkToken().then(oauth => {
                    if (oauth) {
                        this.status += " (Auth)";
                    } else {
                        this.status += " (Auth Failed)";
                    }
                });
            }
            this.backoff = 1000;
            this.chatsocket.send(this.getClientConfig());
            this.chatsocket.onmessage = this.loadData;
            this.chatsocket.onclose = this.socket_close;
        },
        socket_close: function () {
            this.status = "Reconnecting"
            setTimeout(this.connect(), 2000);
        },
        connect: function() {
            if (!Number.isInteger(this.backoff)) {
                this.backoff = 1000;
            } else {
                this.backoff *= 1.5
            }
            var boundReconnect = this.connect.bind(this);
            if (this.chatsocket) {
                if (this.chatsocket.readyState <= 1 /* connecting or open */) {
                    console.warn("Connect called while already connected");
                    return;
                }
            }

            try {
                this.chatsocket = new WebSocket(websocketLocation);
                this.chatsocket.onerror = function() {
                        setTimeout(boundReconnect, this.backoff);
                };
                this.chatsocket.onopen = this.socket_open
            }
            catch(error) {
                if (this.backoff == 1000) {
                    console.log("Failed to connect - retrying");
                    console.log(error);
                }
                setTimeout(boundReconnect, this.backoff);
            }
        }
    },
    watch: {
        'config': {
            handler: function (newConfig) {
                localStorage.config = JSON.stringify(newConfig);
            },
            deep: true
        },
        status(value) {
            if (this.$refs.menu) {
                this.$refs.menu.status = value;
            }
        },
        incoming: {
            handler(events, oldevts) {
                if (events.length == 0) {
                    return;
                }
                if (events.length > 1) {
                    console.log("Processing " + events.length + " events at once!");
                }
                for (const event of events) {
                    let msg = JSON.parse(event.data);
                    if (this.config["sound"] && this.$refs.soundhandler) {
                        this.$refs.soundhandler.do_alert(msg);
                    }
                    if (this.$refs.alerthandler) {
                        this.$refs.alerthandler.do_alert(msg);
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
                            if (msg.type == "BITS") { msg.type = "TWITCHCHATMESSAGE" }
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
                            follow = this.config["hosts"];
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
            show_menu = this.$children[0].menu;
        }
        if (!this.channel) {
            console.warn("No channel specified");
            return;
        }
        if (this.config["pubsub"]) {
            if (!this.auth) {
                console.log("pubsub with no auth")
                checkToken().then(oauth => {
                    console.log(`authstatus ${oauth}`)
                    if (oauth === false) {
                        this.getToken();
                    }
                });
            } else {
                this.auth.then( auth => {

                    if (auth) {
                        this.token = auth;
                        this.connect();
                    } else {
                        if (auth == null) {
                            console.log("No auth for channel")
                            this.status = "Connecting"
                            this.connect();
                        } else {
                            console.log("Auth invalid, aquiring new token")
                            this.status = "Invalid Auth"
                            this.getToken();
                        }
                    }
                })
            }
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

            window.addEventListener("keypress", function(e) {
                document.getElementsByClassName("menu")[0].style.opacity = "1";
                this.menu_timeout = setTimeout(function() {
                    document.getElementsByClassName("menu")[0].style.opacity = "0";
                }, 3000);
            }.bind(this));
        }

        this.curChannel = getChannel();
        if ("obsstudio" in window) {
            window.obsstudio.getCurrentScene(function (scene) {
                this.scene = scene;
            })
        }
    },

    beforeDestroy: function(){
        this.chatsocket.close();
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
    'sound-handler', component_sound
).component(
    'view-select', component_views
).component(
    'chase', component_animations.chase
).component(
    'banner', component_animations.banner
)
app.mount("#app")

export default app;