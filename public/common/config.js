Vue.component('config-menu', {
    mounted: function () {
        if (localStorage.config) {
            config = JSON.parse(localStorage.config);
            this.commands = config.commands;
            this.images = config.images;
            this.alert = config.alert;
            this.sound = config.sound;
            this.tts = config.tts;
            this.menu = config.menu;
            this.pubsub = config.pubsub;
            this.chatbot = config.chatbot;
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
        status: "",
        commands: true,
        images: true,
        alert: true,
        sound: true,
        tts: false,
        menu: true,
        pubsub: false,
        chatbot: false
      }
    },
    watch: {
        status(v) {
            console.log(v);
        },
        commands(n) { this.handleInput(); },
        images(n) { this.handleInput(); },
        alert(n) { this.handleInput(); },
        sound(n) { this.handleInput(); },
        tts(n) { this.handleInput(); },
        menu(n) { this.handleInput(); },
        pubsub(n) { this.handleInput(); },
        chatbot(n) { this.handleInput(); },
    },
    template: `
    <div class="popout">
    <label for="menuStatus">Status</label>
    <input id="menuStatus" v-model="status" disabled>
    <div class="form">
    <fieldset>
    <legend>Press 'Submit' to set config </legend>

    <input type="checkbox" id="menuChk1" v-model="commands">
    <label for="menuChk1" name="commands">Allow Commands</label>

    <input type="checkbox" id="menuChk2" v-model="chatbot" >
    <label for="menuChk2" name="Chatbot">Respond in chat</label>

    <input type="checkbox" id="menuChk3" v-model="images">
    <label for="menuChk3" name="images">Pull Avatars</label>

    <input type="checkbox" id="menuChk4" v-model="alert" >
    <label for="menuChk4" name="alert">Show chat notifications</label>

    <input type="checkbox" id="menuChk5" v-model="sound" >
    <label for="menuChk5" name="sound">Sounds</label>

    <input type="checkbox" id="menuChk6" v-model="tts" >
    <label for="menuChk6" name="tts">Text to speech</label>

    <input type="checkbox" id="menuChk7" v-model="pubsub" >
    <label for="menuChk7" name="pubsub">Show alerts from PubSub (requires auth)</label>

    <input type="checkbox" id="menuChk8" v-model="menu" >
    <label for="menuChk8" name="menu">Show menu on load</label>

    </fieldset>

    </div>
    </div>
    `
  })
