// Load at startup, this is done async
var synth = window.speechSynthesis;
var voice;
synth.getVoices();
window.speechSynthesis.onvoiceschanged = function() {
	voice = synth.getVoices()[0].name;
};


Vue.component('sound-handler', {
	template: '<div style="display:none;"></div>',
	props: {
		tts: {
			type: Boolean,
			default: false,
		}
	},
	data: function () {
        var urlChunks = location.pathname.split('/');
        return {view: urlChunks[urlChunks.length - 2], audio: null, playqueue: []};
	},
    methods: {
        do_alert: function (msg) {
			try {
				this.playsound(msg);
			} catch(err) {
				console.warn(err);
			}
		},
		playsound: function (msg) {
			var path;
			var speech = msg.orig_message;
			switch (msg.type) {
				case "BITS":
					re = /^(\w*Cheer\d+\(s+|$)+/i
					if (msg.orig_message.match(re)) {
						// Skip messages that are just bits
					    speech = "";
					} else {
						// a little over zealous
						speech = msg.orig_message.replace(/\w+\d+/, "");
					}
					ammount = msg.tags["bits"]
					path = `/res/${this.view}/sound/bits?value=${ammount}`;
					break;
				case "SUBGIFT":
					path = `/res/${this.view}/sound/sub`;
					speech = "";
					break;
				case "SUB":
					path = `/res/${this.view}/sound/sub`;
					speech = `${msg.nickname} just subscribed. ${msg.orig_message}`
					break;
				case "FOLLOW":
				    path = `/res/${this.view}/sound/follow`;
					break;
				case "RAID":
				    path = `/res/${this.view}/sound/raid`;
					break;
				case "HOSTED":
				    path = `/res/${this.view}/sound/host`;
					break;
				case "REDEMPTION":
				    path = `/res/${this.view}/sound/${msg.tags["reward-title"]}`;
					break;
				default:
					return;
			}
			audio = new Audio(path);
			this.playqueue.push([audio, speech]);
			if (this.playqueue.length == 1)
			{
				this.play();
			}
		},
		play: function() {
			if (this.playqueue.length > 0){
				data = this.playqueue[0];
				audio = data[0];
				speech = data[1];
				if (this.audio && !this.audio.paused) {
					/* another audio is playing, queue for after */
					this.audio.addEventListener("ended", function () {
						this.audio = audio;
						audio.play().then(function(resp) {
							this.do_tts(audio, speech);
						}).catch(function(error) {
							console.error(error)
							this.playqueue.shift();
						})
					}.bind(this))
				} else {
					/* no audio is playing, play */
					this.audio = audio;
					audio.play().then(function(resp) {
						this.do_tts(audio, speech);
					}).catch(error => {
						console.error(error);
						this.playqueue.shift();
					})
				}
			}
		},
		do_tts: function(audio, msg) {
			if (this.tts && voice) {
				audio.addEventListener("ended", function () {
					var utterThis = new SpeechSynthesisUtterance(msg);
					synth.speak(utterThis);
					utterThis.onend = function() {
						/* unshift needs to wait until the end */
						this.playqueue.shift();
						/* play next queue item, if any */
						this.play();
					}.bind(this)
				}).bind(this);
			} else {
				this.playqueue.shift();
				this.play();
			}
		}
    }
});
