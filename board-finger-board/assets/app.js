// Finger count on the board: the live page. Talks to main.py through socket.io: it sends 'cmd' and receives 'view', 'bench' and 'notice'.
(function () {
  const socket = io(window.location.origin);
  const $ = (id) => document.getElementById(id);
  const BENCH_COLUMNS = ['time', 'what', 'frame', 'n', 'prep_median_ms', 'infer_median_ms', 'infer_p95_ms', 'infer_max_ms', 'total_median_ms', 'fps_estimate', 'machine', 'python', 'numpy', 'opencv'];
  let benchRows = [], benchmarking = false, lastMode = null, paused = false;
  const send = (o) => socket.emit('cmd', o);
  const fmt = (v, d) => (v === null || v === undefined ? '–' : (typeof v === 'number' && d !== undefined ? v.toFixed(d) : String(v)));
  function showNotice(level, text) { const el = $('notice'); el.className = 'notice ' + (level || 'info'); el.textContent = text; }

  // the six probability bars
  const bars = [];
  for (let i = 0; i < 6; i++) {
    const row = document.createElement('div'); row.className = 'bar';
    const n = document.createElement('span'); n.textContent = String(i);
    const track = document.createElement('div'); track.className = 'track'; const fill = document.createElement('div'); fill.className = 'fill'; track.appendChild(fill);
    const pct = document.createElement('span'); pct.textContent = '–';
    row.appendChild(n); row.appendChild(track); row.appendChild(pct); $('bars').appendChild(row); bars.push({ row, fill, pct });
  }

  const nudge = (dx, dy, ds) => send({ action: 'nudge', dx: dx, dy: dy, ds: ds });
  const step = 4;
  [['left', -step, 0, 0], ['right', step, 0, 0], ['up', 0, -step, 0], ['down', 0, step, 0], ['smaller', 0, 0, -step], ['bigger', 0, 0, step]].forEach((b) => {
    $(b[0]).addEventListener('click', (e) => { nudge(b[1], b[2], b[3]); e.currentTarget.blur(); });
  });
  $('find').addEventListener('click', (e) => { send({ action: 'find_tape', color: $('color').value }); e.currentTarget.blur(); });
  $('save').addEventListener('click', (e) => { send({ action: 'save_roi' }); e.currentTarget.blur(); });
  $('reset').addEventListener('click', (e) => { send({ action: 'reset_roi' }); e.currentTarget.blur(); });
  $('pauseBtn').addEventListener('click', (e) => { send({ action: 'pause', paused: !paused }); e.currentTarget.blur(); });
  $('applyFmt').addEventListener('click', (e) => { send({ action: 'camera_mode', fourcc: $('fmt').value }); e.currentTarget.blur(); });
  $('bench').addEventListener('click', (e) => { if (!benchmarking) send({ action: 'benchmark' }); e.currentTarget.blur(); });
  $('csv').addEventListener('click', (e) => {
    e.currentTarget.blur();
    if (!benchRows.length) { showNotice('warn', 'Nothing to download yet: press Benchmark first.'); return; }
    const cell = (v) => { const s = v === null || v === undefined ? '' : String(v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
    const text = [BENCH_COLUMNS.join(',')].concat(benchRows.map((r) => BENCH_COLUMNS.map((c) => cell(r[c])).join(','))).join('\n') + '\n';
    const a = document.createElement('a');
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(text); a.download = 'board_speed.csv';
    document.body.appendChild(a); a.click(); a.remove();
  });

  // The arrow keys move the square and + and - resize it (Shift = bigger steps). Not while a drop-down or box has the keyboard.
  document.addEventListener('keydown', (e) => {
    const t = e.target && e.target.tagName;
    if (t === 'INPUT' || t === 'SELECT' || t === 'TEXTAREA') return;
    const big = e.shiftKey ? 4 : 1, d = step * big;
    const moves = { ArrowLeft: [-d, 0, 0], ArrowRight: [d, 0, 0], ArrowUp: [0, -d, 0], ArrowDown: [0, d, 0], '+': [0, 0, d], '=': [0, 0, d], '-': [0, 0, -d], '_': [0, 0, -d] };
    const m = moves[e.key];
    if (!m) return;
    e.preventDefault();
    nudge(m[0], m[1], m[2]);
  });
  document.addEventListener('keyup', (e) => { if ((e.key === ' ' || e.code === 'Space') && e.target && e.target.tagName === 'BUTTON') e.preventDefault(); });

  function renderBench(rows) {
    benchRows = rows || [];
    const body = $('benchRows'); body.textContent = '';
    benchRows.slice().reverse().forEach((r) => {
      const tr = document.createElement('tr');
      [r.time, r.what, r.frame, fmt(r.total_median_ms), fmt(r.prep_median_ms), fmt(r.infer_median_ms), fmt(r.infer_p95_ms), fmt(r.infer_max_ms), fmt(r.fps_estimate), r.machine, r.python].forEach((text) => {
        const td = document.createElement('td'); td.textContent = text === undefined ? '–' : String(text); tr.appendChild(td);
      });
      body.appendChild(tr);
    });
  }

  function render(v) {
    // the picture and the square drawn over it
    if (v.jpg) { $('frame').src = 'data:image/jpeg;base64,' + v.jpg; $('nopic').style.display = 'none'; } else { $('nopic').style.display = ''; }
    if (v.crop) $('crop').src = 'data:image/jpeg;base64,' + v.crop;
    const r = v.roi, w = v.frame.w, h = v.frame.h, roi = $('roi');
    roi.style.left = (100 * r.x / w) + '%'; roi.style.top = (100 * r.y / h) + '%'; roi.style.width = (100 * r.side / w) + '%'; roi.style.height = (100 * r.side / h) + '%';
    $('roiSource').textContent = 'The square now: ' + v.roi_source + ' (x ' + r.x + ', y ' + r.y + ', side ' + r.side + ').';
    // the camera
    const c = v.camera, chip = $('camera');
    if (c.lost) { chip.textContent = 'camera lost: plug it in again'; chip.className = 'chip bad'; }
    else if (!c.ok) { chip.textContent = 'no camera found yet (looking every 5 seconds)'; chip.className = 'chip warn'; }
    else { chip.textContent = 'camera: ' + (c.name || 'webcam') + ' (' + c.path + ')' + (c.format ? ', ' + c.format : ''); chip.className = 'chip good'; }
    if (c.mode !== undefined && c.mode !== lastMode) { $('fmt').value = c.mode; lastMode = c.mode; }          // follow the board's setting, but never overwrite a choice you are making
    $('fmtNote').textContent = c.format ? 'The camera reports: ' + c.format + '.' : '';
    // the answer
    const has = !!v.probs;
    $('digit').textContent = has ? String(v.digit) : '–';
    $('conf').innerHTML = has ? 'sure to ' + Math.round(100 * v.probs[v.digit]) + '%' : '&nbsp;';
    const st = $('steady');
    if (!has) { st.textContent = 'steady answer: –'; st.className = 'chip'; }
    else if (v.stable !== null && v.stable !== undefined) { st.textContent = 'steady answer: ' + v.stable; st.className = 'chip good'; }
    else { st.textContent = 'not steady yet'; st.className = 'chip warn'; }
    bars.forEach((b, i) => {
      const p = has ? v.probs[i] : 0;
      b.fill.style.width = (100 * p) + '%'; b.pct.textContent = has ? Math.round(100 * p) + '%' : '–';
      b.row.className = 'bar' + (has && i === v.digit ? ' top' : '');
    });
    // the speed
    const t = v.timing;
    $('fps').textContent = fmt(t.fps, 1); $('camfps').textContent = fmt(c.fps, 1); $('prep').textContent = fmt(t.prep_ms, 1); $('infer').textContent = fmt(t.infer_ms, 1); $('age').textContent = fmt(t.age_ms, 0);
    paused = !!v.paused;
    $('pauseBtn').textContent = paused ? 'Resume the network' : 'Pause the network';
    $('pauseNote').textContent = paused ? 'The network is PAUSED: the "camera pictures per second" is the camera\'s own speed. Watch it for 10 seconds, then resume.' : 'Pausing stops the network but not the camera, so "camera pictures per second" then shows what the camera can do by itself.';
    benchmarking = !!v.benchmarking;
    $('bench').disabled = benchmarking; $('bench').textContent = benchmarking ? 'Measuring…' : 'Benchmark (about 5 seconds)';
  }

  socket.on('connect', () => { $('conn').textContent = 'connected'; $('conn').className = 'chip good'; send({ action: 'refresh' }); });
  socket.on('disconnect', () => { $('conn').textContent = 'disconnected'; $('conn').className = 'chip bad'; });
  socket.on('notice', (n) => showNotice(n.level, n.text));
  socket.on('view', render);
  socket.on('bench', (b) => renderBench(b.rows));
})();
