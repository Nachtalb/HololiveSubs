Vue.component('member-card', {
  props: ['member'],
  template: `
        <li v-bind:class="['member', member.twitter, member.retired ? 'retired' : '', isLive ? 'live' : (member.video ? 'scheduled' : '')]"
            v-bind:style="liStyle">
          <div class="actions">
            <span @click="toggleFavourite" class="action action-icon action-heart-full" v-if="isFavourite"></span>
            <span @click="toggleFavourite" class="action action-icon action-heart action-hidden" v-else></span>
            <a v-bind:href="'webcal://' + calendarLink"
               target="_blank"
               title="Add live streams to your calendar"
               class="action action-icon action-calendar action-hidden">
            </a>
          </div>
          <div class="badges">
            <a v-if="member.video"
               v-bind:href="mainLink"
               v-bind:title="member.video.title"
               target="_blank"
               ref="live">
              <span class="badge badge-icon badge-live" v-if="isLive">LIVE</span>
              <span class="badge badge-icon badge-scheduled" v-else>{{ scheduledTitle }}</span>
              <a class="thumbnail" v-bind:href="mainLink" target="_blank" ref="thumbnail">
                <span class="thumbnail-title">{{ member.video.title }}</span>
                <img v-bind:src="member.video.thumbnail">
              </a>
            </a>
            <span class="badge badge-retired" v-if="member.retired">RETIRED</span>
          </div>
          <a v-bind:href="mainLink"
             v-bind:title="member.name"
             target="_blank">
            <div class="profile-image"><img v-bind:src="member.image" alt="member.name"></div>
            <span class="name" v-bind:style="nameStyle">{{ member.name }}</span>
          </a>
          <div class="buttons">
            <a class="ytFollowersCount followersCount"
               v-bind:href="'https://www.youtube.com/channel/' + member.youtube"
               v-bind:title="member.youtube_subs + ' subscribers on YouTube'"
               v-if="member.youtube_subs">
              <span>{{ nFormatter(member.youtube_subs, 2) }}</span> YouTube
            </a>
            <a class="bFollowersCount followersCount"
               v-bind:href="'https://space.bilibili.com/' + member.bilibili"
               v-bind:title="member.bilibili_subs + ' subscribers on Bilibili'"
               v-if="member.bilibili_subs && app.settings.bilibili.value">
              <span>{{ nFormatter(member.bilibili_subs, 2) }}</span> Bilibili
            </a>
            <a class="tFollowersCount followersCount"
               v-bind:title="member.twitter_subs + ' subscribers on Twitter'"
               v-bind:href="'https://twitter.com/' + member.twitter">
              <span>{{ nFormatter(member.twitter_subs, 2) }}</span> Twitter
            </a>
          </div>
        </li>`,

  mounted() {
    if (this.$refs.live) {
      tippy(this.$refs.live, {
        allowHTML: true,
        interactive: true,
        appendTo: () => document.body,
        content: this.$refs.thumbnail,
        maxWidth: 'none',
      });
    }
  },

  computed: {
    isFavourite() {
      return app.favourites.includes(this.member.twitter)
    },

    isLive: function () {
      return this.member.video && (this.member.video.start === 0 || this.currentTimestamp() > this.member.video.start)
    },

    scheduledTitle: function () {
      if (this.member.video) {
        const date = new Date(this.member.video.start * 1000)
        return "Live " + moment(date).fromNow()
      }
    },

    calendarLink: function () {
      return window.location.host + "/events/" + this.member.twitter + ".ics?noCache"
    },

    mainLink: function () {
      if (this.member.youtube_subs) {
        if (this.member.video) return "https://youtube.com/watch?v=" + this.member.video.id
        else "https://youtube.com/channel/" + this.member.youtube
      } else if (this.member.twitter_subs) {
        return 'https://twitter.com/' + this.member.twitter
      } else if (this.member.bilibili_subs) {
        return 'https://space.bilibili.com/' + member.bilibili
      } else {
        return '#'
      }
    },

    liStyle: function () {
      let style = {backgroundImage: `linear-gradient(180deg, ${this.member.bg} 0%, ${this.colourShade(-.9, this.member.bg)} 100%)`}
      if (this.member.background_image && !app.settings.simpleBackgrounds.value) {
        style.backgroundImage = `url("${this.member.background_image}"), ${style.backgroundImage}`
      }
      return style
    },

    nameStyle: function () {
      if (this.member.background_image && !app.settings.simpleBackgrounds.value) {
        return {color: '#222', 'font-weight': 'bold'}
      } else {
        return {color: this.member.fg, 'font-weight': 'normal'}
      }
    }
  },

  methods: {
    toggleFavourite() {
      let index = app.favourites.indexOf(this.member.twitter)
      if (index !== -1) app.favourites.splice(index, 1)
      else app.favourites.push(this.member.twitter)
    },

    currentTimestamp() {
      return (new Date()).getTime() / 1000
    },

    // https://stackoverflow.com/a/13542669/5699307
    // Takes a 6 char hex, shades it and returns a rgb(...) value
    colourShade(p, c) {
      var m = Math.round, c = parseInt(c.slice(1), 16), r = c >> 16, g = c >> 8 & 255, b = c & 255, P = p < 0, t = P ? 0 : p * 255 ** 2, P = P ? 1 + p : 1 - p;
      return "rgb" + "(" + m((P * r ** 2 + t) ** 0.5) + "," + m((P * g ** 2 + t) ** 0.5) + "," + m((P * b ** 2 + t) ** 0.5) + ")";
    },

    nFormatter(num, digits) {
      if (num === undefined) return;
      var si = [
        {value: 1, symbol: ''},
        {value: 1E3, symbol: 'k'},
        {value: 1E6, symbol: 'M'},
        {value: 1E9, symbol: 'G'},
        {value: 1E12, symbol: 'T'},
        {value: 1E15, symbol: 'P'},
        {value: 1E18, symbol: 'E'}
      ];
      var i, rx = /\.0+$|(\.[0-9]*[1-9])0+$/;
      for (i = si.length - 1; i > 0; i--) {
        if (num >= si[i].value) {
          break;
        }
      }
      return (num / si[i].value).toFixed(digits).replace(rx, '$1') + si[i].symbol;
    },
  },
});

Vue.component('member-group', {
  props: ['id', 'group'],
  template: `
        <section v-bind:id="id" :style="{order: group.order}">
          <h2 v-if="group.show_title">{{ group.name }}</h2>

          <ul>
            <member-card
              v-for="member in filteredMembers"
              v-bind:member="member"
              v-bind:key="member.id"
            ></member-card>
          </ul>
        </section>`,

  computed: {
    filteredMembers() {
      let members = []

      for (let member of this.group.members) {
        if (
          (!app.settings.retired.value && member.retired) ||
          (app.settings.onlyLive.value && !member.video) ||
          (app.settings.onlyFavourites.value && !app.favourites.includes(member.twitter))
        ) {
          continue
        }
        members.push(member)

      }

      if (app.settings.sortLive.value && !app.settings.sortName.value) {
        members.sort((a, b) => {
          if (a.video && b.video) return a.video.start - b.video.start
          else if (a.video) return -1
          else if (b.video) return 1
          return 0
        })
      }

      if (app.settings.sortName.value) {
        members.sort((a,b) => {
          if (a.name > b.name) return 1
          else if (a.name < b.name) return -1
          return 0
        })
      }

      if (app.settings.sortFavourites.value) {
        members.sort((a, b) => {
          if (app.favourites.includes(a.twitter) && app.favourites.includes(b.twitter)) return 0
          else if (app.favourites.includes(a.twitter)) return -1
          return 1
        })
      }
      return members
    },
  },
});

var app = new Vue({
  el: '#app',
  data: {
    groups: {},
    favourites: [],
    settings: {
      simpleBackgrounds: {
        value: false,
        label: 'Show simple backgrounds',
      },
      retired: {
        value: true,
        label: 'Show retired',
      },
      bilibili: {
        value: false,
        label: 'Show Bilibili',
      },
      onlyLive: {
        value: false,
        label: 'Only show currently live',
      },
      sortLive: {
        value: false,
        label: 'Sort by live status',
      },
      onlyFavourites: {
        value: false,
        label: "Only show favourites"
      },
      sortFavourites: {
        value: true,
        label: "Sort favourites first"
      },
      sortName: {
        value: false,
        label: "Sort by name"
      }
    }
  },

  mounted() {
    this.loadSettings()
    this.loadStats()
    setInterval(this.loadStats, 1000 * 60 * 5)
  },

  watch: {
    favourites(newValue) {
      window.localStorage.setItem('favourites', newValue)
    }
  },

  methods: {
    loadStats() {
      axios
        .get('stats.json')
        .then(response => {
          this.groups = response.data;
          document.getElementById('lastUpdated').textContent = response.headers['last-modified'];
        });
    },

    loadSettings() {
      let container = document.getElementById('settings');

      this.favourites = window.localStorage.getItem("favourites")?.split(",") || []

      for (const name in this.settings) {
        let storedValue = window.localStorage.getItem(name)
        let defaultValue = this.settings[name].value
        this.settings[name].value = storedValue === null ? defaultValue : (storedValue === 'true' ? true : false)

        let label = document.createElement('label')
        let box = document.createElement('input')
        label.setAttribute('for', name)
        label.textContent = this.settings[name].label
        box.name = name
        box.id = name
        box.type = 'checkbox'
        box.checked = this.settings[name].value

        box.addEventListener('change', (event) => this.toggleSetting(event.target.name))

        container.append(box)
        container.append(label)
      }
      this.updateClasses()
    },

    toggleSetting(name) {
      this.settings[name].value = !this.settings[name].value
      window.localStorage.setItem(name, this.settings[name].value)
      this.updateClasses()
    },

    updateClasses() {
      for (const name in this.settings) {
        document.body.classList.toggle(name, this.settings[name].value)
      }
    }
  },
});

