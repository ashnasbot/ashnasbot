var synth = window.speechSynthesis || null;
var voice;
if (synth) {
	synth.getVoices();
	synth.onvoiceschanged = function() {
		const voices = synth.getVoices();
		if (voices.length) voice = voices[0].name;
	};
}

var mediaContent = {
	template: `<div>
	<canvas ref="screen" width=640 height=480></canvas>
	<banner v-if="alert !== null" v-bind="alert" @finished="onBannerFinished"></banner>
	</div>`,
	props: {
		rate: {  // maximum number of sprites on screen at once
			type: Number,
			default: 50,
		},
		tts: {
			type: Boolean,
			default: false,
		},
		sound: {
			type: Boolean,
			default: true,
		},
	},
	data() {
		const urlChunks = location.pathname.split('/');
		return {
			canvas: null,
			sprites: [],
			view: urlChunks[urlChunks.length - 2],
			alert: null,
			queue: [],
			ready: true,
			bannerDone: true,
			soundDone: true,
		};
	},
	created() {
		// Non-reactive bookkeeping
		this._alertSeq = 0;     // stale-callback guard: bumped per alert
		this._watchdog = null;  // force-completes a jammed alert
	},
	mounted() {
		this.canvas = this.$refs.screen;
		this.canvas.width = window.innerWidth;
		this.canvas.height = window.innerHeight;
		this._onResize = () => {
			this.canvas.width = window.innerWidth;
			this.canvas.height = window.innerHeight;
		};
		window.addEventListener('resize', this._onResize);
		this.mainLoop();
	},
	beforeUnmount() {
		window.removeEventListener('resize', this._onResize);
		clearTimeout(this._watchdog);
	},
	watch: {
		queue: {
			handler(content) {
				if (content.length === 0) return;
				if (this.ready) {
					this.ready = false;
					this._startNext();
				}
			},
			deep: true
		},
		ready(val) {
			if (val && this.queue.length > 0) {
				this.ready = false;
				setTimeout(() => { this._startNext(); }, 1000);
			}
		}
	},
	methods: {
		_startNext() {
			const item = this.queue.shift();
			const seq = ++this._alertSeq;
			this.bannerDone = !item.alertData;
			this.soundDone = !item.soundPath;
			this.alert = item.alertData || null;
			if (item.soundPath) {
				this._playSound(item.soundPath, item.speech, seq);
			}
			// Watchdog: whatever fails (404'd audio, stuck video, wedged TTS),
			// the queue must keep moving.
			clearTimeout(this._watchdog);
			this._watchdog = setTimeout(() => {
				if (!this.bannerDone || !this.soundDone) {
					console.warn("Alert watchdog fired — forcing completion");
					if (this._audio) {
						this._audio.pause();
						this._audio = null;
					}
					this.bannerDone = true;
					this.soundDone = true;
					this._checkDone();
				}
			}, 20000);
		},
		_checkDone() {
			if (this.bannerDone && this.soundDone) {
				clearTimeout(this._watchdog);
				this.ready = true;
				this.alert = null;
			}
		},
		onBannerFinished() {
			this.bannerDone = true;
			this._checkDone();
		},
		_soundFinished(seq) {
			if (seq !== this._alertSeq) {
				return; // late completion from a previous (watchdogged) alert
			}
			this.soundDone = true;
			this._checkDone();
		},
		_playSound(path, speech, seq) {
			const audio = new Audio(path);
			this._audio = audio;
			audio.addEventListener("error", () => {
				console.warn("Alert sound unavailable:", path);
				this._soundFinished(seq);
			}, { once: true });
			audio.addEventListener("canplay", () => {
				audio.addEventListener("ended", () => {
					this._speak(speech, seq);
				}, { once: true });
				audio.play().catch(err => {
					console.error("Alert sound playback failed:", err);
					this._soundFinished(seq);
				});
			}, { once: true });
			audio.load();
		},
		_speak(speech, seq) {
			if (this.tts && synth && voice && speech) {
				const utterThis = new SpeechSynthesisUtterance(speech);
				utterThis.onend = () => this._soundFinished(seq);
				utterThis.onerror = () => this._soundFinished(seq);
				synth.speak(utterThis);
			} else {
				this._soundFinished(seq);
			}
		},
		mainLoop() {
			window.requestAnimationFrame(this.mainLoop);

			if (this.sprites.length > 0) {
				const context = this.canvas.getContext('2d');
				context.clearRect(0, 0, this.canvas.width, this.canvas.height);
				const toRender = this.sprites.slice(0, this.rate);

				toRender.forEach(img => {
					if (!img.update(img)) {
						// cull sprites that die (reach the edge)
						this.sprites.splice(this.sprites.indexOf(img), 1);
					} else {
						img.render();
					}
				});
				if (this.sprites.length === 0) {
					context.clearRect(0, 0, this.canvas.width, this.canvas.height);
				}
			}
		},
		_frameGeometry(img) {
			// Sprite sheets hold square frames laid out horizontally (side by
			// side) or vertically (stacked). Detect the axis from the aspect
			// ratio; a square image is a single frame.
			const vertical = img.height > img.width;
			const frames = Math.max(1, Math.round(
				vertical ? img.height / img.width : img.width / img.height));
			return {
				vertical,
				numberOfFrames: frames,
				frameWidth: vertical ? img.width : img.width / frames,
				frameHeight: vertical ? img.height / frames : img.height,
			};
		},
		sprite(options) {
			const that = {};
			that.frameIndex = 0;
			that.tickCount = 0;
			that.ticksPerFrame = options.ticksPerFrame || 0;
			that.number_of_frames = options.numberOfFrames || 1;
			that.context = options.context;
			that.vertical = options.vertical || false;
			that.frameWidth = options.frameWidth || options.width;
			that.frameHeight = options.frameHeight || options.height;
			that.image = options.image;
			that.x = options.x;
			that.y = options.y;
			that.speed = options.speed;
			if (typeof that.x === 'undefined') {
				if (options.id < this.rate) {
					that.x = options.context.canvas.width + ((options.context.canvas.width / this.rate) * options.id);
				} else {
					that.x = options.context.canvas.width + that.frameWidth;
				}
			}
			if (typeof that.y === 'undefined') {
				that.y = (options.context.canvas.height * 0.25) + (Math.random() * (options.context.canvas.height * 0.5));
			}
			if (typeof that.speed === 'undefined') {
				that.speed = 1.5 + Math.random();
			}
			that.update = options.updatefunc;
			that.render = function() {
				const sx = that.vertical ? 0 : that.frameIndex * that.frameWidth;
				const sy = that.vertical ? that.frameIndex * that.frameHeight : 0;
				that.context.drawImage(
					that.image,
					sx,
					sy,
					that.frameWidth,
					that.frameHeight,
					that.x,
					that.y,
					that.frameWidth,
					that.frameHeight);
			};
			return that;
		},
		createsprites(number, image_name) {
			const spriteImage = new Image();
			spriteImage.addEventListener("error", () => {
				console.warn(`Sprite image unavailable: ${image_name} (view ${this.view})`);
			}, { once: true });
			spriteImage.addEventListener("load", () => {
				const updatefunc = function(ctx) {
					ctx.tickCount += 1;
					ctx.x -= ctx.speed;
					if (ctx.x < -ctx.frameWidth) {
						return false;
					}
					if (ctx.tickCount > ctx.ticksPerFrame) {
						ctx.tickCount = 0;
						if (ctx.frameIndex < ctx.number_of_frames - 1) {
							ctx.frameIndex += 1;
						} else {
							ctx.frameIndex = 0;
						}
					}
					return true;
				};
				for (let i = 0; i < number; i++) {
					this.sprites.push(this.sprite({
						id: i,
						context: this.canvas.getContext("2d"),
						image: spriteImage,
						...this._frameGeometry(spriteImage),
						ticksPerFrame: 8,
						updatefunc,
					}));
				}
			}, { once: true });
			spriteImage.src = `/res/${this.view}/image/${image_name}`;
		},
		creategem() {
			const spriteImage = new Image();
			spriteImage.src = `/res/${this.view}/media/red_jewel`;
			const h = this.canvas.height;
			const w = this.canvas.width;
			const radius = parseInt(w / 3);
			spriteImage.addEventListener("load", () => {
				const updatefunc = function(ctx) {
					if (typeof ctx.counter === "undefined") {
						ctx.counter = 0;
						ctx.x2 = ctx.x;
						ctx.y2 = ctx.y;
					}
					if (ctx.y2 < 0) {
						if (ctx.y < 0) {
							return false;
						}
					}
					ctx.tickCount += 1;
					ctx.counter += 1;
					ctx.y2 -= ctx.speed * 0.75;
					ctx.x = ctx.x2;
					ctx.y = ctx.y2;
					// follow a flat arc
					ctx.x += radius * Math.cos(ctx.counter * 0.02);
					ctx.y += radius * 0.5 * Math.sin(ctx.counter * 0.02);
					if (ctx.tickCount > ctx.ticksPerFrame) {
						ctx.tickCount = 0;
						if (ctx.frameIndex < ctx.number_of_frames - 1) {
							ctx.frameIndex += 1;
						} else {
							ctx.frameIndex = 0;
						}
					}
					return true;
				};
				this.sprites.push(this.sprite({
					id: 1,
					context: this.canvas.getContext("2d"),
					x: parseInt(w / 2),
					y: h,
					image: spriteImage,
					...this._frameGeometry(spriteImage),
					ticksPerFrame: 8,
					updatefunc,
				}));
			}, { once: true });
		},
		do_alert(msg) {
			try {
				// Sprites fire immediately — not gated by the banner queue
				if (msg.type === "FOLLOW") {
					this.createsprites(1, "follow");
				} else if (msg.type === "REDEMPTION") {
					// TODO: a way to make this generic and not hard-coded
					if (msg.tags['reward-title'] === "Chocobos") {
						this.createsprites(15, "chocobo");
					} else if (msg.tags['reward-title'] === "Send Jewels to Gem") {
						this.creategem();
					}
				} else if (["RAID", "HOSTED"].includes(msg.type)) {
					const count = parseInt(msg.tags['msg-param-viewerCount']);
					this.createsprites(count, "raid");
				}

				// Sound path
				let soundPath = null;
				let speech = null;
				if (this.sound) {
					switch (msg.type) {
						case "BITS": {
							const amount = msg.tags["bits"];
							soundPath = `/res/${this.view}/sound/bits?value=${amount}`;
							const re = /^(\w*Cheer\d+\s*|$)+/i;
							speech = msg.orig_message?.match(re) ? "" : (msg.orig_message?.replace(/\w+\d+/, "") || "");
							break;
						}
						case "SUBGIFT":
							soundPath = `/res/${this.view}/sound/sub`;
							break;
						case "SUB":
							soundPath = `/res/${this.view}/sound/sub`;
							speech = `${msg.nickname} just subscribed. ${msg.orig_message}`;
							break;
						case "FOLLOW":
							soundPath = `/res/${this.view}/sound/follow`;
							break;
						case "RAID":
							soundPath = `/res/${this.view}/sound/raid`;
							break;
						case "HOSTED":
							soundPath = `/res/${this.view}/sound/host`;
							break;
						case "REDEMPTION":
							soundPath = `/res/${this.view}/sound/${encodeURIComponent(msg.tags["reward-title"])}`;
							break;
					}
				}

				// Banner / visual alert
				let alertData = null;
				let media = null;
				switch (msg.type) {
					case "FOLLOW":
						media = `/res/${this.view}/media/follow`;
						break;
					case "RAID":
						media = `/res/${this.view}/media/raid`;
						break;
					case "SUB":
						media = `/res/${this.view}/media/sub`;
						break;
					case "BITS": {
						const amount = msg.tags["bits"];
						media = `/res/${this.view}/media/bits?value=${amount}`;
						break;
					}
				}
				if (media) {
					const sysMsg = msg.tags['system-msg'] || '';
					const body = msg.message || '';
					const text = (sysMsg && body) ? `${sysMsg}<br/>${body}` : (sysMsg || body);
					alertData = {
						type: undefined,
						media,
						user: msg.nickname,
						message: text,
						id: msg.id,
					};
				}

				if (soundPath || alertData) {
					this.queue.push({ alertData, soundPath, speech });
				}
			} catch(err) {
				console.warn(err);
			}
		},
	}
};

var banner = {
	template: `
	<transition mode="out-in">
	<div v-show="!done" id="alertbox">
	<video v-if="type=='video'" ref="media" autoplay class="content" :src="media"></video>
	<img v-if="type=='gif'" :src="media" class="content"/>

	<p v-html="message" class="message"></p>
	</div>
	</transition>
	`,
	props: {
		media: String,
		user: String,
		message: String,
		id: String
	},
	data() {
		return {
			done: true,
			type: null,
		};
	},
	created() {
		this._finished = false;
		this._fallbackTimer = null;
	},
	mounted() {
		this.start();
	},
	beforeUnmount() {
		clearTimeout(this._fallbackTimer);
	},
	methods: {
		async start() {
			try {
				const response = await fetch(this.media);
				if (!response.ok) {
					throw new Error(`HTTP ${response.status}`);
				}
				const ct = response.headers.get("content-type") || "";
				this.type = ct.startsWith("image") ? "gif" : "video";
			} catch (err) {
				// No media available — finish immediately so the queue moves on
				console.warn("Alert media unavailable:", this.media, err);
				this.setdone();
				return;
			}
			this.done = false;
			if (this.type === "video") {
				await this.$nextTick();
				const video = this.$refs.media;
				if (!video) {
					this.fallback(7000);
					return;
				}
				video.addEventListener('ended', this.setdone, { once: true });
				video.addEventListener('error', this.setdone, { once: true });
				const played = video.play();
				if (played) {
					played.catch(err => {
						// Autoplay refused or decode failure — show the frame briefly
						console.warn("Alert video playback failed:", err);
						this.fallback(7000);
					});
				}
			} else {
				this.fallback(7000);
			}
		},
		fallback(ms) {
			clearTimeout(this._fallbackTimer);
			this._fallbackTimer = setTimeout(this.setdone, ms);
		},
		setdone() {
			if (this._finished) {
				return;
			}
			this._finished = true;
			clearTimeout(this._fallbackTimer);
			this.done = true;
			this.$emit('finished');
		}
	},
};

export default {
	mediaContent,
	banner,
}
