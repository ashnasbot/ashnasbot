new Vue({
	el: '#follows',
	data: {
		message: "",
		ping: null,
	},
	methods: {
        loadData: function() {
		name = event.data
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
		this.message = p.outerHTML;
  		setTimeout(function(){
		       this.message = "";
	       	}.bind(this), 10000);
        },
	socket_open: function () {
		this.chatsocket.send("follow");
		this.chatsocket.onmessage = this.loadData;
		this.chatsocket.onclose = this.reconnect;
		if (this.ping) {
			clearInterval(this.ping);
		}
		this.ping = setInterval(function(){
			this.chatsocket.send("ping");
		}.bind(this), 20000);
	},
        reconnect: function() {
                this.chatsocket = new WebSocket("ws://localhost:8765/");
                this.chatsocket.onopen = this.socket_open
		}
	},
	mounted: function () {
		this.chatsocket = new WebSocket("ws://localhost:8765/");
		this.chatsocket.onopen = this.socket_open
	},

	beforeDestroy: function(){
		this.chatsocket.close();
	}
});


