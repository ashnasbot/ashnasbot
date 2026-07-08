export default {
    mounted: function () {
        if (localStorage.config) {
            let config = JSON.parse(localStorage.config);
            this.commands = config.commands;
            this.images = config.images;
            this.alert = config.alert;
            this.sound = config.sound;
            this.tts = config.tts;
            this.menu = config.menu;
            this.pubsub = config.pubsub;
            this.chatbot = config.chatbot;
        }
        const params = new URLSearchParams(window.location.search);
        this.currentChannel = params.get('channel') || '';
        fetch(`/api/config?channel=${encodeURIComponent(this.currentChannel)}`)
            .then(r => r.json())
            .then(cfg => {
                this.botConfigured = cfg.bot_configured || false;
                this.botUsername = cfg.username || '';
                this.channelAuthed = cfg.channel_configured || false;
                this.channelTokenFor = cfg.channel_token_for || '';
                if (this.botConfigured) {
                    this._checkBotToken();
                }
            })
            .catch(() => {});
    },
    methods: {
        handleInput () {
            let data = Object.fromEntries(Object.entries(this.$data));
            this.$emit("cfg-update", data);
        },
        _checkBotToken() {
            fetch('/api/bot_status')
                .then(r => r.json())
                .then(s => { this.botTokenValid = s.valid; })
                .catch(() => {});
        },
        toggleOpen() { this.open = !this.open; },
        setBotToken() {
            const payload = this.botTokenInput.trim()
                ? { token: this.botTokenInput.trim() }
                : {};
            fetch('/api/set_bot_token', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            })
                .then(r => r.json())
                .then(d => {
                    if (d.ok) {
                        this.botConfigured = true;
                        this.botUsername = d.login;
                        this.botTokenValid = true;
                        this.botTokenInput = '';
                        this.botTokenError = '';
                    } else {
                        this.botTokenError = d.error || 'Failed';
                    }
                })
                .catch(() => { this.botTokenError = 'Request failed'; });
        },
    },
    data: function () {
      return {
        open: false,
        channelAuthed: false,
        channelTokenFor: '',
        currentChannel: '',
        commands: true,
        images: true,
        alert: true,
        sound: true,
        tts: false,
        menu: true,
        pubsub: false,
        chatbot: false,
        botConfigured: false,
        botUsername: '',
        botTokenValid: null,
        botTokenInput: '',
        locationSearch: window.location.search,
        botTokenError: '',
      }
    },
    watch: {
        commands() { this.handleInput(); },
        images() { this.handleInput(); },
        alert() { this.handleInput(); },
        sound() { this.handleInput(); },
        tts() { this.handleInput(); },
        menu() { this.handleInput(); },
        pubsub() { this.handleInput(); },
        chatbot() { this.handleInput(); },
    },
    template: `
    <div class="popout">
    <button class="hamburger" @click="toggleOpen" :aria-expanded="open">☰</button>
    <div class="form" v-show="open">
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
    <label for="menuChk7" name="pubsub">Show alerts from EventSub (requires auth)</label>

    <input type="checkbox" id="menuChk8" v-model="menu" >
    <label for="menuChk8" name="menu">Show menu on load</label>

    <input type="checkbox" id="menuChkChanAuth" :checked="channelAuthed" disabled>
    <label for="menuChkChanAuth">Channel auth <a :href="'/user_auth' + locationSearch">{{ channelAuthed ? 're-auth' : 'authenticate' }}</a><span v-if="channelTokenFor && !channelAuthed" style="color:orange;"> (token is for '{{ channelTokenFor }}')</span></label>

    <input type="checkbox" id="menuChkBotAuth" :checked="botConfigured" disabled>
    <label for="menuChkBotAuth">Bot{{ botConfigured ? ': ' + botUsername : '' }}<span v-if="botConfigured && botTokenValid === false" style="color: orange;"> (token expired)</span></label>
    <div style="grid-column:1/-1;display:flex;gap:4px;align-items:center;margin-top:4px;">
      <input type="text" v-model="botTokenInput" placeholder="Paste token, or leave blank for config oauth" style="flex:1;min-width:0;font-size:0.8em;">
      <button @click="setBotToken" style="white-space:nowrap;">Use Token</button>
      <span v-if="botTokenError" style="color:orange;font-size:0.8em;">{{ botTokenError }}</span>
    </div>

    </fieldset>

    </div>
    </div>
    `
};
