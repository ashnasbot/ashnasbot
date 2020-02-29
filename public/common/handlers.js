/* 
 * Max messages before several will be deleted per batch
 * Helps with high loads
 */
var max_messages = Math.floor(window.innerHeight / 30 );

// Load at startup, this is done async (we should use window.speechSynthesis.onvoiceschanged)
var synth = window.speechSynthesis;
var voices = synth.getVoices();

// This serves only to stop random things knocking the websocket
// can filter though proxy
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

function getChannel() {
    if (channel != "") {
        return channel;
    }
    const urlParams = new URLSearchParams(window.location.search);
    channel = urlParams.get('channel');
    return channel;
}

Vue.component('config-menu', {
    mounted: function () {
        if (localStorage.config) {
            config = JSON.parse(localStorage.config);
            this.commands = config.commands;
            this.follows = config.follows;
            this.images = config.images;
            this.alerts = config.alerts;
            this.sound = config.sound;
            this.hosts = config.hosts;
            this.menu = config.menu;
        }
    },
    methods: {
        handleInput () {
            data = Object.fromEntries(Object.entries(this._data));
            this.$emit("cfg-update", data);
        }
    },
    data: function () {
      return {
        commands: true,
        follows: false,
        images: true,
        alerts: true,
        sound: true,
        hosts: false,
        menu: true
      }
    },
    watch: {
        commands(n) { this.handleInput(); },
        follows(n) { this.handleInput(); },
        images(n) { this.handleInput(); },
        alerts(n) { this.handleInput(); },
        sound(n) { this.handleInput(); },
        hosts(n) { this.handleInput(); },
        menu(n) { this.handleInput(); },
    },
    template: `
    <div class="popout">
    <div class="form">
    <span>Press 'Submit' to set config </span>
    <label>Allow commands<input name="commands" type="checkbox" v-model="commands"> </label>
    <!--<label>Show follows<input name="follows" type="checkbox" v-model="follows"></label>-->
    <label>Pull Avatars<input name="images" type="checkbox" v-model="images"></label>
    <label>Show Chat Notifications<input name="alerts" type="checkbox" v-model="alerts"></label>
    <label>Sounds<input name="sound" type="checkbox" v-model="sound"></label>
    <label>Follow Hosts<input name="hosts" type="checkbox" v-model="hosts"></label>
    <label>Show menu on load<input name="menu" type="checkbox" v-model="menu"></label>
    </div>
    </div>
    `
  })

new Vue({
    el: '#app',
    props: ['client', 'incoming'],
    data: {
        chat: [],
        config: {},
        alert: "",
        alertLog: [],
        ping: null,
        channel: getChannel(),
        curChannel: ""
    },
    methods: {
        updateCfg: function(data) {
            this.config = data;
        },
        getClientConfig: function() {
            const channel = getChannel();
            const cmds = this.$el.attributes.client.value.split(',');
            clientConfig = this.config;
            for (var i = 0; i < cmds.length; i++) {
                clientConfig[cmds[i]] = channel;
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
            this.chatsocket.onclose = null;
            this.chatsocket.close();
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
        config(newConfig) {
            
            localStorage.config = JSON.stringify(newConfig);
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
                switch(msg.type) {
                    case "BANNED":
                        alert("Banned from " + msg.channel)
                        this.chatsocket.onclose = null;
                        this.chatsocket.close();
                        break;
                    case "SUB":
                        if (self.config["alerts"]) {
                            do_alert(msg, this, this.config["sound"]);
                        }
                        // No Break: flow through
                    case "TWITCHCHATUSERNOTICE":
                        if (!self.config["alerts"]) {
                            console.log(msg);
                            break;
                        }
                        // No Break: flow through
                    case "TWITCHCHATMESSAGE":
                        ts = performance.now();
                        msgtimes.push(ts);
                        chat = this.chat.concat(msg);
                        var container = document.getElementById('chat');
                        if (container == null){
                            container = document.getElementById('app');
                        }
                        if (checkOverflow(container)) {
                            this.chat.shift();
                        }
                        this.chat = chat.slice(Math.max(
                            chat.length - max_messages, 0)
                        );
                        break;
                    case "CLEARMSG":
                        this.chat = this.chat.filter(m => m.id != msg.id)
                        break;
                    case "CLEARCHAT":
                        this.chat = this.chat.filter(m => msg.id != m.tags["user-id"]);
                        break;
                    case "FOLLOW":
                        do_alert(msg, this, this.config["sound"]);
                        this.alertLog.push(msg)
                        console.log(msg.message);
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
        var show_menu;
        if (localStorage.config) {
            this.config = JSON.parse(localStorage.config);
            show_menu = this.config["menu"];
        } else {
            show_menu = this.$children[0].menu;
        }

        this.connect();
        var chat = document.getElementById('chat');
        if (chat == null){
            var chat = document.getElementById('app');
        }
        setInterval(function() {
            if (checkOverflow(chat)) {
                this.chat.shift();
            }
        }.bind(this), 300);

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

        this.curChannel = getChannel();

        if (localStorage.getItem('chat-' + this.curChannel)) {
            try {
              save = JSON.parse(localStorage.getItem('chat-' + this.curChannel));
              console.log(save.ts)
              console.log(Date.now() - 600000)
              if (save.ts > (Date.now() - 600000)){
                  this.chat = save.chat;
              } else {
                  console.log("Cache exists but is over 10 minutes old")
              }
            } catch(e) {
              localStorage.removeItem('chat-' + this.curChannel);
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

    var isOverflowing = el.clientHeight < el.scrollHeight;

    el.style.overflow = curOverflow;

    return isOverflowing;
}

// Alert handling - WIP
function do_alert(event, app, sounds)
{
    name = event.nickname
    if (event.audio && sounds) {
        var audio = new Audio(event.audio);
        audio.play().then(function(){
            audio.addEventListener("ended", function(){
                voice = synth.getVoices()[0].name;
                var utterThis = new SpeechSynthesisUtterance(event.orig_message);
                synth.speak(utterThis);
            });
        });
    }

    if (event.type == "FOLLOW") {
        var suffix = " gets whacked!"

        var d = Math.random();
        if (d < 0.05) {
            suffix = " gets quacked!"
        }

        var p = document.createElement("p"); 
        p.classList.add('toast-inner');
        // and give it some content 
        var mContent = document.createTextNode(name + suffix); 
        // add the text node to the newly created div
        p.appendChild(mContent);
        app.alert = p.outerHTML;
        setTimeout(function(){
            app.alert = "";
        }.bind(app), 10000);
        return
    }
    if (event.type == "RAID") {
        var p = document.createElement("p"); 
        p.classList.add('toast-inner');
        // and give it some content 
        var mContent = document.createTextNode(event.message); 
        // add the text node to the newly created div
        p.appendChild(mContent);
        app.alert = p.outerHTML;
        return
    }
    if (event.type == "SUB") {
        console.log("Sub alert")
    }

    setTimeout(function(){
        app.alert = "";
    }.bind(app), 10000);
}

window.onresize = function(event) {
    max_messages = Math.floor(window.innerHeight / 30 );
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
  window.requestAnimationFrame(() => {
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
    refreshLoop();
  });
}

refreshLoop();

