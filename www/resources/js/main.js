Vue.component("member-card", {
  props: ["member"],
  template: `
        <li v-bind:class="['member', member.twitter, member.retired ? 'retired' : '', isLive ? 'live' : (member.video ? 'scheduled' : '')]"
            v-bind:style="liStyle">
          <div class="actions">
            <span @click="toggleFavourite" class="action action-icon action-heart-full" v-if="isFavourite"></span>
            <span @click="toggleFavourite" class="action action-icon action-heart action-hidden-desktop" v-else></span>
            <a v-bind:href="'webcal://' + calendarLink"
               target="_blank"
               title="Add live streams to your calendar"
               class="action action-icon action-calendar action-hidden">
            </a>
            <a v-bind:href="'https://' + rssLink"
               target="_blank"
               title="Goto RSS feed"
               class="action action-icon action-rss action-hidden">
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
            <div class="profile-image"><img v-bind:src="member.image" alt="{{ member.name }}"></div>
            <span class="name" v-bind:style="nameStyle">{{ member.name }}</span>
          </a>
          <div class="buttons">
            <a class="ytFollowersCount followersCount"
               v-bind:href="'https://www.youtube.com/channel/' + member.youtube"
               v-bind:title="member.youtube_subs + ' subscribers on YouTube'"
               v-if="member.youtube_subs"
               target="_blank">
              <span>{{ nFormatter(member.youtube_subs, 2) }}</span> YouTube
            </a>
            <a class="bFollowersCount followersCount"
               v-bind:href="'https://space.bilibili.com/' + member.bilibili"
               v-bind:title="member.bilibili_subs + ' subscribers on Bilibili'"
               v-if="member.bilibili_subs && app.settings.bilibili.value"
               target="_blank">
              <span>{{ nFormatter(member.bilibili_subs, 2) }}</span> Bilibili
            </a>
            <a class="tFollowersCount followersCount"
               v-bind:title="member.twitter_subs + ' subscribers on Twitter'"
               v-bind:href="'https://twitter.com/' + member.twitter"
               target="_blank">
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
        maxWidth: "none",
      });
    }
  },

  computed: {
    isFavourite() {
      return app.favourites.includes(this.member.twitter);
    },

    isLive: function () {
      return this.member.video && (this.member.video.start === 0 || this.currentTimestamp() > this.member.video.start);
    },

    scheduledTitle: function () {
      if (this.member.video) {
        const date = new Date(this.member.video.start * 1000);
        return "Live " + moment(date).fromNow();
      }
    },

    calendarLink: function () {
      return window.location.host + "/events/" + this.member.twitter + ".ics?noCache";
    },

    rssLink: function () {
      return window.location.host + "/rss/" + this.member.twitter + ".xml";
    },

    mainLink: function () {
      if (this.member.youtube_subs) {
        if (this.member.video) return "https://youtube.com/watch?v=" + this.member.video.id;
        else "https://youtube.com/channel/" + this.member.youtube;
      } else if (this.member.twitter_subs) {
        return "https://twitter.com/" + this.member.twitter;
      } else if (this.member.bilibili_subs) {
        return "https://space.bilibili.com/" + member.bilibili;
      } else {
        return "#";
      }
    },

    liStyle: function () {
      let style = {
        backgroundImage: `linear-gradient(180deg, ${this.member.bg} 0%, ${this.colourShade(
          -0.9,
          this.member.bg
        )} 100%)`,
      };
      if (this.member.background_image && !app.settings.simpleBackgrounds.value) {
        style.backgroundImage = `url("${this.member.background_image}"), ${style.backgroundImage}`;
      }
      return style;
    },

    nameStyle: function () {
      if (this.member.background_image && !app.settings.simpleBackgrounds.value) {
        return { color: "#222", "font-weight": "bold" };
      } else {
        return { color: this.member.fg, "font-weight": "normal" };
      }
    },
  },

  methods: {
    toggleFavourite() {
      let index = app.favourites.indexOf(this.member.twitter);
      if (index !== -1) app.favourites.splice(index, 1);
      else app.favourites.push(this.member.twitter);
    },

    currentTimestamp() {
      return new Date().getTime() / 1000;
    },

    // https://stackoverflow.com/a/13542669/5699307
    // Takes a 6 char hex, shades it and returns a rgb(...) value
    colourShade(p, c) {
      var m = Math.round,
        c = parseInt(c.slice(1), 16),
        r = c >> 16,
        g = (c >> 8) & 255,
        b = c & 255,
        P = p < 0,
        t = P ? 0 : p * 255 ** 2,
        P = P ? 1 + p : 1 - p;
      return (
        "rgb" +
        "(" +
        m((P * r ** 2 + t) ** 0.5) +
        "," +
        m((P * g ** 2 + t) ** 0.5) +
        "," +
        m((P * b ** 2 + t) ** 0.5) +
        ")"
      );
    },

    nFormatter(num, digits) {
      if (num === undefined) return;
      var si = [
        { value: 1, symbol: "" },
        { value: 1e3, symbol: "k" },
        { value: 1e6, symbol: "M" },
        { value: 1e9, symbol: "G" },
        { value: 1e12, symbol: "T" },
        { value: 1e15, symbol: "P" },
        { value: 1e18, symbol: "E" },
      ];
      var i,
        rx = /\.0+$|(\.[0-9]*[1-9])0+$/;
      for (i = si.length - 1; i > 0; i--) {
        if (num >= si[i].value) {
          break;
        }
      }
      return (num / si[i].value).toFixed(digits).replace(rx, "$1") + si[i].symbol;
    },
  },
});

Vue.component("member-group", {
  props: ["id", "group"],
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
      let members = [];

      for (let member of this.group.members) {
        if (
          (!app.settings.retired.value && member.retired) ||
          (app.settings.onlyLive.value && !member.video) ||
          (app.settings.onlyFavourites.value && !app.favourites.includes(member.twitter))
        ) {
          continue;
        }
        members.push(member);
      }

      if (app.settings.sortLive.value && !app.settings.sortName.value) {
        members.sort((a, b) => {
          if (a.video && b.video) return a.video.start - b.video.start;
          else if (a.video) return -1;
          else if (b.video) return 1;
          return 0;
        });
      }

      if (app.settings.sortName.value) {
        members.sort((a, b) => {
          if (a.name > b.name) return 1;
          else if (a.name < b.name) return -1;
          return 0;
        });
      }

      if (app.settings.sortFavourites.value) {
        members.sort((a, b) => {
          if (app.favourites.includes(a.twitter) && app.favourites.includes(b.twitter)) return 0;
          else if (app.favourites.includes(a.twitter)) return -1;
          return 1;
        });
      }
      return members;
    },
  },
});

var app = new Vue({
  el: "#app",
  data: {
    groups: {},
    meta: {},
    favourites: [],
    showSettings: false,
    settings: {
      exportSettings: {
        label: "Export settings",
        value: "exportSettingsProcedure",
        icon: "export",
      },
      simpleBackgrounds: {
        value: false,
        label: "Show simple backgrounds",
      },
      retired: {
        value: true,
        label: "Show retired",
      },
      bilibili: {
        value: false,
        label: "Show Bilibili",
      },
      onlyLive: {
        value: false,
        label: "Only show currently live",
      },
      sortLive: {
        value: false,
        label: "Sort by live status",
      },
      onlyFavourites: {
        value: false,
        label: "Only show favourites",
      },
      sortFavourites: {
        value: true,
        label: "Sort favourites first",
      },
      sortName: {
        value: false,
        label: "Sort by name",
      },
    },
  },

  mounted() {
    this.installServiceWorker();
    this.importSettingsFromLink(window.location.href);
    this.loadSettings();
    this.loadStats();
    document.addEventListener("click", this.handleClickOutsideSettings);
    setInterval(this.loadStats, 1000 * 60 * 5);
  },

  watch: {
    favourites(newValue) {
      window.localStorage.setItem("favourites", newValue);
      this.sendFavouritesToSW();
    },
  },

  methods: {
    handleClickOutsideSettings(event) {
      const settingsElement = document.querySelector("#settings");
      if (this.showSettings) {
        if (!settingsElement.contains(event.target)) {
          event.preventDefault();
          this.showSettings = false;
        }
      } else {
        if (settingsElement.contains(event.target)) {
          event.preventDefault();
          this.showSettings = true;
        }
      }
    },

    installServiceWorker() {
      if ("serviceWorker" in navigator) {
        navigator.serviceWorker.register("/service_worker.js");

        if (Notification.permission === "default") {
          Notification.requestPermission().then((state) => {
            if (state === "granted") new Notification("You will get live update for your favourite talents!");
          });
        }
      }
    },

    loadStats() {
      axios.get("stats.json").then((response) => {
        this.groups = response.data.groups;
        this.meta = response.data.meta;
        this.$refs.lastUpdated.textContent = this.meta.subsLastUpdate;
      });
    },

    exportSettingsProcedure() {
      const url = this.exportSettingsLink();

      function failed() {
        window.history.pushState("", "", url);
        Toastify({
          text: "Copy the URL. Use it to automatically import the settings again.",
          duration: 7000,
          position: "center",
        }).showToast();
      }

      if (window.navigator.clipboard) {
        window.navigator.clipboard.writeText(url).then(() => {
          Toastify({
            text: "The settings URL has been copied. Use it to automatically import the settings again.",
            duration: 7000,
            position: "center",
          }).showToast();
        }, failed);
      } else {
        failed();
      }
    },

    exportSettingsLink() {
      let url = window.location.origin + "?";
      url += "favourites=" + window.localStorage.getItem("favourites");

      for (const name in this.settings) {
        url += `&${name}=${window.localStorage.getItem(name)}`;
      }

      return url;
    },

    importSettingsFromLink(link) {
      const url = new URL(link);
      if (url.search) {
        url.searchParams.forEach((value, key) => {
          window.localStorage.setItem(key, value);
        });
        window.history.pushState("", "", window.location.origin);

        Toastify({
          text: "Imported settings",
          duration: 3000,
          position: "center",
        }).showToast();
      }
    },

    action(name) {
      this[name]();
    },

    loadSettings() {
      this.favourites = window.localStorage.getItem("favourites")?.split(",") || [];

      for (const name in this.settings) {
        let defaultValue = this.settings[name].value;
        if (typeof defaultValue === "string") continue;
        let storedValue = window.localStorage.getItem(name);
        this.settings[name].value = storedValue === null ? defaultValue : storedValue === "true" ? true : false;
      }
      this.updateClasses();
    },

    sendFavouritesToSW() {
      const bc = new BroadcastChannel("sw");
      bc.postMessage({
        target: "favourites",
        data: this.favourites,
      });
    },

    toggleSetting(name) {
      window.localStorage.setItem(name, this.settings[name].value);
      this.updateClasses();
    },

    updateClasses() {
      for (const name in this.settings) {
        document.body.classList.toggle(name, this.settings[name].value);
      }
    },
  },
});
