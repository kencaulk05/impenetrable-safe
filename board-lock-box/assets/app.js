// Finger lock box: the live page. Talks to main.py through socket.io: it sends 'cmd' and receives 'view' (the camera), 'lock' (the lock, the door, the log) and 'notice'.
(function () {
  const socket = io(window.location.origin);
  const $ = (id) => document.getElementById(id);
  const LOG_COLUMNS = ['time', 'source', 'kind', 'text'];
  let lock = null, paused = false, lastMode = null;
  const send = (o) => socket.emit('cmd', o);
  const fmt = (v, d) => (v === null || v === undefined ? '–' : (typeof v === 'number' && d !== undefined ? v.toFixed(d) : String(v)));
  function showNotice(level, text) { const el = $('notice'); el.className = 'notice ' + (level || 'info'); el.textContent = text; }

  // the LED matrix, drawn like the one on the box (13 columns, 8 rows)
  const leds = [];
  for (let i = 0; i < 104; i++) { const d = document.createElement('i'); d.className = 'led'; $('matrix').appendChild(d); leds.push(d); }
  // the six probability bars
  const bars = [];
  for (let i = 0; i < 6; i++) {
    const row = document.createElement('div'); row.className = 'bar';
    const n = document.createElement('span'); n.textContent = String(i);
    const track = document.createElement('div'); track.className = 'track'; const fill = document.createElement('div'); fill.className = 'fill'; track.appendChild(fill);
    const pct = document.createElement('span'); pct.textContent = '–';
    row.appendChild(n); row.appendChild(track); row.appendChild(pct); $('bars').appendChild(row); bars.push({ row, fill, pct });
  }

  const step = 4;
  const nudge = (dx, dy, ds) => send({ action: 'nudge', dx: dx, dy: dy, ds: ds });
  $('pushBtn').addEventListener('click', (e) => { send({ action: 'button' }); e.currentTarget.blur(); });
  $('stopBtn').addEventListener('click', (e) => { send({ action: 'stop' }); e.currentTarget.blur(); });
  $('openBtn').addEventListener('click', (e) => { send({ action: 'door_open' }); e.currentTarget.blur(); });
  $('closeBtn').addEventListener('click', (e) => { send({ action: 'door_close' }); e.currentTarget.blur(); });
  $('calBtn').addEventListener('click', (e) => { send({ action: 'calibrate' }); e.currentTarget.blur(); });
  $('pushBack').addEventListener('change', () => send({ action: 'push_back', on: $('pushBack').checked }));
  [['left', -step, 0, 0], ['right', step, 0, 0], ['up', 0, -step, 0], ['down', 0, step, 0], ['smaller', 0, 0, -step], ['bigger', 0, 0, step]].forEach((b) => $(b[0]).addEventListener('click', (e) => { nudge(b[1], b[2], b[3]); e.currentTarget.blur(); }));
  $('find').addEventListener('click', (e) => { send({ action: 'find_tape', color: $('color').value }); e.currentTarget.blur(); });
  $('saveRoi').addEventListener('click', (e) => { send({ action: 'save_roi' }); e.currentTarget.blur(); });
  $('resetRoi').addEventListener('click', (e) => { send({ action: 'reset_roi' }); e.currentTarget.blur(); });
  $('applyFmt').addEventListener('click', (e) => { send({ action: 'camera_mode', fourcc: $('fmt').value }); e.currentTarget.blur(); });
  $('clearLog').addEventListener('click', (e) => { send({ action: 'clear_log' }); e.currentTarget.blur(); });
  function downloadRows(rows, name) {
    const cell = (v) => { const s = v === null || v === undefined ? '' : String(v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
    const text = [LOG_COLUMNS.join(',')].concat(rows.map((r) => LOG_COLUMNS.map((c) => cell(r[c])).join(','))).join('\n') + '\n';
    const a = document.createElement('a');
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(text); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
  }
  $('csv').addEventListener('click', (e) => {
    e.currentTarget.blur();
    const rows = lock ? lock.log : [];
    if (!rows.length) { showNotice('warn', 'Nothing to download yet: the log is empty.'); return; }
    downloadRows(rows, 'lockbox_log.csv');
  });
  $('wholeLog').addEventListener('click', (e) => { send({ action: 'log_full' }); e.currentTarget.blur(); });
  $('resetStats').addEventListener('click', (e) => { send({ action: 'reset_stats' }); e.currentTarget.blur(); });

  // choosing a new code: checked here a little, checked properly by the board. The boxes are emptied at once, so the digits do not stay on the page.
  $('saveCode').addEventListener('click', (e) => {
    e.currentTarget.blur();
    const code = $('code').value, confirm = $('confirm').value;
    $('code').value = ''; $('confirm').value = '';
    if (!/^[1-5]{3}$/.test(code) || new Set(code).size !== 3) { showNotice('warn', 'A code is 3 DIFFERENT digits, each from 1 to 5 (for example 314).'); return; }
    if (code !== confirm) { showNotice('warn', 'The two codes are not the same: type them again.'); return; }
    send({ action: 'set_code', code: code, confirm: confirm, challenge: parseInt($('challenge').value, 10), pool: $('pool').value });
  });

  // The SPACE bar is the push-button and ESC stops the motor. SPACE does nothing while the person is typing or choosing in a field, and it must never "click" a focused button.
  // The arrow keys and + and - move the square, but only while the "Camera and square" part is open.
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { e.preventDefault(); send({ action: 'stop' }); return; }
    const t = e.target && e.target.tagName;
    if (t === 'INPUT' || t === 'SELECT' || t === 'TEXTAREA') return;
    if (e.code === 'Space' || e.key === ' ') { e.preventDefault(); send({ action: 'button' }); return; }
    if (!$('squareBox').open) return;
    const d = step * (e.shiftKey ? 4 : 1);
    const moves = { ArrowLeft: [-d, 0, 0], ArrowRight: [d, 0, 0], ArrowUp: [0, -d, 0], ArrowDown: [0, d, 0], '+': [0, 0, d], '=': [0, 0, d], '-': [0, 0, -d], '_': [0, 0, -d] };
    const m = moves[e.key];
    if (m) { e.preventDefault(); nudge(m[0], m[1], m[2]); }
  });
  document.addEventListener('keyup', (e) => { const t = e.target && e.target.tagName; if ((e.code === 'Space' || e.key === ' ') && (t === 'BUTTON' || t === 'SUMMARY')) e.preventDefault(); });

  function banner(L) {
    if (!L.configured) return { text: 'SET A CODE', cls: 'unknown' };
    if (L.tamper_left > 0 || L.door.tamper) return { text: 'TAMPER' + (L.tamper_left > 0 ? ': entry blocked ' + Math.ceil(L.tamper_left) + ' s' : ''), cls: 'tamper' };
    const d = L.display;
    if (L.state === 'lockout') return { text: 'LOCKED OUT: ' + Math.ceil(d.lockout_left) + ' s', cls: 'lockout' };
    if (L.state === 'challenge') return { text: 'CHALLENGE: show the digit', cls: 'challenge' };
    if (L.state === 'entering') return { text: 'SHOW YOUR CODE: ' + (d.entered + 1) + ' of ' + d.of, cls: 'entering' };
    if (L.state === 'unlocked') return { text: 'UNLOCKED: ' + Math.ceil(d.unlocked_left) + ' s', cls: 'unlocked' };
    return { text: 'LOCKED', cls: 'locked' };
  }

  function renderLog(rows) {
    const body = $('logRows'); body.textContent = '';
    rows.slice().reverse().forEach((e) => {
      const tr = document.createElement('tr');
      [e.time, e.source, e.kind, e.text].forEach((text, i) => { const td = document.createElement('td'); td.textContent = text; if (i === 2) td.className = 'k-' + e.kind; tr.appendChild(td); });
      body.appendChild(tr);
    });
  }

  const mmss = (s) => { const t = Math.max(0, Math.floor(s || 0)); return Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0'); };
  const secs = (o) => (o.n ? o.median + ' s (last ' + o.last + ' s, ' + o.n + ' measured)' : '–');
  function renderStats(S) {
    $('sSessions').textContent = S.sessions; $('sUnlocked').textContent = S.unlocked; $('sCode').textContent = S.denied_code; $('sChallenge').textContent = S.denied_challenge;
    $('sTimeouts').textContent = S.timeouts; $('sLockouts').textContent = S.lockouts; $('sTamper').textContent = S.tamper; $('sFaults').textContent = S.faults;
    $('sUnlock').textContent = secs(S.unlock_s); $('sOpen').textContent = secs(S.open_s);
    $('sCheck').textContent = S.check_ms.n ? S.check_ms.last + ' ms (slowest ' + S.check_ms.slowest + ' ms)' : '–';
    $('sLocked').textContent = mmss(S.locked_for_s); $('sUptime').textContent = mmss(S.uptime_s);
  }

  function renderLock(L) {
    lock = L;
    if (L.stats) renderStats(L.stats);
    L.picture.forEach((row, r) => { for (let c = 0; c < 13; c++) leds[r * 13 + c].classList.toggle('on', ((row >> (12 - c)) & 1) === 1); });
    const b = banner(L);
    $('banner').textContent = b.text; $('banner').className = 'banner ' + b.cls; $('hint').textContent = L.hint;
    // the digit to show first, and the progress dots (how many digits were read: never which)
    const ch = L.challenge_digit !== null && L.challenge_digit !== undefined;
    $('challengebox').hidden = !ch; $('bigChallenge').textContent = ch ? String(L.challenge_digit) : '';
    const showDots = L.configured && L.state === 'entering';
    $('dotsbox').hidden = !showDots; $('dots').textContent = '';
    if (showDots) for (let i = 0; i < L.display.of; i++) { const dot = document.createElement('i'); dot.className = 'dot' + (i < L.display.entered ? ' on' : ''); $('dots').appendChild(dot); }
    // the chips
    const cc = $('codechip');
    if (L.configured) { cc.textContent = 'code is set'; cc.className = 'chip good'; } else { cc.textContent = 'no code set yet'; cc.className = 'chip warn'; }
    const door = L.door, dc = $('doorchip');
    if (door.sensor === 'lost') { dc.textContent = 'door sensor lost'; dc.className = 'chip bad'; }
    else if (door.sensor === 'waiting') { dc.textContent = 'door sensor: waiting'; dc.className = 'chip warn'; }
    else if (door.fault) { dc.textContent = 'door problem'; dc.className = 'chip bad'; }
    else { dc.textContent = 'door: ' + (door.state || '?') + (door.moving ? ' (' + (door.moving === 'open' ? 'opening' : 'closing') + ')' : ''); dc.className = 'chip good'; }
    // the door panel
    $('mm').textContent = door.mm === null || door.mm === undefined ? '–' : String(door.mm);
    $('band').textContent = door.state === null ? 'door: not decided yet' : 'door reads: ' + door.state + (door.mm === null ? ' (no echo)' : ''); $('band').className = 'bandchip ' + (door.state || '');
    $('doorinfo').textContent = door.fault ? door.fault : (door.tamper ? 'TAMPER: the locked door was forced.' : 'The door is ' + (door.mode === 'moving' ? 'moving' : door.mode) + '.');
    if (door.settings.push_back !== undefined && door.settings.push_back !== lastPush) { $('pushBack').checked = !!door.settings.push_back; lastPush = door.settings.push_back; }
    // the settings of the code
    const p = L.policy;
    $('policy').textContent = p ? 'Code: ' + p.n_digits + ' different digits · live challenge: ' + (p.challenge_digits ? p.challenge_digits + ' digit(s) from ' + p.challenge_pool.join(', ') : 'off') + ' · ' + p.max_failures + ' wrong tries then a lockout of ' + p.lockout_seconds + ' s (longer each time) · the door locks again after ' + p.relock_seconds + ' s · tamper blocks finger entry for ' + p.tamper_lockout_s + ' s' : 'No code is set yet: choose one below.';
    renderLog(L.log || []);
  }
  let lastPush = null;

  function renderView(v) {
    if (v.jpg) { $('frame').src = 'data:image/jpeg;base64,' + v.jpg; $('nopic').style.display = 'none'; } else { $('nopic').style.display = ''; }
    if (v.crop) $('crop').src = 'data:image/jpeg;base64,' + v.crop;
    const r = v.roi, w = v.frame.w, h = v.frame.h, roi = $('roi');
    roi.style.left = (100 * r.x / w) + '%'; roi.style.top = (100 * r.y / h) + '%'; roi.style.width = (100 * r.side / w) + '%'; roi.style.height = (100 * r.side / h) + '%';
    $('roiSource').textContent = 'The square now: ' + v.roi_source + ' (x ' + r.x + ', y ' + r.y + ', side ' + r.side + ').';
    const c = v.camera, chip = $('camera');
    if (c.lost) { chip.textContent = 'camera lost: plug it in again'; chip.className = 'chip bad'; }
    else if (!c.ok) { chip.textContent = 'no camera found yet'; chip.className = 'chip warn'; }
    else { chip.textContent = 'camera: ' + (c.name || 'webcam') + (c.format ? ', ' + c.format : ''); chip.className = 'chip good'; }
    if (c.mode !== undefined && c.mode !== lastMode) { $('fmt').value = c.mode; lastMode = c.mode; }
    const has = !!v.probs;
    $('digit').textContent = has ? String(v.digit) : '–';
    $('conf').innerHTML = has ? 'sure to ' + Math.round(100 * v.probs[v.digit]) + '%' : '&nbsp;';
    const st = $('steady');
    if (!has) { st.textContent = '–'; st.className = 'chip'; }
    else if (v.stable !== null && v.stable !== undefined) { st.textContent = 'steady: ' + v.stable; st.className = 'chip good'; }
    else { st.textContent = 'not steady yet'; st.className = 'chip warn'; }
    bars.forEach((b, i) => { const p = has ? v.probs[i] : 0; b.fill.style.width = (100 * p) + '%'; b.pct.textContent = has ? Math.round(100 * p) + '%' : '–'; b.row.className = 'bar' + (has && i === v.digit ? ' top' : ''); });
    $('camfps').textContent = fmt(c.fps, 1); $('netfps').textContent = fmt(v.timing.fps, 1);
    $('sSpeed').textContent = fmt(c.fps, 1) + ' / ' + fmt(v.timing.fps, 1);
  }

  socket.on('connect', () => { $('conn').textContent = 'connected'; $('conn').className = 'chip good'; send({ action: 'refresh' }); });
  socket.on('disconnect', () => { $('conn').textContent = 'disconnected'; $('conn').className = 'chip bad'; });
  socket.on('notice', (n) => showNotice(n.level, n.text));
  socket.on('lock', renderLock);
  socket.on('view', renderView);
  socket.on('fulllog', (m) => { if (!m.rows || !m.rows.length) { showNotice('warn', 'The log is empty.'); return; } downloadRows(m.rows, 'lockbox_log_full.csv'); });
})();
