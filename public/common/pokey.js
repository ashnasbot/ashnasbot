/**
 * Pokey - persistent wiggly cactus character from Super Mario World.
 *
 * Greets each unique chatter once with a speech bubble above the head.
 * Greetings are queued and displayed one at a time; once a name has been
 * greeted it is remembered for the lifetime of the component.
 *
 * Each body segment's animation-delay is computed *once* at the moment the
 * segment is added, using the elapsed time since mount to stay phase-locked
 * with the head.  The delay is stored in a reactive array so Vue never
 * recomputes it for existing segments when the list grows or shrinks.
 */
const pokey = {
    template: `
    <div class="pokey-wrapper" v-show="bodyDelays.length > 0">
        <div class="pokey">
            <transition name="pokey-greet">
                <div v-if="greetVisible" class="bubble shadow grow right mini pokey-bubble">
                    {{ currentGreet }}
                </div>
            </transition>
            <img class="pokey-part"
                 src="/static/images/pokeyhead.png"
                 style="animation-delay: 0s">
            <img v-for="(delay, i) in bodyDelays" :key="i"
                 class="pokey-part"
                 src="/static/images/pokeybod.png"
                 :style="{ 'animation-delay': delay }">
        </div>
    </div>
    `,

    data() {
        return {
            bodyDelays: [],
            currentGreet: null,
            greetVisible: false,
        };
    },

    mounted() {
        this._startTime = performance.now();
        this._seenUsers = new Set();
        this._greetQueue = [];
        this._greeting = false;
        this._greetTimers = [];
        // Start with one body segment, in phase with the just-started head.
        this.bodyDelays.push(this._computeDelay(1));
    },

    beforeUnmount() {
        this._greetTimers.forEach(clearTimeout);
    },

    methods: {
        /**
         * Return the CSS animation-delay string that places segment `index`
         * exactly one step behind the segment above it, relative to the head's
         * current position in the cycle.
         *
         * index 0 = head (always delay 0, hardcoded in template)
         * index 1 = first body segment (1 step behind head)
         * index N = N steps behind head
         */
        _computeDelay(index) {
            const step = 0.15;           // seconds per animation frame (one quarter of 0.6s cycle)
            const period = step * 4;     // full cycle duration = 0.6s
            const elapsed = (performance.now() - this._startTime) / 1000;
            const headPhase = elapsed % period;
            // Trailing by index steps = leading by (period - index*step).
            // Expressed as a negative delay so the animation appears to have
            // already been running for `target` seconds when inserted.
            const target = ((headPhase - index * step) % period + period) % period;
            return `-${target.toFixed(4)}s`;
        },

        addSegment() {
            this.bodyDelays.push(this._computeDelay(this.bodyDelays.length + 1));
        },

        removeSegment() {
            if (this.bodyDelays.length > 0) this.bodyDelays.pop();
        },

        /**
         * Greet a chatter by name. Each name is greeted at most once per
         * session; subsequent calls with the same name are ignored.
         */
        greet(name) {
            if (this._seenUsers.has(name.toLowerCase())) return;
            this._seenUsers.add(name.toLowerCase());
            const greetings = ['Hi', 'Hey', 'Hello', 'Ahoy', 'Howdy', 'Sup', 'Yo'];
            const word = greetings[Math.floor(Math.random() * greetings.length)];
            this._greetQueue.push(`${word}, ${name}!`);
            if (!this._greeting) {
                this._showNext();
            }
        },

        say(text) {
            this._greetQueue.push(text);
            if (!this._greeting) {
                this._showNext();
            }
        },

        ignore(name) {
            this._seenUsers.add(name.toLowerCase());
        },

        _showNext() {
            if (this._greetQueue.length === 0) {
                this.currentGreet = null;
                this._greeting = false;
                return;
            }
            this._greeting = true;
            this.currentGreet = this._greetQueue.shift();
            this.greetVisible = true;
            this._greetTimers = [setTimeout(() => {
                this.greetVisible = false;
                // Wait for the leave transition to finish before showing next.
                this._greetTimers.push(setTimeout(() => { this._showNext(); }, 350));
            }, 3000)];
        },
    },
};

export default pokey;
