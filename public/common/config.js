Vue.component('config-menu', {
    mounted: function () {
        if (localStorage.config) {
            config = JSON.parse(localStorage.config);
            this.commands = config.commands;
            this.images = config.images;
            this.alert = config.alert;
            this.sound = config.sound;
            this.tts = config.tts;
            this.hosts = config.hosts;
            this.menu = config.menu;
            this.pubsub = config.pubsub;
        }
    },
    methods: {
        handleInput () {
            data = Object.fromEntries(Object.entries(this._data));
            this.$emit("cfg-update", data);
        }
    },
    data: function () {
      return {
        commands: true,
        images: true,
        alert: true,
        sound: true,
        tts: false,
        hosts: false,
        menu: true,
        pubsub: false
      }
    },
    watch: {
        commands(n) { this.handleInput(); },
        images(n) { this.handleInput(); },
        alert(n) { this.handleInput(); },
        sound(n) { this.handleInput(); },
        tts(n) { this.handleInput(); },
        hosts(n) { this.handleInput(); },
        menu(n) { this.handleInput(); },
        pubsub(n) { this.handleInput(); },
    },
    template: `
    <div class="popout">
    <div class="form">
    <span>Press 'Submit' to set config </span>
    <label>Allow commands<input name="commands" type="checkbox" v-model="commands"> </label>
    <label>Pull Avatars<input name="images" type="checkbox" v-model="images"></label>
    <label>Show Chat Notifications<input name="alert" type="checkbox" v-model="alert"></label>
    <label>Sounds<input name="sound" type="checkbox" v-model="sound"></label>
    <label>Text to speech<input name="tts" type="checkbox" v-model="tts"></label>
    <label>Follow Hosts<input name="hosts" type="checkbox" v-model="hosts"></label>
    <label>Show menu on load<input name="menu" type="checkbox" v-model="menu"></label>
    <label>Show alerts from PubSub (requires auth)<input name="menu" type="checkbox" v-model="pubsub"></label>
    </div>
    </div>
    `
  })
