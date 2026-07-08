"use strict";
var alternator, container;
const viewport = document.defaultView; // "window isn't available, but document is"

export default {
    props: {
        client: {
            type: Array,
            required: true
        }
    },
	data: function() {
		return {
			messages: [],
            channel: null,
		}
	},
    template: `<div v-cloak class="chat_window frame">
		<transition-group name="slide-fade" tag="ol" id="chat" mode="out-in" appear
            v-on:after-enter="checkOverflow" v-on:after-leave="checkOverflow">
		<li v-for="msg in messages" v-bind:key="msg.id" v-bind:id="msg.id" v-bind:class="[msg.alternator ? 'even' : 'odd']" >
			<div v-bind:class="msg.type" >
				<div v-if="msg.type != 'TWITCHCHATMESSAGE'" class="alert" v-html="msg.tags['system-msg']"></div>
				<template v-if="msg.message">
					<span class="badges">
						<span v-for="badge in msg.badges" v-html="badge"></span>
					</span>
					<span class="nickname" v-bind:class="msg.extra" v-bind:style="{ color: msg.tags[&quot;color&quot;] }"
						  v-html="msg.nickname"></span>
					<span v-if="msg.extra && msg.extra.includes(&quot;quoted&quot;)" class="message" v-bind:class="{ jumbo: msg.tags[&quot;jumbo&quot;] }"
						  v-html="msg.message"></span>
					<span v-else v-bind:style="{ color: msg.tags[&quot;color&quot;] }" class="message me"
					      v-html="msg.message"></span>
				</template>
			</div>
		</li>
		</transition-group>
	</div>`,
	methods:
	{
		add_msg: function(msg)
		{
			// for rate handling
			msgtimes.push(performance.now());

			// CSS uses this
			msg.alternator = alternator;
			alternator = !alternator;

			this.messages.push(msg);
		},
        clear: function(id, user, room) {
            if (id) {
                this.messages = this.messages.filter(m => m.id != id);
            } else if (user) {
                this.messages = this.messages.filter(m => m["tags"]["user-id"] != user || m["tags"]["room-id"] != room);
            } else {
                /* If no user, clear all */
                this.messages = [];
            }
        },
		checkOverflow: function() {
			/* check overflow, and shift elements until we're under it */
			const isScrolledToBottom = container.scrollHeight - container.clientHeight <= container.scrollTop + 1
			if (isScrolledToBottom) {
				container.scrollTop = container.scrollHeight - container.clientHeight
			}
			if (checkOverflow(container)) {
				if (this.messages.length > 1) {
					this.messages.shift();
				}
			}
		},
        store_chat: function(event) {
            let save = {
                ts: Date.now(),
                chat: this.messages
            }
            const parsed = JSON.stringify(save);
            localStorage.setItem('chat-' + this.channel, parsed);
        },
    },
    mounted: function() {
        viewport.onbeforeunload = this.store_chat;
		container = this.$el.querySelector("#chat");
        alternator = false;

        const urlParams = new URLSearchParams(viewport.location.search);
        this.channel = urlParams.get('channel');

        var clientCfg = this.client;

        if ("obsstudio" in viewport) {
            viewport.addEventListener('obsSceneChanged', function(event) {
                this.store_chat();
            }.bind(this))
        }

        if (clientCfg.includes("chat")) {
            if (localStorage.getItem('chat-' + this.channel)) {
                try {
                    let save = JSON.parse(localStorage.getItem('chat-' + this.channel));
                    if (save.ts > (Date.now() - 600000)){
                        this.messages = save.chat;
                        if(this.messages.length > 0) {
                            alternator = !this.messages[this.messages.length - 1].alternator
                        }
                    } else {
                        console.log("Cache exists but is over 10 minutes old")
                    }
                } catch(e) {
                    localStorage.removeItem('chat-' + this.channel);
                }
            }
        }
    }
};

// Animation speed handling
const msgtimes = [];
let msgrate;
let animrate = "0.3s";

function setSlideDelay(rate) {
    for (const ss of document.styleSheets) {
        if (!ss.href || !ss.href.endsWith("textbox.css")) {
            continue;
        }
        let rules;
        try {
            rules = ss.cssRules;
        } catch (e) {
            continue; // cross-origin sheet
        }
        for (const r of rules) {
            if (!r.style || !r.selectorText) {
                continue;
            }
            if (r.style["transition-duration"] && r.selectorText.includes("slide-fade")) {
                r.style["transition-duration"] = rate;
            }
        }
    }
}

// Determines if the passed element is overflowing its visible bounds.
// Uses #app.clientHeight as the constraint: intermediate ancestors like
// .chat_window resolve height:100% to auto when their parent has no explicit
// height, so they grow with the content and cannot be used as a limit.
// #app always has an explicit height (100vh base, 50vh+zoom:200% earthbound, etc).
function checkOverflow(el)
{
    if (document.hidden) {
        return false;
    }
    const app = document.getElementById('app');
    const maxHeight = app ? app.clientHeight : viewport.innerHeight;
    return el.scrollHeight > maxHeight;
}

function refreshLoop() {
    function refresh() {
        viewport.requestAnimationFrame(refresh);
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
