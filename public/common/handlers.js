/* 
 * Max messages before several will be deleted per batch
 * Helps with high loads
 */
var max_messages = Math.floor(window.innerHeight / 60 );

// This serves only to stop random things knocking the websocket
// can filter though proxy
document.cookie = 'secretvalue=true;path=/';
if (document.location.protocol == "https:") {
    websocketLocation = "wss://" + location.hostname + ":443/wsapp"
} else {
    console.warn("Using unsecured websocket")
    websocketLocation = "ws://" + location.hostname + ":8765"
}

function getChannel() {
    // TODO: Cache result
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('channel');
}

new Vue({
    el: '#app',
    props: ['client'],
    data: {
        chat: [],
        alert: "",
        alertLog: [],
        ping: null,
        channel: getChannel()
    },
    methods: {
        getClientConfig: function() {
            const channel = getChannel();
            const cmds = this.$el.attributes.client.value.split(',');
            clientConfig = {};
            for (var i = 0; i < cmds.length; i++) {
                clientConfig[cmds[i]] = channel;
            }
            return JSON.stringify(clientConfig);
        },
        loadData: function() {
            if (event.data == "ping") {
                this.chatsocket.send("pong");
            }
            msg = JSON.parse(event.data);
            switch(msg.type) {
                case "TWITCHCHATMESSAGE":
                    chat = this.chat.concat(msg);
                    this.chat = chat.slice(Math.max(
                        chat.length - max_messages, 0)
                    );
                    break;
                case "FOLLOW":
                case "SUB":
                    do_alert(msg, this);
                    this.alertLog.push(msg)
                    console.log(msg.message);
                    break;
                default: 
                    console.log(msg);
            };
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
            console.log("Connection closed")
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
    mounted: function () {
        this.connect();
        var chat = document.getElementById('app');
        setInterval(function() {
            if (checkOverflow(chat)) {
                this.chat.shift();
            }
        }.bind(this), 300);

        this.menu_timeout = setTimeout(function() {
            document.getElementsByClassName("menu")[0].style.display = "none";
        }, 3000);

        window.addEventListener("keypress", function(e) {
            document.getElementsByClassName("menu")[0].style.display = "block";
            this.menu_timeout = setTimeout(function() {
                document.getElementsByClassName("menu")[0].style.display = "none";
            }, 3000);
        }.bind(this));

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

function do_alert(event, app)
{
    name = event.nickname
    if (event.audio) {
        var audio = new Audio(event.audio);
        audio.play().then(function(){
            var synth = window.speechSynthesis;
            voice = synth.getVoices()[0].name;
            var utterThis = new SpeechSynthesisUtterance(event.orig_message);
            synth.speak(utterThis);
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
        console.log(event)
    }

    setTimeout(function(){
        app.alert = "";
    }.bind(app), 10000);
}

window.onresize = function(event) {
    max_messages = Math.floor(window.innerHeight / 60 );
}
