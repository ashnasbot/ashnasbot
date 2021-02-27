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
    <fieldset>
    <legend>Press 'Submit' to set config </legend>

    <input type="checkbox" id="menuChk1" v-model="commands">
    <label for="menuChk1" name="commands">Allow Commands</label>

    <input type="checkbox" id="menuChk2" v-model="images">
    <label for="menuChk2" name="images">Pull Avatars</label>

    <input type="checkbox" id="menuChk3" v-model="alert" >
    <label for="menuChk3" name="alert">Show chat notifications</label>

    <input type="checkbox" id="menuChk4" v-model="sound" >
    <label for="menuChk4" name="sound">Sounds</label>

    <input type="checkbox" id="menuChk5" v-model="tts" >
    <label for="menuChk5" name="tts">Text to speech</label>

    <input type="checkbox" id="menuChk6" v-model="hosts" >
    <label for="menuChk6" name="hosts">Follow hosts</label>

    <input type="checkbox" id="menuChk7" v-model="menu" >
    <label for="menuChk7" name="menu">Show menu on load</label>

    <input type="checkbox" id="menuChk8" v-model="pubsub" >
    <label for="menuChk8" name="pubsub">Show alerts from PubSub (requires auth)</label>
    </fieldset>

    </div>
    </div>
    `
  })
