/* Stella web UI: API helpers, overlay drawing and Alpine components. */
'use strict';

const CSRF = document.querySelector('meta[name="csrf-token"]').content;
const DEVICE_ID = (document.querySelector('meta[name="device-id"]') || {}).content || '';

async function api(method, url, data) {
  const opts = { method, headers: { 'X-CSRF-Token': CSRF }, credentials: 'same-origin' };
  if (data !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(data);
  }
  const resp = await fetch(url, opts);
  if (resp.status === 401) { location.href = '/login?next=' + encodeURIComponent(location.pathname); }
  let json = null;
  try { json = await resp.json(); } catch (e) { /* empty body */ }
  if (!resp.ok) {
    const err = new Error((json && json.error) || ('Error HTTP ' + resp.status));
    err.status = resp.status;
    throw err;
  }
  return json;
}

function toast(message, kind) {
  const box = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = 'toast ' + (kind || 'ok');
  el.textContent = message;
  box.appendChild(el);
  setTimeout(() => el.remove(), kind === 'error' ? 6000 : 3000);
}

function clone(obj) { return JSON.parse(JSON.stringify(obj)); }

function duration(seconds) {
  if (seconds == null) return '–';
  const d = Math.floor(seconds / 86400), h = Math.floor(seconds % 86400 / 3600), m = Math.floor(seconds % 3600 / 60);
  return (d ? d + ' d ' : '') + (h ? h + ' h ' : '') + m + ' min';
}

/* ---------- overlay ---------- */

const COLORS = { roi: 'rgba(0, 140, 255, 0.18)', roiEdge: 'rgba(0, 160, 255, 0.9)', line: '#ff2bd6',
                 entry: '#2ecc71', sideA: '#00d1ff', sideB: '#2ecc71', none: '#bbbbbb', handle: '#ffffff' };

function drawScene(canvas, scene) {
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);
  const px = (p) => [p[0] * W, p[1] * H];

  if (scene.roi && scene.roi.length) {
    ctx.beginPath();
    scene.roi.forEach((p, i) => { const [x, y] = px(p); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
    if (scene.roi.length > 2) ctx.closePath();
    ctx.fillStyle = COLORS.roi; ctx.fill();
    ctx.lineWidth = 2; ctx.strokeStyle = COLORS.roiEdge; ctx.stroke();
  }

  if (scene.line) {
    const [a, b] = scene.line.map(px);
    ctx.lineWidth = 3; ctx.strokeStyle = COLORS.line;
    ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
    // Arrow towards the side that counts as "entry".
    let nx = -(b[1] - a[1]), ny = b[0] - a[0];
    const len = Math.hypot(nx, ny) || 1;
    nx /= len; ny /= len;
    if (scene.invert) { nx = -nx; ny = -ny; }
    const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2, L = Math.min(W, H) * 0.12;
    const sx = mx - nx * L / 2, sy = my - ny * L / 2, ex = mx + nx * L / 2, ey = my + ny * L / 2;
    ctx.strokeStyle = COLORS.entry; ctx.fillStyle = COLORS.entry; ctx.lineWidth = 4;
    ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(ex, ey); ctx.stroke();
    const ang = Math.atan2(ey - sy, ex - sx), hs = 12;
    ctx.beginPath(); ctx.moveTo(ex, ey);
    ctx.lineTo(ex - hs * Math.cos(ang - 0.5), ey - hs * Math.sin(ang - 0.5));
    ctx.lineTo(ex - hs * Math.cos(ang + 0.5), ey - hs * Math.sin(ang + 0.5));
    ctx.closePath(); ctx.fill();
    ctx.font = 'bold 13px system-ui, sans-serif';
    ctx.fillText('entrada', ex + 6, ey + 4);
  }

  (scene.tracks || []).forEach((t) => {
    const x1 = t.box[0] * W, y1 = t.box[1] * H, x2 = t.box[2] * W, y2 = t.box[3] * H;
    const color = t.side < 0 ? COLORS.sideA : t.side > 0 ? COLORS.sideB : COLORS.none;
    ctx.lineWidth = 2; ctx.strokeStyle = color; ctx.globalAlpha = t.missing ? 0.4 : 1;
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.arc((x1 + x2) / 2, y2, 4, 0, Math.PI * 2); ctx.fill();
    ctx.font = 'bold 12px system-ui, sans-serif';
    ctx.fillText('#' + t.id, x1 + 3, y1 + 14);
    ctx.globalAlpha = 1;
  });

  (scene.handles || []).forEach((p) => {
    const [x, y] = px(p);
    ctx.beginPath(); ctx.arc(x, y, 7, 0, Math.PI * 2);
    ctx.fillStyle = COLORS.handle; ctx.fill();
    ctx.lineWidth = 2; ctx.strokeStyle = '#000'; ctx.stroke();
  });
}

/* Shared behaviour of components that show the video with an overlay. */
function videoBase() {
  return {
    pipelineError: '',
    videoError: false,
    resize() {
      const img = this.$refs.video, canvas = this.$refs.canvas;
      if (!img || !canvas) return;
      canvas.width = img.clientWidth;
      canvas.height = img.clientHeight;
      this.draw();
    },
    initVideo() {
      new ResizeObserver(() => this.resize()).observe(this.$refs.video);
    },
  };
}

/* Without Internet the board cannot sync its clock: offer it the browser's time
   (the server applies it only when NTP is not synchronized). Once per 10 minutes. */
async function syncClock() {
  if (location.pathname === '/login') return;
  try {
    const last = Number(sessionStorage.getItem('stella-clock') || 0);
    if (Date.now() - last < 600000) return;
    sessionStorage.setItem('stella-clock', String(Date.now()));
  } catch (e) { /* storage unavailable: just try */ }
  try {
    const r = await api('POST', '/api/v1/system/clock', { epoch: Date.now() / 1000 });
    if (r.changed) toast('Hora de la placa ajustada con la de este dispositivo (' + Math.round(r.offset) + ' s)');
  } catch (e) { /* not critical */ }
}
document.addEventListener('DOMContentLoaded', syncClock);

document.addEventListener('alpine:init', () => {
  /* ---------- dashboard ---------- */
  Alpine.data('dashboard', () => ({
    ...videoBase(),
    counters: {}, pipeline: {}, status: {}, events: [], roi: null, line: null, invert: false, source: null,
    async init() {
      this.initVideo();
      const counting = await api('GET', '/api/v1/config/counting');
      Object.assign(this, { roi: counting.roi, line: counting.line, invert: counting.invert });
      this.events = await api('GET', '/api/v1/events?limit=15');
      this.refreshStatus();
      setInterval(() => this.refreshStatus(), 10000);
      this.connect();
    },
    connect() {
      this.source = new EventSource('/api/v1/stream');
      this.source.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        this.pipeline = msg.pipeline;
        this.counters = msg.counters;
        this.pipelineError = msg.pipeline.error || '';
        if (msg.event && !this.events.some((ev) => ev.uid === msg.event.uid)) {
          this.events.unshift(msg.event);
          this.events = this.events.slice(0, 15);
        }
        this.draw();
      };
    },
    async refreshStatus() {
      try { this.status = await api('GET', '/api/v1/status'); } catch (e) { /* ignore */ }
    },
    draw() {
      if (!this.$refs.canvas) return;
      drawScene(this.$refs.canvas, { roi: this.roi, line: this.line, invert: this.invert, tracks: this.pipeline.tracks });
    },
    async resetCounters() {
      if (!confirm('¿Poner a cero las entradas, salidas y el aforo de hoy?')) return;
      try {
        this.counters = await api('POST', '/api/v1/counters/reset', { occupancy: 0 });
        toast('Conteo reiniciado');
      } catch (e) { toast(e.message, 'error'); }
    },
    mqttClass() { return !this.status.mqtt || !this.status.mqtt.enabled ? 'off' : this.status.mqtt.connected ? 'ok' : 'bad'; },
    mqttText() { return !this.status.mqtt || !this.status.mqtt.enabled ? 'desactivado' : this.status.mqtt.connected ? 'conectado' : 'desconectado'; },
    duration,
  }));

  /* ---------- calibration editor ---------- */
  Alpine.data('calibration', () => ({
    ...videoBase(),
    mode: 'line', roi: [], line: [[0, 0.5], [1, 0.5]], invert: false, tracks: [], saving: false, drag: null,
    async init() {
      this.initVideo();
      const c = await api('GET', '/api/v1/config/counting');
      Object.assign(this, { roi: c.roi, line: c.line, invert: c.invert });
      this.$watch('invert', () => this.draw());
      this.$watch('mode', () => this.draw());
      const canvas = this.$refs.canvas;
      canvas.addEventListener('pointerdown', (e) => this.down(e));
      canvas.addEventListener('pointermove', (e) => this.move(e));
      canvas.addEventListener('pointerup', () => { this.drag = null; });
      canvas.addEventListener('dblclick', (e) => this.dbl(e));
      const source = new EventSource('/api/v1/stream');
      source.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        this.tracks = msg.pipeline.tracks || [];
        this.pipelineError = msg.pipeline.error || '';
        this.draw();
      };
    },
    pos(e) {
      const r = this.$refs.canvas.getBoundingClientRect();
      const clamp = (v) => Math.min(1, Math.max(0, v));
      return [clamp((e.clientX - r.left) / r.width), clamp((e.clientY - r.top) / r.height)];
    },
    nearest(points, p) {
      const r = this.$refs.canvas.getBoundingClientRect();
      let best = -1, bestD = 14;
      points.forEach((q, i) => {
        const d = Math.hypot((q[0] - p[0]) * r.width, (q[1] - p[1]) * r.height);
        if (d < bestD) { best = i; bestD = d; }
      });
      return best;
    },
    points() { return this.mode === 'roi' ? this.roi : this.line; },
    down(e) {
      const p = this.pos(e);
      const i = this.nearest(this.points(), p);
      if (i >= 0) { this.drag = i; this.$refs.canvas.setPointerCapture(e.pointerId); return; }
      if (this.mode === 'roi') { this.roi.push(p); this.draw(); }
    },
    move(e) {
      if (this.drag === null) return;
      const p = this.pos(e);
      this.points()[this.drag] = p;
      this.draw();
    },
    dbl(e) {
      if (this.mode !== 'roi') return;
      const i = this.nearest(this.roi, this.pos(e));
      if (i >= 0) { this.roi.splice(i, 1); this.draw(); }
    },
    fullRoi() { this.roi = [[0, 0], [1, 0], [1, 1], [0, 1]]; this.draw(); },
    draw() {
      if (!this.$refs.canvas) return;
      drawScene(this.$refs.canvas, { roi: this.roi, line: this.line, invert: this.invert, tracks: this.tracks,
                                     handles: this.points() });
    },
    async save() {
      if (this.roi.length < 3) { toast('La zona necesita al menos 3 puntos', 'error'); return; }
      this.saving = true;
      try {
        await api('PUT', '/api/v1/config/counting', { roi: this.roi, line: this.line, invert: this.invert });
        toast('Zona y línea guardadas');
      } catch (e) { toast(e.message, 'error'); }
      this.saving = false;
    },
  }));

  /* ---------- generic config section form ---------- */
  Alpine.data('section', (name) => ({
    data: null, saving: false,
    async init() { this.data = await api('GET', '/api/v1/config/' + name); },
    payload() { return this.data; },
    async save() {
      this.saving = true;
      try {
        this.data = await api('PUT', '/api/v1/config/' + name, this.payload());
        toast('Guardado');
        this.afterSave && this.afterSave();
      } catch (e) { toast(e.message, 'error'); }
      this.saving = false;
    },
  }));

  const sectionForm = (name, extra) => () => Object.assign({
    data: null, saving: false,
    async init() { this.data = await api('GET', '/api/v1/config/' + name); if (this.loaded) await this.loaded(); },
    payload() { return this.data; },
    async save() {
      this.saving = true;
      try {
        this.data = await api('PUT', '/api/v1/config/' + name, this.payload());
        if (this.loaded) await this.loaded();
        toast('Guardado');
      } catch (e) { toast(e.message, 'error'); }
      this.saving = false;
    },
  }, extra, clone(extra));  // methods from extra, fresh copies of its data

  /* ---------- integrations ---------- */
  Alpine.data('mqttForm', sectionForm('mqtt', {
    testing: false,
    topics() {
      const base = (this.data.topic_prefix || 'stella') + '/' + DEVICE_ID + '/';
      return ['event', 'counters', 'status', 'availability', 'cmd'].map((t) => base + t);
    },
    async test() {
      this.testing = true;
      try {
        const r = await api('POST', '/api/v1/test/mqtt', this.data);
        toast(r.message, r.ok ? 'ok' : 'error');
      } catch (e) { toast(e.message, 'error'); }
      this.testing = false;
    },
  }));

  Alpine.data('webhookForm', sectionForm('webhook', {
    testing: false, headers: [],
    loaded() { this.headers = Object.entries(this.data.headers || {}).map(([key, value]) => ({ key, value })); },
    payload() {
      const headers = {};
      this.headers.filter((h) => h.key.trim()).forEach((h) => { headers[h.key.trim()] = h.value; });
      return Object.assign(clone(this.data), { headers });
    },
    async test() {
      this.testing = true;
      try {
        const r = await api('POST', '/api/v1/test/webhook', this.payload());
        toast(r.message, r.ok ? 'ok' : 'error');
      } catch (e) { toast(e.message, 'error'); }
      this.testing = false;
    },
  }));

  Alpine.data('tokenForm', () => ({
    token: '', show: false,
    async init() { this.token = (await api('GET', '/api/v1/auth/token')).token; },
    toggle() { this.show = !this.show; },
    async regenerate() {
      if (!confirm('El token actual dejará de funcionar. ¿Generar uno nuevo?')) return;
      this.token = (await api('POST', '/api/v1/auth/token')).token;
      this.show = true;
      toast('Token nuevo generado');
    },
  }));

  /* ---------- network ---------- */
  Alpine.data('networkForm', sectionForm('network', {
    status: null, statusError: '', showPassword: false,
    form: { ssid: '', password: '', hidden: false },
    async loaded() { if (!this.status) this.loadStatus(); },
    async loadStatus() {
      try { this.status = await api('GET', '/api/v1/network/status'); this.statusError = ''; }
      catch (e) { this.statusError = e.message; }
    },
    webUrl() { return this.status && this.status.hostname ? 'http://' + this.status.hostname + '.local:7777' : ''; },
    notice: '',
    async connect() {
      const ssid = this.form.ssid.trim();
      if (!ssid) { toast('Escribe el nombre de la red', 'error'); return; }
      if (this.form.password && this.form.password.length < 8) { toast('La clave debe tener al menos 8 caracteres', 'error'); return; }
      const others = this.data.wifi.filter((w) => w.ssid !== ssid);
      // The newest network gets the highest priority.
      const top = others.reduce((m, w) => Math.max(m, w.priority || 0), 0);
      this.data.wifi = others.concat([{ ssid, password: this.form.password, priority: top + 1, hidden: this.form.hidden }]);
      await this.save();
      this.form = { ssid: '', password: '', hidden: false };
      this.notice = 'Red «' + ssid + '» guardada. La placa se está conectando: si estabas en ' + this.data.hotspot.ssid +
                    ' perderás la conexión. Después entra en ' + (this.webUrl() || 'la IP que le dé tu router') +
                    '. Si no lo consigue en un minuto, vuelve a crear ' + this.data.hotspot.ssid + '.';
    },
    async forget(i) {
      if (!confirm('¿Olvidar la red «' + this.data.wifi[i].ssid + '»?')) return;
      this.data.wifi.splice(i, 1);
      await this.save();
    },
  }));

  /* ---------- system ---------- */
  Alpine.data('deviceForm', sectionForm('device', {
    zones: [],
    async loaded() { if (!this.zones.length) this.zones = await api('GET', '/api/v1/timezones'); },
  }));

  Alpine.data('countingForm', sectionForm('counting', {
    occupancy: 0,
    payload() { return { reset_time: this.data.reset_time, occupancy_limit: this.data.occupancy_limit }; },
    async reset() {
      if (!confirm('¿Poner los contadores de hoy a cero?')) return;
      try { await api('POST', '/api/v1/counters/reset', { occupancy: this.occupancy }); toast('Contadores reiniciados'); }
      catch (e) { toast(e.message, 'error'); }
    },
  }));

  Alpine.data('ledsForm', sectionForm('leds', {
    labels: { entry: 'Entrada', exit: 'Salida', no_network: 'Sin red', hotspot: 'Hotspot activo', error: 'Error', full: 'Aforo completo' },
    swatch(c) { return 'background: rgb(' + c.map((v) => (v ? 255 : 30)).join(',') + ')'; },
    driver: '',
    ledResult(r, what) {
      this.driver = r.driver;
      if (r.driver === 'none') toast('No hay controlador de LED activo (driver: ninguno)', 'error');
      else toast(what);
    },
    async test(color) {
      try { this.ledResult(await api('POST', '/api/v1/leds/test', { color, seconds: 3 }), 'LED encendido 3 s'); }
      catch (e) { toast(e.message, 'error'); }
    },
    async sequence() {
      try { this.ledResult(await api('POST', '/api/v1/leds/test', { sequence: true }), 'Rojo, verde, azul y blanco'); }
      catch (e) { toast(e.message, 'error'); }
    },
  }));

  Alpine.data('otaForm', sectionForm('ota', {
    state: null, stateError: '', checking: false,
    async loaded() { if (!this.state) this.loadState(); },
    async loadState() {
      try { this.state = await api('GET', '/api/v1/ota'); this.stateError = ''; }
      catch (e) { this.stateError = e.message; }
    },
    async saveConfig() { await this.save(); },
    async check() {
      this.checking = true;
      try { this.state = await api('POST', '/api/v1/ota/check'); toast(this.state.message); }
      catch (e) { toast(e.message, 'error'); }
      this.checking = false;
    },
    async apply() {
      if (!confirm('Se instalará la actualización y Stella se reiniciará. ¿Continuar?')) return;
      try { const r = await api('POST', '/api/v1/ota/apply'); toast(r.message); }
      catch (e) { toast(e.message, 'error'); }
    },
  }));

  Alpine.data('passwordForm', () => ({
    username: '', current: '', next: '', repeat: '', saving: false,
    async save() {
      if (this.next !== this.repeat) { toast('Las contraseñas nuevas no coinciden', 'error'); return; }
      this.saving = true;
      try {
        await api('POST', '/api/v1/auth/password', { username: this.username, current: this.current, new: this.next });
        toast('Contraseña cambiada');
        this.current = this.next = this.repeat = '';
        setTimeout(() => location.reload(), 800);
      } catch (e) { toast(e.message, 'error'); }
      this.saving = false;
    },
  }));

  Alpine.data('actionsPanel', () => ({
    logs: [],
    async loadLogs() { this.logs = await api('GET', '/api/v1/logs?limit=200'); },
    async restart() {
      if (!confirm('¿Reiniciar el servicio Stella?')) return;
      const r = await api('POST', '/api/v1/system/restart');
      toast(r.message);
      setTimeout(() => location.reload(), 8000);
    },
    async reboot() {
      if (!confirm('¿Reiniciar el equipo completo?')) return;
      try { const r = await api('POST', '/api/v1/system/reboot'); toast(r.message); }
      catch (e) { toast(e.message, 'error'); }
    },
    async factoryReset() {
      const word = prompt('Se borrarán las redes wifi, el historial, los contadores y la configuración.\n' +
                          'Escribe RESTAURAR para confirmar:');
      if (word === null) return;
      try {
        const r = await api('POST', '/api/v1/system/factory-reset', { confirm: word.trim() });
        toast(r.message);
        document.body.classList.add('resetting');
      } catch (e) { toast(e.message, 'error'); }
    },
  }));
});
