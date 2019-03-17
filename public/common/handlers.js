/* 
 * Max messages before several will be deleted per batch
 * Helps with high loads
 */
var max_messages = 25

new Vue({
    el: '#app',
    props: ['client'],
    data: {
        chat: [],
        alert: "",
        ping: null,
    },
    methods: {
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
                    break;
                default: 
                    console.log(msg);
            };
        },
        socket_open: function () {
            console.log("Connected")
            this.chatsocket.send(this.$el.attributes.client.value);
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
            this.reconnect();
        },
        reconnect: function() {
            try {
                this.chatsocket = new WebSocket("ws://localhost:8765/");
                this.chatsocket.onerror(
                    function() {
                        setTimeout(this.reconnect, 5000);
                    });
                this.chatsocket.onopen = this.socket_open
            }
            catch(error) {
                setTimeout(this.reconnect, 1000);
            }
        }
    },
    mounted: function () {
        this.chatsocket = new WebSocket("ws://localhost:8765/");
        this.chatsocket.onopen = this.socket_open
        var chat = document.getElementById('app');
        setInterval(function() {
            if (checkOverflow(chat)) {
                this.chat.shift();
            }
        }.bind(this), 300);

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
        audio.play();
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
