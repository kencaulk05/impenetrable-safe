// Motor test: the live page. Talks to main.py through socket.io: it sends 'cmd' and receives 'state' and 'notice'.
(function () {
  const socket = io(window.location.origin);
  const $ = (id) => document.getElementById(id);
  const COLUMNS = ['id', 'time', 'action', 'dir', 'ms', 'pwm', 'ramp_ms', 'confirmed', 'outcome'];
  let running = false, settingsLoaded = false, lastState = null, lastMoves = null, outcomes = [];

  const clampInt = (v, lo, hi, fallback) => { const n = parseInt(v, 10); return Number.isFinite(n) ? Math.max(lo, Math.min(hi, n)) : fallback; };
  // The page is the source of truth for the settings (it sends them with every move); the board's copy is only used to fill the boxes when the page opens.
  function settings() {
    const s = lastState ? lastState.settings : { pwm: 150, ramp_ms: 250, open_ms: 600, close_ms: 600, open_dir: 1 };
    const out = {
      pwm: clampInt($('pwm').value, 60, 255, s.pwm), ramp_ms: clampInt($('ramp').value, 0, 1000, s.ramp_ms),
      open_ms: clampInt($('openMs').value, 50, 3000, s.open_ms), close_ms: clampInt($('closeMs').value, 50, 3000, s.close_ms), open_dir: $('swap').checked ? -1 : 1
    };
    $('pwm').value = out.pwm; $('ramp').value = out.ramp_ms; $('openMs').value = out.open_ms; $('closeMs').value = out.close_ms;
    $('pwmVal').textContent = out.pwm; $('rampVal').textContent = out.ramp_ms;
    return out;
  }
  function showNotice(level, text) { const el = $('notice'); el.className = 'notice ' + (level || 'info'); el.textContent = text; }
  const send = (o) => socket.emit('cmd', o);

  const stop = () => send({ action: 'stop' });
  const next = () => { if (running) return; send({ action: 'next', settings: settings() }); };
  const move = (which) => { if (running) return; send({ action: 'move', which: which, settings: settings() }); };

  $('nextBtn').addEventListener('click', (e) => { next(); e.currentTarget.blur(); });
  $('openBtn').addEventListener('click', (e) => { move('open'); e.currentTarget.blur(); });
  $('closeBtn').addEventListener('click', (e) => { move('close'); e.currentTarget.blur(); });
  $('stopBtn').addEventListener('click', (e) => { stop(); e.currentTarget.blur(); });
  $('isClosed').addEventListener('click', (e) => { send({ action: 'set_door', door: 'closed' }); e.currentTarget.blur(); });
  $('isOpen').addEventListener('click', (e) => { send({ action: 'set_door', door: 'open' }); e.currentTarget.blur(); });
  $('clear').addEventListener('click', (e) => { send({ action: 'clear' }); e.currentTarget.blur(); });
  $('pwm').addEventListener('input', () => { $('pwmVal').textContent = $('pwm').value; });
  $('ramp').addEventListener('input', () => { $('rampVal').textContent = $('ramp').value; });
  $('csv').addEventListener('click', (e) => {
    e.currentTarget.blur();
    const rows = lastState ? lastState.moves : [];
    if (!rows.length) { showNotice('warn', 'Nothing to download yet: make a move first.'); return; }
    const a = document.createElement('a');
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(toCsv(rows));
    a.download = 'motor_moves.csv';
    document.body.appendChild(a); a.click(); a.remove();
  });

  // ESC always stops the motor. SPACE starts the next move, and stops the motor if it is already moving. SPACE does nothing while the person is typing or choosing in a field,
  // and it must never "click" a focused button.
  document.addEventListener('keydown', (e) => {
    if (e.code === 'Escape' || e.key === 'Escape') { e.preventDefault(); stop(); return; }
    if (e.code !== 'Space') return;
    const t = e.target && e.target.tagName;
    if (t === 'INPUT' || t === 'SELECT' || t === 'TEXTAREA') return;
    e.preventDefault();
    if (running) stop(); else next();
  });
  document.addEventListener('keyup', (e) => { if (e.code === 'Space' && e.target && e.target.tagName === 'BUTTON') e.preventDefault(); });

  function csvCell(v) { const s = v === null || v === undefined ? '' : String(v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }
  function toCsv(rows) { return [COLUMNS.join(',')].concat(rows.map((r) => COLUMNS.map((c) => csvCell(r[c])).join(','))).join('\n') + '\n'; }

  function renderMoves(moves) {
    const key = JSON.stringify(moves);
    if (key === lastMoves) return;                       // do not rebuild the table (and close a drop-down someone is using) when nothing changed
    lastMoves = key;
    const body = $('rows'); body.textContent = '';
    moves.slice().reverse().forEach((r) => {
      const tr = document.createElement('tr');
      const conf = r.confirmed === true ? 'yes' : (r.confirmed === false ? 'NOT CONFIRMED' : 'waiting…');
      [r.id, r.time, r.action, (r.dir > 0 ? '+1' : '-1'), r.ms, r.pwm, r.ramp_ms, conf].forEach((text, i) => {
        const td = document.createElement('td'); td.textContent = text;
        if (i === 7) td.className = r.confirmed === false ? 'bad' : (r.confirmed === true ? 'ok' : '');
        tr.appendChild(td);
      });
      const td = document.createElement('td'), sel = document.createElement('select');
      [''].concat(outcomes).forEach((o) => { const op = document.createElement('option'); op.value = o; op.textContent = o === '' ? '(rate it)' : o; sel.appendChild(op); });
      sel.value = r.outcome || '';
      sel.addEventListener('change', () => send({ action: 'rate', id: r.id, outcome: sel.value }));
      td.appendChild(sel); tr.appendChild(td); body.appendChild(tr);
    });
  }

  function render(s) {
    lastState = s;
    running = !!s.running;
    outcomes = s.outcomes || outcomes;
    if (!settingsLoaded) {                               // fill the boxes once, from what the board remembered
      settingsLoaded = true;
      $('pwm').value = s.settings.pwm; $('ramp').value = s.settings.ramp_ms; $('openMs').value = s.settings.open_ms; $('closeMs').value = s.settings.close_ms; $('swap').checked = s.settings.open_dir < 0;
      $('pwmVal').textContent = s.settings.pwm; $('rampVal').textContent = s.settings.ramp_ms;
    }
    $('door').textContent = s.door; $('next').textContent = s.next;
    $('remaining').textContent = running ? s.remaining_ms + ' ms left' : '';
    const chip = $('motor');
    if (running) { chip.textContent = 'motor: running ' + (s.run_dir > 0 ? '→ (+1)' : '← (-1)'); chip.className = 'chip run'; }
    else { chip.textContent = 'motor: stopped'; chip.className = 'chip good'; }
    $('nextBtn').disabled = running; $('openBtn').disabled = running; $('closeBtn').disabled = running;
    renderMoves(s.moves || []);
  }

  socket.on('connect', () => { $('conn').textContent = 'connected'; $('conn').className = 'chip good'; send({ action: 'refresh' }); });
  socket.on('disconnect', () => { $('conn').textContent = 'disconnected'; $('conn').className = 'chip bad'; });
  socket.on('notice', (n) => showNotice(n.level, n.text));
  socket.on('state', render);
})();
