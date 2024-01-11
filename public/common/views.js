export default {
    data: function() {
        let urlChunks = location.pathname.split('/');
        let current = urlChunks[urlChunks.length - 2];
        return {
            views: [],
            search: window.location.search,
            current: current
        }
    },
    methods: {
        getdata: async function () {
            const response = await fetch('/api/views');
            if (!response.ok) {
                throw new Error('Failed to get views');
            }
            return { views: await response.json()};
        }
    },
    mounted: function() {
        this.getdata().then((data) => {
            this.views = data.views
        });
        document.title = this.current + " - Ashnasbot"
    },
    template: `<select onchange="location.href=this.value">
        <option v-for="view in views"
                v-bind:value="'/views/' + view + '/chat.html' + search"
                :selected="view.toLowerCase() == current.toLowerCase()">{{view}}</option>
    </select>`
}