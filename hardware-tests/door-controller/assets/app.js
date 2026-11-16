// Door controller: the live page. Talks to main.py through socket.io: it sends 'cmd' and receives 'state' and 'notice'.
(function () {
  const socket = io(window.location.origin);
  const $ = (id) => document.getElementById(id);
  const EVENT_COLUMNS = ['time', 'kind', 'text', 'mm'];
  const FIELDS = { closed_mm: 'closedMm', closed_tol_mm: 'tolMm', open_mm: 'openMm', pwm: 'pwm', ramp_ms: 'ramp', open_ms: 'openMs', close_ms: 'closeMs', open_dir: 'openDir' };
  let state = null, serverSettings = null, lastEvents = null;

  const clampInt = (v, lo, hi, fallback) => { const n = parseInt(v, 10); return Number.isFinite(n) ? Math.max(lo, Math.min(hi, n)) : fallback; };
  const send = (o) => socket.emit('cmd', o);
  const moving = () => !!(state && state.mode === 'moving');
  function showNotice(level, text) { const el = $('notice'); el.className = 'notice ' + (level || 'info'); el.textContent = text; }

  function settings() {                       // what is in the boxes, cut to the limits (a box with rubbish keeps the board's value)
    const s = (state && state.settings) || { closed_mm: 96, closed_tol_mm: 15, open_mm: 250, pwm: 100, ramp_ms: 250, open_ms: 600, close_ms: 600, open_dir: -1 };
    const out = {
      closed_mm: clampInt($('closedMm').value, 30, 1000, s.closed_mm), closed_tol_mm: clampInt($('tolMm').value, 5, 40, s.closed_tol_mm), open_mm: clampInt($('openMm').value, 60, 3500, s.open_mm),
      pwm: clampInt($('pwm').value, 60, 255, s.pwm), ramp_ms: clampInt($('ramp').value, 0, 1000, s.ramp_ms), open_ms: clampInt($('openMs').value, 50, 3000, s.open_ms),
      close_ms: clampInt($('closeMs').value, 50, 3000, s.close_ms), open_dir: parseInt($('openDir').value, 10) < 0 ? -1 : 1
    };
    $('closedMm').value = out.closed_mm; $('tolMm').value = out.closed_tol_mm; $('openMm').value = out.open_mm; $('pwm').value = out.pwm; $('ramp').value = out.ramp_ms; $('openMs').value = out.open_ms; $('closeMs').value = out.close_ms;
    return out;
  }

  $('toggleBtn').addEventListener('click', (e) => { if (!moving()) send({ action: 'toggle' }); e.currentTarget.blur(); });
  $('openBtn').addEventListener('click', (e) => { if (!moving()) send({ action: 'open' }); e.currentTarget.blur(); });
  $('closeBtn').addEventListener('click', (e) => { if (!moving()) send({ action: 'close' }); e.currentTarget.blur(); });
  $('stopBtn').addEventListener('click', (e) => { send({ action: 'stop' }); e.currentTarget.blur(); });
  $('calBtn').addEventListener('click', (e) => { if (!moving()) send({ action: 'calibrate' }); e.currentTarget.blur(); });
  $('saveBtn').addEventListener('click', (e) => { send({ action: 'settings', settings: settings() }); e.currentTarget.blur(); });
  $('pushBack').addEventListener('change', () => send({ action: 'settings', settings: { push_back: $('pushBack').checked } }));
  $('evClear').addEventListener('click', (e) => { send({ action: 'clear_events' }); e.currentTarget.blur(); });
  $('evCsv').addEventListener('click', (e) => {
    e.currentTarget.blur();
    const rows = state ? state.events : [];
    if (!rows.length) { showNotice('warn', 'Nothing to download yet: no events.'); return; }
    const a = document.createElement('a');
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(toCsv(rows));
    a.download = 'door_events.csv';
    document.body.appendChild(a); a.click(); a.remove();
  });

  // ESC always stops the motor. SPACE is the push-button: it opens a closed door and closes any other, and stops the motor if the door is already moving.
  // SPACE does nothing while the person is typing or choosing in a field, and it must never "click" a focused button.
  document.addEventListener('keydown', (e) => {
    if (e.code === 'Escape' || e.key === 'Escape') { e.preventDefault(); send({ action: 'stop' }); return; }
    if (e.code !== 'Space') return;
    const t = e.target && e.target.tagName;
    if (t === 'INPUT' || t === 'SELECT' || t === 'TEXTAREA') return;
    e.preventDefault();
    if (moving()) send({ action: 'stop' }); else send({ action: 'toggle' });
  });
  document.addEventListener('keyup', (e) => { if (e.code === 'Space' && e.target && e.target.tagName === 'BUTTON') e.preventDefault(); });

  function csvCell(v) { const s = v === null || v === undefined ? '' : String(v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }
  function toCsv(rows) { return [EVENT_COLUMNS.join(',')].concat(rows.map((r) => EVENT_COLUMNS.map((c) => csvCell(r[c])).join(','))).join('\n') + '\n'; }

  function headline(s) {
    if (s.sensor === 'waiting') return { text: 'WAITING FOR THE SENSOR', cls: 'unknown', sub: 'No distance readings have arrived yet: is the app running on the board?' };
    if (s.sensor === 'lost') return { text: 'SENSOR LOST', cls: 'fault', sub: 'No distance readings for over a second: is the sketch running?' };
    if (s.fault) return { text: 'FAULT', cls: 'fault', sub: s.fault };
    if (s.tamper) return { text: 'TAMPER', cls: 'tamper', sub: 'The locked door was forced, or something is in front of the sensor.' };
    if (s.mode === 'moving') return { text: 'MOVING: ' + (s.moving === 'open' ? 'opening' : 'closing') + (s.attempt > 1 ? ' (second try)' : ''), cls: 'moving', sub: 'The door is checked with the sensor when the move has ended.' };
    if (s.mode === 'locked') return { text: 'LOCKED', cls: 'locked', sub: 'The door is closed.' };
    if (s.mode === 'unlocked') return { text: 'UNLOCKED', cls: 'unlocked', sub: 'The door is open.' };
    return { text: 'UNKNOWN', cls: 'unknown', sub: 'The door state is not known yet.' };
  }

  function drawChart(s) {
    const c = $('chart'); const ctx = c.getContext && c.getContext('2d');
    if (!ctx) return;
    const W = c.width, H = c.height, padL = 52, padB = 18, padT = 8, top = Math.min(600, Math.max(s.bands.open + 100, 300));
    const x = (t) => padL + ((t + 30) / 30) * (W - padL - 6);
    const y = (v) => padT + (1 - Math.min(v, top) / top) * (H - padT - padB);
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = 'rgba(46,158,91,0.22)'; ctx.fillRect(padL, y(s.bands.hi), W - padL - 6, y(s.bands.lo) - y(s.bands.hi));
    ctx.strokeStyle = '#98600d'; ctx.lineWidth = 1; ctx.setLineDash && ctx.setLineDash([6, 4]);
    ctx.beginPath(); ctx.moveTo(padL, y(s.bands.open)); ctx.lineTo(W - 6, y(s.bands.open)); ctx.stroke(); ctx.setLineDash && ctx.setLineDash([]);
    ctx.font = '12px sans-serif'; ctx.fillStyle = '#5b6575';
    ctx.fillText(s.bands.hi + ' mm', 4, y(s.bands.hi) + 4); ctx.fillText(s.bands.lo + ' mm', 4, y(s.bands.lo) + 4); ctx.fillText('open ' + s.bands.open, 4, y(s.bands.open) - 3);
    ctx.strokeStyle = '#2f6fdb'; ctx.lineWidth = 2; ctx.beginPath();
    let pen = false;
    (s.history || []).forEach((p) => {
      if (p[1] === null) { pen = false; ctx.fillStyle = '#9aa3b2'; ctx.fillRect(x(p[0]) - 1, padT, 2, 8); return; }
      if (!pen) { ctx.moveTo(x(p[0]), y(p[1])); pen = true; } else ctx.lineTo(x(p[0]), y(p[1]));
    });
    ctx.stroke();
  }

  function renderEvents(events) {
    const key = JSON.stringify(events);
    if (key === lastEvents) return;
    lastEvents = key;
    const body = $('events'); body.textContent = '';
    events.slice().reverse().forEach((e) => {
      const tr = document.createElement('tr');
      [e.time, e.kind, e.text, e.mm === null || e.mm === undefined ? 'no echo' : e.mm].forEach((text, i) => {
        const td = document.createElement('td'); td.textContent = text;
        if (i === 1) td.className = 'k-' + e.kind;
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
  }

  function render(s) {
    state = s;
    if (!serverSettings) serverSettings = {};
    Object.keys(FIELDS).forEach((k) => {                     // fill a box when the board's value changes (at the start, or after "calibrate"), never while it is the same
      if (serverSettings[k] !== s.settings[k]) $(FIELDS[k]).value = String(s.settings[k]);
    });
    if (serverSettings.push_back !== s.settings.push_back) $('pushBack').checked = !!s.settings.push_back;
    serverSettings = Object.assign({}, s.settings);
    const h = headline(s);
    $('headline').textContent = h.text; $('headline').className = 'headline ' + h.cls; $('sub').textContent = h.sub;
    $('mm').textContent = s.mm === null || s.mm === undefined ? '–' : String(s.mm);
    const b = s.state || '–';
    $('band').textContent = s.state === null ? 'door: not decided yet' : 'door reads: ' + b + (s.mm === null ? ' (no echo)' : ''); $('band').className = 'bandchip ' + (s.state || '');
    const chip = $('sensor');
    if (s.sensor === 'ok') { chip.textContent = 'sensor: OK'; chip.className = 'chip good'; }
    else if (s.sensor === 'lost') { chip.textContent = 'sensor: lost'; chip.className = 'chip bad'; }
    else { chip.textContent = 'sensor: waiting for readings'; chip.className = 'chip warn'; }
    const mv = moving();
    $('toggleBtn').textContent = (s.state === 'closed' ? 'Open the door' : 'Close the door') + ' (Space bar)';
    $('toggleBtn').disabled = mv; $('openBtn').disabled = mv; $('closeBtn').disabled = mv; $('calBtn').disabled = mv;
    drawChart(s);
    renderEvents(s.events || []);
  }

  socket.on('connect', () => { $('conn').textContent = 'connected'; $('conn').className = 'chip good'; send({ action: 'refresh' }); });
  socket.on('disconnect', () => { $('conn').textContent = 'disconnected'; $('conn').className = 'chip bad'; });
  socket.on('notice', (n) => showNotice(n.level, n.text));
  socket.on('state', render);
})();
