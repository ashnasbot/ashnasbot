/* 
 * Max messages before several will be deleted per batch
 * Helps with high loads
 */
var max_messages, msg_size, scale_factor;

var alternator = true;

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

function getAuth() {
    var auth = null;
    var token_channel = null;
    var oauth;
    try {
        oauth = cookies
            .split('; ')
            .find(row => row.startsWith('token'))
            .split('=')[1];
    } catch(err) {
        console.log("No auth")
        return null;
    }
    try {
        token_channel = cookies
            .split('; ')
            .find(row => row.startsWith('user'))
            .split('=')[1];
    } catch { }

    if (channel == token_channel) {
        return (new Promise(oauth => {return oauth}));
    }

    return fetch('https://id.twitch.tv/oauth2/validate', {headers: {'Authorization': 'OAuth ' + oauth}})
        .then(response => {
            if (!response.ok) {
                throw new Error('oauth validation failed');
            }
            return response.json();
        })
        .then(authStatus => {
            token_channel = authStatus["login"];
            channel = this.getChannel();
            if (channel == token_channel) {
                console.log(`OAuth Token valid for ${channel}`);
                document.cookie = `user=${channel};path=/`;
                auth = oauth;
            } else {
                console.warn(`OAuth Token invalid for ${channel}`);
            }
        })
        .catch(error => {
            console.warn('Failed to authorize token:', error);
            auth = false;
        })
        .then((response) => auth);
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

new Vue({
    el: '#app',
    props: ['client', 'incoming'],
    data: {
        auth: getAuth(),
        token: null,
        chat: [],
        config: {},
        alert: "",
        ping: null,
        channel: getChannel(),
        theme: getTheme(),
        curChannel: ""
    },
    methods: {
        updateCfg: function(data) {
            this.config = data;
        },
        getToken: function() {
            // Note: this may not return!
            document.location = "/user_auth?channel=" + this.channel + "&theme=" + this.theme;
        },
        getClientConfig: function() {
            const channel = getChannel();
            const cmds = this.$el.attributes.client.value.split(',');
            clientConfig = this.config;
            for (var i = 0; i < cmds.length; i++) {
                clientConfig[cmds[i]] = channel;
            }
            clientConfig["channel"] = channel
            if (this.token) {
                clientConfig["auth"] = this.token;
            }
            return JSON.stringify(clientConfig);
        },
        loadData: function() {
            if (event.data == "ping") {
                this.chatsocket.send("pong");
                return;
            }
            if (!Array.isArray(this.incoming)) {
                this.incoming = [];
            }
            this.incoming.push(event);
        },
        unload: function (event) {
            save = {
                ts: Date.now(),
                chat: this.chat
            }
            const parsed = JSON.stringify(save);
            localStorage.setItem('chat-' + this.curChannel, parsed);
            if ("chatsocket" in this) {
                this.chatsocket.onclose = null;
                this.chatsocket.close();
            }
        },
        socket_open: function () {
            console.log("Connected")
            this.chatsocket.send(this.getClientConfig());
            this.chatsocket.onmessage = this.loadData;
            this.chatsocket.onclose = this.socket_close;
            if (this.ping) {
                clearInterval(this.ping);
            }
            this.ping = setInterval(function(){
                if (this.chatsocket.readystate == "OPEN") {
                    this.chatsocket.send("ping");
                } else {
                    clearInterval(this.ping);
                    this.ping = null;
                }
            }.bind(this), 20000);
        },
        socket_close: function () {
            if (this.ping) {
                clearInterval(this.ping);
                this.ping = null;
            }
            this.connect();
        },
        connect: function() {
            var boundReconnect = this.connect.bind(this);
            try {
                this.chatsocket = new WebSocket(websocketLocation);
                this.chatsocket.onerror = function() {
                        setTimeout(boundReconnect, 5000);
                };
                this.chatsocket.onopen = this.socket_open
            }
            catch(error) {
                console.log(error);
                setTimeout(boundReconnect, 1000);
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
        incoming(events) {
            if (events.length == 0) {
                return;
            }
            if (events.length > 1) {
                console.log("Processing " + events.length + " events at once!");
            }
            for (const event of events) {
                msg = JSON.parse(event.data);
                if (this.config["sound"] && this.$refs.soundhandler) {
                    this.$refs.soundhandler.do_alert(msg);
                }
                switch(msg.type) {
                    case "BANNED":
                        alert("Banned from " + msg.channel)
                        this.chatsocket.onclose = null;
                        this.chatsocket.close();
                        break;
                    case "BITS":
                        if (msg.type == "BITS") { msg.type = "TWITCHCHATMESSAGE" }
                    case "HOSTED":
                    case "RAID":
                        if (["RAID", "HOSTED"].includes(msg.type)){
                            if (this.$refs.raidhandler) {
                                this.$refs.raidhandler.do_alert(msg);
                            }
                        }
                    case "FOLLOW":
                    case "SUBGIFT":
                    case "SUB":
                    case "REDEMPTION":
                    case "TWITCHCHATUSERNOTICE":
                        if (!this.config["alert"]) {
                            console.log(msg);
                            break;
                        }
                        // No Break: flow through
                    case "SYSTEM":
                        if (msg.message == "ERR_BADAUTH") {
                            this.refresh_token()
                        }
                    case "TWITCHCHATMESSAGE":
                        ts = performance.now();
                        msgtimes.push(ts);
                        msg.alternator = alternator;
                        alternator = !alternator;
                        chat = this.chat.concat(msg);
                        var container = document.getElementById('chat');
                        if (container == null){
                            container = this.$el;
                        }
                        if (checkOverflow(container)) {
                            if (this.chat.length > 1) {
                                this.chat.shift();
                            }
                        }
                        this.chat = chat.slice(Math.max(
                            chat.length - max_messages, 0)
                        );
                        break;
                    case "CLEARMSG":
                        this.chat = this.chat.filter(m => m.id != msg.id);
                        break;
                    case "CLEARCHAT":
                        if (msg["user"]) {
                            this.chat = this.chat.filter(m => m["tags"]["user-id"] != msg["user"] || m["tags"]["room-id"] != msg["room"]);
                        } else {
                            /* If no user, clear all */
                            this.chat = [];
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
            this.incoming = [];
        }
    },
    created: function () {
        window.addEventListener('beforeunload', this.unload)
    },
    mounted: function () {
        var appstyle = window.getComputedStyle(this.$el, null).getPropertyValue('font-size');
        msg_size = parseFloat(appstyle); 
        if (typeof scale_factor === 'undefined') { scale_factor = 1.0;}
        max_messages = Math.floor(window.innerHeight / (msg_size * scale_factor) ) + 1;

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
                this.config["pubsub"] = false;
                this.getToken();
            } else {
                this.auth.then( auth => {

                    if (auth) {
                        this.token = auth;
                        this.connect();
                    } else {
                        // TODO: Display feedback that auth failed
                        if (auth == null) {
                            console.log("No auth for channel")
                            this.connect();
                        } else {
                            console.log("Auth invalid, aquiring new token")
                            this.config["pubsub"] = false;
                            this.getToken();
                        }
                    }
                })
            }
        } else {
            this.connect();
        }

        var chat = document.getElementById('chat');
        if (chat == null){
            var chat = document.getElementById('app');
        }
        setInterval(function() {
            if (checkOverflow(chat)) {
                if (this.chat.length > 1) {
                    this.chat.shift();
                }
            }
            if (this.chat.length > max_messages * 1.1) {
                this.chat = this.chat.slice(Math.max(
                    chat.length - max_messages, 0)
                );
            }
        }.bind(this), 300);

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
        clientCfg = JSON.parse(this.getClientConfig());

        if ("chat" in clientCfg) {
            if (localStorage.getItem('chat-' + this.curChannel)) {
                try {
                save = JSON.parse(localStorage.getItem('chat-' + this.curChannel));
                if (save.ts > (Date.now() - 600000)){
                    this.chat = save.chat;
                    if(this.chat.length > 0) {
                        alternator = !this.chat[this.chat.length - 1].alternator
                    }
                } else {
                    console.log("Cache exists but is over 10 minutes old")
                }
                } catch(e) {
                    localStorage.removeItem('chat-' + this.curChannel);
                }
            }
        }
    },

    beforeDestroy: function(){
        this.chatsocket.close();
    }
});

// Determines if the passed element is overflowing its bounds.
// Will temporarily modify the "overflow" style to detect this
// if necessary.
function checkOverflow(el)
{
    var curOverflow = el.style.overflow;
    if (document.hidden) {
        return false
    }

    if ( !curOverflow || curOverflow === "visible" )
        el.style.overflow = "hidden";

    var isOverflowing = el.clientHeight < el.scrollHeight - 2; /* THIS IS A HACK */

    el.style.overflow = curOverflow;
    if (!isOverflowing){
        isOverflowing = el.scrollHeight > window.innerHeight;
    }

    return isOverflowing;
}

window.onresize = function(event) {
    max_messages = Math.floor(window.innerHeight / (msg_size * scale_factor) ) + 1;
}

// Animation speed handling
// TODO: refactor into component or somesuch
const msgtimes = [];
let msgrate;
let animrate = "0.3s";

function setSlideDelay(rate) {
    for (const ss of document.styleSheets) {
        if (!ss.href) {
            continue;
        }
        if (ss.href.endsWith("textbox.css")) {
            for(const r of ss.cssRules) {
                if (!r.style) {
                    continue;
                }
                if (r.style["transition-duration"] && r.selectorText.includes("slide-fade")){
                    r.style["transition-duration"] = rate;
                }
            }
        }
    }    
}

function refreshLoop() {
    function refresh() {
        window.requestAnimationFrame(refresh);
        const now = performance.now();
        while (msgtimes.length > 0 && msgtimes[0] <= now - 10000) {
        msgtimes.shift();
        }
        msgrate = msgtimes.length/10;
        if (msgrate > 4 && animrate == "0.1s") {
            console.warn("Disable animation to boost rendering");
            animrate = "0s";
            setSlideDelay(animrate);
        } else if (msgrate > 3 && animrate == "0.3s") {
            console.info("Increasing animation rate");
            animrate = "0.1s";
            setSlideDelay(animrate);
        } else if ( msgrate < 1 && animrate != "0.3s") {
            console.warn("Reenabling animations");
            animrate = "0.3s";
            setSlideDelay(animrate);
        }
    };
    refresh();
}

refreshLoop();

