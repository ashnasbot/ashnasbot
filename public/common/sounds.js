// Load at startup, this is done async (we should use window.speechSynthesis.onvoiceschanged)
var synth = window.speechSynthesis;


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
        return {view: urlChunks[urlChunks.length - 2], audio: null};
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
					re = /(\w*Cheer\d+\(s+|$)+/i
					if (msg.orig_message.match(re)) {
						// Skip messages that are just bits
					    speech = "";
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
				default:
					return;
			}
			audio = new Audio(path);
			if (this.audio && !this.audio.paused) {
				this.audio.addEventListener("ended", function () {
					audio.play().then( resp => {
						this.do_tts(audio, speech);
					}).catch(error => {
						console.error(error)
					})
				}.bind(this))
			} else {
				audio.play().then( resp => {
					this.do_tts(audio, speech);
				}).catch(error => {
					console.error(error)
				})
			}
			this.audio = audio;
		},
		do_tts: function(audio, msg) {
			if (this.tts) {
				audio.addEventListener("ended", function () {
					voice = synth.getVoices()[0].name;
					var utterThis = new SpeechSynthesisUtterance(msg);
					synth.speak(utterThis);
				});
			}
		}
    }
});
