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
					if (!img.update()) {
						// cull sprites that reach the left edge
						this.sprites.splice(this.sprites.indexOf(img), 1);
						var toRender = this.sprites.slice(0, this.rate);
						// Sort by -y
						toRender.sort((a, b) => a.y - b.y);
					};
					img.render();
				});
			}
		},
		sprite: function (options) {
		
			var that = {},
				frameIndex = 0,
				tickCount = 0,
				ticksPerFrame = options.ticksPerFrame || 0,
				numberOfFrames = options.numberOfFrames || 1;
			
			that.context = options.context;
			that.width = options.width;
			that.height = options.height;
			that.image = options.image;
			if (options.id < this.rate) {
				that.x = options.context.canvas.width + ((options.context.canvas.width / this.rate) * options.id );
			} else {
				that.x = options.context.canvas.width + options.width;
			}
			that.y = (options.context.canvas.height * 0.25) + (Math.random() * (options.context.canvas.height * 0.5));
			that.speed = 1.5 + (Math.random());
			
			that.update = function () {

				tickCount += 1;
				that.x -= that.speed;
				if (that.x < -(that.width / numberOfFrames)) {
					return false;
				}

				if (tickCount > ticksPerFrame) {

					tickCount = 0;
					
					// If the current frame index is in range
					if (frameIndex < numberOfFrames - 1) {	
						// Go to the next frame
						frameIndex += 1;
					} else {
						frameIndex = 0;
					}
				}
				return true
			};
			
			that.render = function () {
			// Draw the animation
			that.context.drawImage(
				that.image,
				frameIndex * that.width / numberOfFrames,
				0,
				that.width / numberOfFrames,
				that.height,
				that.x,
				that.y,
				that.width / numberOfFrames,
				that.height);
			};
			
			return that;
		},
		createsprites: function (number, image_name) {
			// Load sprite sheet
			let spriteImage = new Image()
			spriteImage.src = `/res/${this.view}/image/${image_name}`;
			spriteImage.addEventListener("load", (e) => {
				for (let i = 0; i < number; i++) {
					// Create sprite
					var newsprite = this.sprite({
						id: i,
						context: this.canvas.getContext("2d"),
						width: spriteImage.width,
						height: spriteImage.height,
						image: spriteImage,
						numberOfFrames: parseInt(spriteImage.width / spriteImage.height),
						ticksPerFrame: 8
					});
					this.sprites.push(newsprite)
				}
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
