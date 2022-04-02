
import eventBus from "./eventBus";

Vue.component('obs-handler', {
	template: '<div style="display:none;"></div>',
	props: {
		tts: {
			type: Boolean,
			default: false,
		}
	},
	data: function () {
        return {};
	},
    methods: {
		mounted: function() {
			do_mount();

		},
        do_thing: function (msg) {
		}
    }
});

function do_mount() {

	window.addEventListener('obsSceneChanged', function(event) {
		var t = event.detail.name;
		eventBus.$emit('clear')
	});

	window.addEventListener('obsStreamingStarting', function(event) {
		eventBus.$emit('clear')
	})
}