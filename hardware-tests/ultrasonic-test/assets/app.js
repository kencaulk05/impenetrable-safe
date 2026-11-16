// Ultrasonic sensor test: the live page. Talks to main.py through socket.io: it sends 'cmd' and receives 'state' and 'notice'.
(function () {
  const socket = io(window.location.origin);
  const $ = (id) => document.getElementById(id);
  const store = {
    get(k, d) { try { const v = window.localStorage.getItem('ultra.' + k); return v === null ? d : v; } catch (e) { return d; } },
    set(k, v) { try { window.localStorage.setItem('ultra.' + k, v); } catch (e) { /* private mode: just do not remember */ } }
  };
  const COLUMNS = ['time', 'label', 'kind', 'supply', 'seconds', 'n', 'valid', 'valid_pct', 'mean_mm', 'median_mm', 'min_mm', 'max_mm', 'std_mm', 'verdict'];
  let capturing = false, lastState = null;

  // remember what was chosen last time
  const supply = store.get('supply', '3V3'); if (supply === '3V3' || supply === '5V') $('supply').value = supply;
  const label = store.get('label', ''); if (label) { for (const o of $('label').options) if (o.value === label || o.text === label) $('label').value = o.value || o.text; }
  $('supply').addEventListener('change', () => store.set('supply', $('supply').value));
  $('label').addEventListener('change', () => { store.set('label', $('label').value); $('custom').hidden = $('label').value !== '__other'; });
  $('custom').hidden = $('label').value !== '__other';

  function showNotice(level, text) { const el = $('notice'); el.className = 'notice ' + (level || 'info'); el.textContent = text; }
  const fmt = (v) => (v === null || v === undefined ? '–' : String(v));

  function capture() {
    if (capturing) return;
    let what = $('label').value;
    const opt = $('label').options[$('label').selectedIndex];
    const kind = (opt && opt.dataset && opt.dataset.kind) || 'other';
    if (what === '__other') { what = $('custom').value.trim(); if (!what) { showNotice('warn', 'Type what the sensor is looking at.'); return; } }
    let secs = parseInt($('seconds').value, 10);
    if (!Number.isFinite(secs) || secs < 1) secs = 1;
    if (secs > 60) secs = 60;
    $('seconds').value = secs;
    socket.emit('cmd', { action: 'capture', label: what, kind: kind, supply: $('supply').value, seconds: secs });
  }

  $('capture').addEventListener('click', (e) => { capture(); e.currentTarget.blur(); });
  $('clear').addEventListener('click', (e) => { socket.emit('cmd', { action: 'clear' }); e.currentTarget.blur(); });
  $('csv').addEventListener('click', (e) => {
    e.currentTarget.blur();
    const rows = lastState ? lastState.rows : [];
    if (!rows.length) { showNotice('warn', 'Nothing to download yet: capture something first.'); return; }
    const a = document.createElement('a');
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(toCsv(rows));
    a.download = 'ultrasonic_captures.csv';
    document.body.appendChild(a); a.click(); a.remove();
  });

  // The SPACE bar starts a capture, unless the person is typing or choosing in a field. It must never "click" a focused button (such as Clear).
  document.addEventListener('keydown', (e) => {
    if (e.code !== 'Space') return;
    const t = e.target && e.target.tagName;
    if (t === 'INPUT' || t === 'SELECT' || t === 'TEXTAREA') return;
    e.preventDefault();
    capture();
  });
  document.addEventListener('keyup', (e) => { if (e.code === 'Space' && e.target && e.target.tagName === 'BUTTON') e.preventDefault(); });

  function csvCell(v) { const s = v === null || v === undefined ? '' : String(v); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }
  function toCsv(rows) { return [COLUMNS.join(',')].concat(rows.map((r) => COLUMNS.map((c) => csvCell(r[c])).join(','))).join('\n') + '\n'; }

  function drawChart(hist) {
    const c = $('chart'); const ctx = c.getContext && c.getContext('2d');
    if (!ctx) return;
    const W = c.width, H = c.height, padL = 52, padB = 18, padT = 8;
    ctx.clearRect(0, 0, W, H);
    const vals = hist.filter((p) => p[1] !== null).map((p) => p[1]);
    ctx.font = '12px sans-serif'; ctx.fillStyle = '#5b6575'; ctx.strokeStyle = '#2f6fdb'; ctx.lineWidth = 2;
    if (!vals.length) { ctx.fillText('no readings yet', W / 2 - 40, H / 2); return; }
    let lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    if (hi - lo < 20) { const mid = (hi + lo) / 2; lo = mid - 10; hi = mid + 10; }
    const x = (t) => padL + ((t + 15) / 15) * (W - padL - 6);
    const y = (v) => padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB);
    ctx.fillText(Math.round(hi) + ' mm', 4, padT + 10); ctx.fillText(Math.round(lo) + ' mm', 4, H - padB);
    ctx.beginPath();
    let pen = false;
    hist.forEach((p) => { if (p[1] === null) { pen = false; return; } if (!pen) { ctx.moveTo(x(p[0]), y(p[1])); pen = true; } else ctx.lineTo(x(p[0]), y(p[1])); });
    ctx.stroke();
  }

  function renderRows(rows) {
    const body = $('rows'); body.textContent = '';
    rows.slice().reverse().forEach((r) => {
      const tr = document.createElement('tr');
      const cells = [r.time, r.label, r.supply, r.seconds + ' s', r.valid + ' of ' + r.n + ' (' + r.valid_pct + '%)', fmt(r.mean_mm), fmt(r.median_mm), fmt(r.min_mm) + ' to ' + fmt(r.max_mm), fmt(r.std_mm), r.verdict];
      cells.forEach((text, i) => {
        const td = document.createElement('td'); td.textContent = text;
        if (i === cells.length - 1) td.className = 'v-' + String(r.verdict).split(/[: ]/)[0];
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
  }

  function render(s) {
    lastState = s;
    $('mm').textContent = s.mm === null || s.mm === undefined ? '–' : String(s.mm);
    $('cm').textContent = s.mm === null || s.mm === undefined ? '' : (s.mm / 10).toFixed(1) + ' cm';
    $('raw').textContent = s.raw === null || s.raw === undefined ? 'none' : s.raw + ' mm';
    $('okpct').textContent = s.ok_pct === null || s.ok_pct === undefined ? '–' : s.ok_pct + '%';
    const chip = $('sensor');
    if (s.age_s === null || s.age_s === undefined || s.age_s > 2) { chip.textContent = 'sensor: no data from the board'; chip.className = 'chip bad'; }
    else if (s.mm === null && s.raw === null) { chip.textContent = 'sensor: no echo'; chip.className = 'chip bad'; }
    else if (s.mm === null) { chip.textContent = 'sensor: settling'; chip.className = 'chip warn'; }
    else { chip.textContent = 'sensor: OK'; chip.className = 'chip good'; }
    drawChart(s.history || []);
    capturing = !!s.capturing;
    $('capture').disabled = capturing;
    $('progress').textContent = capturing ? 'Capturing "' + s.capturing.label + '" (' + s.capturing.supply + '): ' + s.capturing.remaining_s + ' s left. Keep everything still.' : '';
    renderRows(s.rows || []);
  }

  socket.on('connect', () => { $('conn').textContent = 'connected'; $('conn').className = 'chip good'; socket.emit('cmd', { action: 'refresh' }); });
  socket.on('disconnect', () => { $('conn').textContent = 'disconnected'; $('conn').className = 'chip bad'; });
  socket.on('notice', (n) => showNotice(n.level, n.text));
  socket.on('state', render);
})();
