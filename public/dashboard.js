Vue.component('events-display', {
    data: function() {
      return {
        events: [],
        categoryList: ['SUB', 'FOLLOW', 'RAID', 'SUBGIFT', 'BITS'],
        filters: ['SUB', 'FOLLOW', 'RAID', 'SUBGIFT', 'BITS']
      }
    },
    computed: {
      filtered: function () {
        return this.events.filter(function (item) {
          return this.filters.includes(item.type);
        }, this);
      }
    },
    created: function() {
      this.get_events();
      window.setInterval(this.get_events, 5000)
    },
    methods: {
      get_events: function() {
        fetch('/events')
        .then(res => res.json())
        .then(res => {
          this.events = res;
        });
      },
      replay: function(event_id) {
        const event = this.events.find(element => element.id == event_id);
        fetch('/replay_event', {
          method: 'POST',
          body: JSON.stringify(event)
        }).then( resp => {
          console.log(resp);
        })
      },
      renderTs: function(ts) {
        var date = new Date(parseInt(ts));
        if(isNaN(date.getTime())) {
          return "";
        }
        return date.toLocaleTimeString(navigator.language, {
          hour: '2-digit',
          minute:'2-digit'
        });
      }
    },
    template: `
    <div>
    <div v-for="cat in categoryList" class="uk-inline uk-padding-small">
      <input type="checkbox" :id="cat" :value="cat" v-model="filters" class="uk-checkbox">
      <label :for="cat">{{cat}}</label>
    </div>
    <table class="uk-table uk-table-striped uk-table-small uk-overflow-auto">
      <caption></caption>
      <thead>
          <tr>
              <th>Time</th>
              <th>Event</th>
              <th>Who</th>
              <th>Message</th>
              <th>Actions</th>
          </tr>
      </thead>
      <tbody>
        <tr v-for="event in filtered" v-bind:key="event.id" v-bind:id="event.id">
          <td>{{renderTs(event.tags['tmi-sent-ts'])}}</td>
          <td>{{event.type}}</td>
          <td v-if="event.tags">{{event.tags['display-name']}}</td> <td v-else>{{event.nickname}}</td>
          <td v-if="event.tags">{{event.tags['system-msg']}}</td> <td v-else>{{event.message}}</td>
          <td><button title="Replay" v-on:click="replay(event.id)" class="uk-button uk-button-primary uk-button-small">↺</button></td>
        </tr>
      </tbody>
  </table>
  </div>`
  })

Vue.component('event-create', {
    data: function() {
      return {
        options: {
          channel: {
            type: 'text',
            value: '',
            forEvents: ['SUB', 'FOLLOW', 'RAID', 'SUBGIFT', 'BITS'],
          },
          who: {
            type: 'text',
            value: '',
            forEvents: ['SUB', 'FOLLOW', 'RAID', 'SUBGIFT', 'BITS'],
          },
          tier: {
            type: 'number',
            value: '1',
            forEvents: ['SUB'],
          },
          months: {
            type: 'number',
            value: '1',
            forEvents: ['SUB'],
          },
          message: {
            type: 'text',
            value: '',
            forEvents: ['SUB'],
          },
          value: {
            type: 'number',
            value: '100',
            forEvents: ['BITS'],
          },
          viewers: {
            type: 'number',
            value: '50',
            forEvents: ['RAID'],
          },
        },
        types: ['SUB', 'FOLLOW', 'RAID', 'SUBGIFT', 'BITS'],
        selectedType: 'FOLLOW'
      }
    },
    computed: {
      filteredOptions: function () {
        return Object.keys(this.options)
          .filter(key => this.options[key].forEvents.includes(this.selectedType))
          .reduce((obj, key) => {
            obj[key] = this.options[key];
            return obj;
          }, {});
      }
    },
    methods: {
      send: function(evt) {
        const event = this[this.selectedType]();
        fetch('/replay_event', {
          method: 'POST',
          body: JSON.stringify(event)
        }).then( resp => {
          console.log(resp);
        })
      },
      FOLLOW: function() {
        let ts = Date.now()
        return {
          type: "FOLLOW",
          nickname: `${this.options.who.value}`,
          channel: `${this.options.channel.value}`,
          audio: "/static/audio/Mana_got_item.wav",
          id: uuid4(),
          tags: {
              "system-msg": `${this.options.who.value} followed the channel`,
              "tmi-sent-ts": `${ts}`,
              "display-name": `${this.options.who.value}`
          }
        }
      },
      SUB: function() {
        let ts = Date.now()

        return {
          type: "SUB",
          nickname: `${this.options.who.value}`,
          message: `${this.options.message.value}`,
          channel: `${this.options.channel.value}`,
          id: "xxx",
          tags: {
            "display-name": `${this.options.who.value}`,
            "id": uuid4(),
            "system-msg": `${this.options.who.value} subscribed at Tier ${this.options.tier.value}. They've subscribed for ${this.options.months.value} months!`,
            "tmi-sent-ts": `${ts}`,
          },
          extra: [
            "quoted"
          ]
        }
      },
      RAID: function() {
        let ts = Date.now()
        return {
          type: "RAID",
          nickname: `${this.options.who.value}`,
          channel: `${this.options.channel.value}`,
          message: "",
          id: uuid4(),
          tags: {
            "color": "#126B00",
            "display-name": `${this.options.who.value}`,
            "msg-id": "raid",
            "msg-param-viewerCount": `${this.options.viewers.value}`,
            "system-msg": `${this.options.who.value} is raiding with a party of ${this.options.viewers.value}`,
            "tmi-sent-ts": `${ts}`,
          },
          extra: [
            "quoted"
          ]
        }
      },
      BITS: function() {
        let ts = Date.now()

        return {
          type: "BITS",
          nickname: `${this.options.who.value}`,
          value: `${this.options.value.value}`,
          channel: `${this.options.channel.value}`,
          message: `Cheer${this.options.value.value}`,
          orig_message: `Cheer${this.options.value.value}`,
          id: "xxx",
          tags: {
            "display-name": `${this.options.who.value}`,
            "id": uuid4(),
            "bits": `${this.options.value.value}`,
          },
          extra: [
            "quoted"
          ]
        }
      },
    },
    template: `
    <div class="uk-card uk-card-body">
      <form
        @submit.prevent
        @submit=send
        class="uk-form-horizontal">

        <div class="uk-margin-small">
          <label for="select" class="uk-form-label">Event Type</label>
          <div class="uk-form-controls uk-form-width-medium">
            <select id="select" v-model="selectedType" class="uk-select">
              <option v-for="type in types">{{type}}</option>
            </select>
          </div>
        </div>
        
        <div v-for="(opt, name) in filteredOptions" class="uk-margin-small">
          <label :for="name" class="uk-form-label">{{name}}</label>
          <div class="uk-form-controls">
            <input v-bind:type="opt.type" :id="name" :value="opt.value" v-model="opt.value" v-bind:class="'uk-' + opt.type">
          </div>
        </div>
        <input type="submit" value="Submit" class="uk-button uk-button-default uk-form-controls">
      </form>
    </div>
    `
  }
);

const app = new Vue({
    el:'#app',
})

function uuid4() {
  return ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
    (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)
  );
}