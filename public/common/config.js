Vue.component('config-menu', {
    mounted: function () {
        if (localStorage.config) {
            config = JSON.parse(localStorage.config);
            this.commands = config.commands;
            this.follows = config.follows;
            this.images = config.images;
            this.alerts = config.alerts;
            this.sound = config.sound;
            this.hosts = config.hosts;
            this.menu = config.menu;
            this.channel_points = config.channel_points;
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
        follows: false,
        images: true,
        alerts: true,
        sound: true,
        hosts: false,
        menu: true,
        channel_points: false
      }
    },
    watch: {
        commands(n) { this.handleInput(); },
        follows(n) { this.handleInput(); },
        images(n) { this.handleInput(); },
        alerts(n) { this.handleInput(); },
        sound(n) { this.handleInput(); },
        hosts(n) { this.handleInput(); },
        menu(n) { this.handleInput(); },
        channel_points(n) { this.handleInput(); },
    },
    template: `
    <div class="popout">
    <div class="form">
    <span>Press 'Submit' to set config </span>
    <label>Allow commands<input name="commands" type="checkbox" v-model="commands"> </label>
    <!--<label>Show follows<input name="follows" type="checkbox" v-model="follows"></label>-->
    <label>Pull Avatars<input name="images" type="checkbox" v-model="images"></label>
    <label>Show Chat Notifications<input name="alerts" type="checkbox" v-model="alerts"></label>
    <label>Sounds<input name="sound" type="checkbox" v-model="sound"></label>
    <label>Follow Hosts<input name="hosts" type="checkbox" v-model="hosts"></label>
    <label>Show menu on load<input name="menu" type="checkbox" v-model="menu"></label>
    <label>Show Channel point redemptions (requires auth)<input name="menu" type="checkbox" v-model="channel_points"></label>
    </div>
    </div>
    `
  })
