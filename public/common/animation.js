Vue.component('chase', {
	template: '<canvas ref="screen" width=640 height=480></canvas>',
	props: {
		rate: {  // Number of chocos on screen at once
			type: Number,
			default: 32,
		}
	},
	data: function() {
        var urlChunks = location.pathname.split('/');
		return {
			canvas: null,
			sprites: [],
			view: urlChunks[urlChunks.length - 2], audio: null
		}
	},
    mounted: function () {
		// Get canvas
		this.canvas = this.$refs.screen
		this.canvas.width = window.innerWidth;
		this.canvas.height = window.innerHeight;

		this.mainLoop()
		
    },
    methods: {
		mainLoop: function() {
		
			window.requestAnimationFrame(this.mainLoop);

			if (this.sprites.length > 0) {
				const context = this.canvas.getContext('2d');
				context.clearRect(0, 0, this.canvas.width, this.canvas.height);
				if (!toRender) {
					var toRender = this.sprites.slice(0, this.rate);
				}

				toRender.forEach(img => {
					if (!img.update(img)) {
						// cull sprites that die (reach the edge)
						this.sprites.splice(this.sprites.indexOf(img), 1);
						var toRender = this.sprites.slice(0, this.rate);
						// Sort by -y
						toRender.sort((a, b) => a.y - b.y);
					};
					img.render();
				});
				// Cleanup if all are gone
				if (this.sprites.length == 0) {
					context.clearRect(0, 0, this.canvas.width, this.canvas.height);
				}
			}
		},
		sprite: function (options) {
		
			var that = {}

			that.frameIndex = 0,
			that.tickCount = 0,
			that.ticksPerFrame = options.ticksPerFrame || 0,
			that.number_of_frames = options.numberOfFrames || 1;
			
			that.context = options.context;
			that.width = options.width;
			that.height = options.height;
			that.image = options.image;

			/* Optionals */
			that.x = options.x;
			that.y = options.y;
			that.speed = options.speed;
			if (typeof that.x == undefined) {
				if (options.id < this.rate) {
					that.x = options.context.canvas.width + ((options.context.canvas.width / this.rate) * options.id );
				} else {
					that.x = options.context.canvas.width + options.width;
				}
			}
			if (typeof that.y == 'undefined') {
				that.y = (options.context.canvas.height * 0.25) + (Math.random() * (options.context.canvas.height * 0.5));
			}
			if (typeof that.speed == 'undefined') {
				that.speed = 1.5 + (Math.random());
			}

			/* methods */
			that.update = options.updatefunc;
			that.render = function () {
			// Draw the animation
			that.context.drawImage(
				that.image,
				that.frameIndex * that.width / that.number_of_frames,
				0,
				that.width / that.number_of_frames,
				that.height,
				that.x,
				that.y,
				that.width / that.number_of_frames,
				that.height);
			};
			
			return that;
		},
		createsprites: function (number, image_name) {
			// Load sprite sheet
			let spriteImage = new Image()
			spriteImage.src = `/res/${this.view}/image/${image_name}`;
			spriteImage.addEventListener("load", (e) => {
				updatefunc = function (ctx) {
					ctx.tickCount += 1;
					ctx.x -= ctx.speed;
					if (ctx.x < -(ctx.width / ctx.number_of_frames)) {
						return false;
					}

					if (ctx.tickCount > ctx.ticksPerFrame) {

						ctx.tickCount = 0;
						
						// If the current frame index is in range
						if (ctx.frameIndex < ctx.number_of_frames - 1) {	
							// Go to the next frame
							ctx.frameIndex += 1;
						} else {
							ctx.frameIndex = 0;
						}
					}
					return true
				};
				for (let i = 0; i < number; i++) {
					// Create sprite
					var newsprite = this.sprite({
						id: i,
						context: this.canvas.getContext("2d"),
						width: spriteImage.width,
						height: spriteImage.height,
						image: spriteImage,
						numberOfFrames: parseInt(spriteImage.width / spriteImage.height),
						ticksPerFrame: 8,
						updatefunc: updatefunc
					});
					this.sprites.push(newsprite)
				}
			});
		},
		creategem: function () {
			// Load sprite sheet
			let spriteImage = new Image()
			spriteImage.src = `/res/${this.view}/image/red_jewel`;
			h = this.canvas.height;
			w = this.canvas.width;
			radius = parseInt(w/3);
			rads_per_second = 0.5
			spriteImage.addEventListener("load", (e) => {
				updatefunc = function (ctx) {
					if (typeof ctx.counter == "undefined") {
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
						
						// If the current frame index is in range
						if (ctx.frameIndex < ctx.number_of_frames - 1) {	
							// Go to the next frame
							ctx.frameIndex += 1;
						} else {
							ctx.frameIndex = 0;
						}
					}
					return true
				};
				// Create sprite
				var newsprite = this.sprite({
					id: 1,
					context: this.canvas.getContext("2d"),
					width: spriteImage.width,
					height: spriteImage.height,
					x: parseInt(w / 2),
					y: h,
					image: spriteImage,
					numberOfFrames: parseInt(spriteImage.width / spriteImage.height),
					ticksPerFrame: 8,
					updatefunc: updatefunc
				});
				this.sprites.push(newsprite)
			});
		},
        do_alert(msg) {
			try {
				// TODO: Handle event while sprites still running
				if (msg.type == "FOLLOW") {
					this.createsprites(1, "follow");
				}
				else if (msg.type == "REDEMPTION")
				{
					// TODO: a way to make this generic and not hard-coded
					if (msg.tags['reward-title'] == "Chocobos")
					{
						this.createsprites(15, "chocobo");
					}
					else if (msg.tags['reward-title'] == "Send Jewels to Gem") {
						this.creategem();
					}
				} else if (["RAID", "HOSTED"].includes(msg.type)){
				    let count = parseInt(msg.tags['msg-param-viewerCount']);
					this.createsprites(count, "raid");
				}
			}
			catch(err) {
				console.warn(err);
			}
		}
    }
});
