// The time machine's front end: a timeline scrubber over an article's stored
// versions, and page swaps without a reload so travelling can be animated.
// Every swap still fetches the server-rendered page, so the database query
// (FOR SYSTEM_TIME AS OF) stays the single source of truth.

(() => {
  const root = document.documentElement;
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (sel, scope = document) => scope.querySelector(sel);
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const DAY = 864e5;

  const fmtDate = ms => new Date(ms).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const fmtSize = bytes => bytes >= 1024 ? `${Math.round(bytes / 1024)} KB` : `${bytes} B`;
  const toParam = ms => new Date(ms).toISOString().slice(0, 19); // what ?at= expects, in UTC

  // ---------- rolling year counter ----------
  function rollYear(el, from, to) {
    if (!el || reduceMotion || !from || !to || from === to) return;
    const start = performance.now();
    const duration = Math.min(1100, 300 + Math.abs(to - from) * 45);
    const step = now => {
      const k = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - k, 3);
      el.textContent = Math.round(from + (to - from) * eased);
      if (k < 1) requestAnimationFrame(step);
    };
    el.textContent = from;
    requestAnimationFrame(step);
  }

  // ---------- timeline scrubber ----------
  class Timeline {
    constructor(el) {
      this.el = el;
      this.dragging = false;
      el.addEventListener("pointerdown", e => {
        if (!this.versions?.length) return;
        this.dragging = true;
        el.classList.add("dragging");
        el.setPointerCapture(e.pointerId);
        this.preview(e);
      });
      el.addEventListener("pointermove", e => this.versions?.length && this.preview(e));
      el.addEventListener("pointerup", e => {
        if (!this.dragging) return;
        this.dragging = false;
        el.classList.remove("dragging");
        this.travelTo(this.msAt(e.clientX));
      });
      el.addEventListener("pointercancel", () => { this.dragging = false; el.classList.remove("dragging"); });
      el.addEventListener("keydown", e => {
        if (!this.versions?.length || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
        e.preventDefault();
        const i = this.indexAt(this.moment);
        const target = { ArrowLeft: i - 1, ArrowRight: i + 1, Home: 0, End: this.versions.length - 1 }[e.key];
        const v = this.versions[clamp(target, 0, this.versions.length - 1)];
        if (v) this.travelTo(v.ms);
      });
    }

    setData(data) {
      const sameArticle = this.data && this.data.title === data.title;
      this.data = data;
      this.versions = data.versions.map(v => ({ ...v, ms: Date.parse(v.t) }));
      if (!this.versions.length) { this.el.innerHTML = ""; return; }
      this.t0 = this.versions[0].ms;
      this.t1 = Math.max(Date.parse(data.now), this.versions.at(-1).ms + DAY);
      if (!sameArticle) this.build();
      this.place(Date.parse(data.moment));
    }

    pct(ms) { return clamp((ms - this.t0) / (this.t1 - this.t0), 0, 1) * 100; }

    msAt(clientX) {
      const r = this.el.getBoundingClientRect();
      return this.t0 + clamp((clientX - r.left) / r.width, 0, 1) * (this.t1 - this.t0);
    }

    indexAt(ms) { // the version that was live at ms, as AS OF would pick it
      let found = -1;
      this.versions.forEach((v, i) => { if (v.ms <= ms) found = i; });
      return found;
    }

    build() {
      this.el.innerHTML = `
        <svg viewBox="0 0 1000 100" preserveAspectRatio="none" aria-hidden="true">
          <path class="area"></path><path class="area-line"></path>
        </svg>
        <div class="span"></div><div class="ghost"></div><div class="marker"></div>
        <div class="tip"></div><div class="axis"></div>`;
      [this.span, this.ghost, this.marker, this.tip, this.axis] =
        [".span", ".ghost", ".marker", ".tip", ".axis"].map(s => $(s, this.el));

      // Article size over time as a step chart: each version holds until the next one.
      const max = Math.max(...this.versions.map(v => v.bytes));
      const y = b => (100 - (b / max) * 90).toFixed(2);
      const xs = this.versions.map(v => (this.pct(v.ms) * 10).toFixed(2));
      let line = `M ${xs[0]} 100 `;
      this.versions.forEach((v, i) => {
        line += `L ${xs[i]} ${y(v.bytes)} L ${i + 1 < xs.length ? xs[i + 1] : 1000} ${y(v.bytes)} `;
      });
      $(".area-line", this.el).setAttribute("d", line);
      $(".area", this.el).setAttribute("d", line + "L 1000 100 Z");

      // Year labels, thinned out so they never crowd.
      const y0 = new Date(this.t0).getUTCFullYear() + 1, y1 = new Date(this.t1).getUTCFullYear();
      const width = this.el.clientWidth;
      const every = Math.max(1, Math.ceil((y1 - y0 + 1) / Math.max(3, Math.floor(width / 70))));
      const edge = (20 / width) * 100; // half a label's width, in percent
      for (let yr = y0; yr <= y1; yr += every) {
        const at = this.pct(Date.UTC(yr, 0, 1));
        if (at < edge || at > 100 - edge) continue; // would be cut off at the edges
        const label = document.createElement("span");
        label.textContent = yr;
        label.style.left = `${at}%`;
        this.axis.append(label);
      }
    }

    place(ms) {
      this.moment = ms;
      this.marker.style.left = `${this.pct(ms)}%`;
      const i = this.indexAt(ms);
      if (i < 0) {
        this.span.style.width = "0";
      } else {
        const start = this.pct(this.versions[i].ms);
        const end = i + 1 < this.versions.length ? this.pct(this.versions[i + 1].ms) : 100;
        this.span.style.left = `${start}%`;
        this.span.style.width = `${end - start}%`;
      }
      this.el.setAttribute("aria-valuetext", fmtDate(ms));
    }

    preview(e) {
      const ms = this.msAt(e.clientX);
      const p = this.pct(ms);
      this.ghost.style.left = `${p}%`;
      this.tip.style.left = `${clamp(p, 7, 93)}%`;
      const v = this.versions[this.indexAt(ms)];
      this.tip.textContent = v ? `${fmtDate(ms)} · ${fmtSize(v.bytes)}` : `${fmtDate(ms)} · not written yet`;
      if (this.dragging) this.place(ms);
    }

    travelTo(ms) {
      const url = new URL(location.href);
      url.pathname = "/";
      url.searchParams.set("title", this.data.title);
      url.searchParams.set("at", toParam(ms));
      travel(url.toString());
    }
  }

  // ---------- page swaps ----------
  const timelineEl = $("#timeline");
  const timeline = timelineEl && new Timeline(timelineEl);
  let state = JSON.parse($("#timeline-data")?.textContent || "null");
  if (timeline && state) timeline.setData(state);

  let pending = null;
  async function travel(url, { push = true } = {}) {
    pending?.abort();
    const ctrl = (pending = new AbortController());
    root.classList.add("loading");
    try {
      const res = await fetch(url, { signal: ctrl.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const doc = new DOMParser().parseFromString(await res.text(), "text/html");
      const next = JSON.parse(doc.getElementById("timeline-data").textContent);
      const newArticle = !state || next.title !== state.title;

      root.dataset.direction = state && Date.parse(next.moment) < Date.parse(state.moment) ? "past" : "future";
      const fromYear = parseInt($("[data-year]")?.textContent, 10);
      const content = doc.getElementById("content");
      $("article", content)?.classList.remove("reveal"); // the swap animation replaces the drift-in

      const swap = () => {
        $("#content").replaceWith(content);
        $("#controls").innerHTML = doc.getElementById("controls").innerHTML;
        $("nav").innerHTML = doc.querySelector("nav").innerHTML;
        $("#timeline-count").textContent = doc.getElementById("timeline-count").textContent;
        document.title = doc.title;
        timeline.setData(next);
        state = next;
      };

      if (document.startViewTransition && !reduceMotion) {
        await document.startViewTransition(swap).updateCallbackDone;
      } else {
        swap();
        content.classList.add("warp-in");
      }
      if (push) history.pushState(null, "", url);
      if (newArticle) scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
      rollYear($("[data-year]"), fromYear, new Date(Date.parse(next.moment)).getUTCFullYear());
    } catch (err) {
      if (err.name !== "AbortError") location.href = url; // fall back to a normal page load
    } finally {
      if (pending === ctrl) root.classList.remove("loading");
    }
  }

  if (timeline) {
    document.addEventListener("submit", e => {
      if (e.target.id !== "travel-form") return;
      e.preventDefault();
      const url = new URL(location.href);
      url.search = new URLSearchParams(new FormData(e.target)).toString();
      travel(url.toString());
    });
    addEventListener("popstate", () => travel(location.href, { push: false }));
  }

  // ---------- compare page: count the stats up ----------
  if (!reduceMotion) {
    document.querySelectorAll("[data-count]").forEach(el => {
      const target = parseInt(el.dataset.count, 10);
      const start = performance.now();
      const step = now => {
        const k = Math.min(1, (now - start) / 900);
        el.textContent = Math.round(target * (1 - Math.pow(1 - k, 3)));
        if (k < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }
})();
