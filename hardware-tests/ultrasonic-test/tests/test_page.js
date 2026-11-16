// Tests for assets/index.html + assets/app.js in a simulated browser (jsdom).   npm install jsdom  &&  node test_page.js
// It renders the REAL payloads that python/main.py produces (state_samples.json, written by test_ultrasonic.py).
const { JSDOM, VirtualConsole } = require('jsdom');
const fs = require('fs');
const path = require('path');
const assets = path.join(__dirname, '..', 'assets');
let problems = 0;
function expect(label, cond, detail) { console.log('  ' + (cond ? 'ok  ' : 'FAIL') + ' ' + label + (detail !== undefined ? '   [' + detail + ']' : '')); if (!cond) problems++; }
const samplesFile = path.join(__dirname, 'state_samples.json');
if (!fs.existsSync(samplesFile)) { console.log('state_samples.json not found: run `python test_ultrasonic.py` first'); process.exit(1); }
const S = JSON.parse(fs.readFileSync(samplesFile, 'utf8'));

function makePage(opts) {
  opts = opts || {};
  const html = fs.readFileSync(path.join(assets, 'index.html'), 'utf8').replace(/<script[^>]*><\/script>/g, '');
  const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true, url: 'http://board.local:7000/', virtualConsole: new VirtualConsole() });
  const w = dom.window, handlers = {}, emitted = [], drawn = { lines: 0, moves: 0, texts: [] }, downloads = [];
  w.io = () => ({ on: (e, f) => { handlers[e] = f; }, emit: (e, d) => emitted.push([e, d]) });
  w.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, { get: (t, k) => (k === 'lineTo' ? () => { drawn.lines++; } : k === 'moveTo' ? () => { drawn.moves++; } : k === 'fillText' ? (s) => { drawn.texts.push(s); } : () => {}), set: () => true });
  w.HTMLAnchorElement.prototype.click = function () { downloads.push({ href: this.href, name: this.download }); };
  if (opts.supply) w.localStorage.setItem('ultra.supply', opts.supply);
  w.eval(fs.readFileSync(path.join(assets, 'app.js'), 'utf8'));
  const d = w.document, $ = (id) => d.getElementById(id);
  const click = (e) => e.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true }));
  const key = (target, code) => { const ev = new w.KeyboardEvent('keydown', { code, bubbles: true, cancelable: true }); target.dispatchEvent(ev); return ev; };
  const keyup = (target, code) => { const ev = new w.KeyboardEvent('keyup', { code, bubbles: true, cancelable: true }); target.dispatchEvent(ev); return ev; };
  const type = (e, v) => { e.value = v; e.dispatchEvent(new w.Event('input', { bubbles: true })); e.dispatchEvent(new w.Event('change', { bubbles: true })); };
  return { w, d, $, click, key, keyup, type, handlers, emitted, drawn, downloads };
}
const cmds = (p) => p.emitted.filter((e) => e[0] === 'cmd').map((e) => e[1]);
const captures = (p) => cmds(p).filter((c) => c.action === 'capture');

console.log('1. connecting');
let p = makePage(); p.handlers.connect();
expect('"connected" in green, and it asks the board for the state', p.$('conn').textContent === 'connected' && p.$('conn').className.includes('good') && JSON.stringify(cmds(p).pop()) === '{"action":"refresh"}');
p.handlers.disconnect();
expect('a dropped connection is shown in red', p.$('conn').textContent === 'disconnected' && p.$('conn').className.includes('bad'));

console.log('2. the live distance');
p = makePage(); p.handlers.state(S.no_data);
expect('with no data from the board: a dash, and a red "no data from the board" chip', p.$('mm').textContent === '–' && p.$('sensor').textContent.includes('no data') && p.$('sensor').className.includes('bad'));
p = makePage(); p.handlers.state(S.ok);
expect('with readings: 143 mm, 14.3 cm, raw 142 mm, 100% usable, and a green "sensor: OK"', p.$('mm').textContent === '143' && p.$('cm').textContent === '14.3 cm' && p.$('raw').textContent === '142 mm' && p.$('okpct').textContent === '100%' && p.$('sensor').textContent === 'sensor: OK' && p.$('sensor').className.includes('good'));
expect('the chart is drawn as a line through the history (%d line segments)', p.drawn.lines > 50 && p.drawn.moves >= 1, p.drawn.lines);
p = makePage(); p.handlers.state(S.no_echo);
expect('when the echo disappears: a dash, "raw reading: none", a red "no echo" chip, and the chart says there are no readings', p.$('mm').textContent === '–' && p.$('raw').textContent === 'none' && p.$('sensor').textContent === 'sensor: no echo' && p.$('sensor').className.includes('bad') && p.drawn.texts.includes('no readings yet'));

console.log('3. starting a capture');
p = makePage(); p.handlers.state(S.ok); p.click(p.$('capture'));
expect('the button asks the board for a capture with the label, the power supply and the length chosen', JSON.stringify(captures(p)) === '[{"action":"capture","label":"door closed","kind":"closed","supply":"3V3","seconds":5}]', JSON.stringify(captures(p)));
p = makePage(); p.handlers.state(S.ok); const ev = p.key(p.d.body, 'Space');
expect('the SPACE bar does exactly the same, and does not scroll the page', JSON.stringify(captures(p)) === '[{"action":"capture","label":"door closed","kind":"closed","supply":"3V3","seconds":5}]' && ev.defaultPrevented);
const other = p.key(p.d.body, 'KeyA');
expect('another key does nothing', captures(p).length === 1 && !other.defaultPrevented);
p = makePage(); p.handlers.state(S.ok); p.$('seconds').focus(); const typed = p.key(p.$('seconds'), 'Space');
expect('SPACE while typing in the seconds box does not start a capture (and is not blocked)', captures(p).length === 0 && !typed.defaultPrevented);
p.key(p.$('label'), 'Space'); p.key(p.$('supply'), 'Space'); p.key(p.$('custom'), 'Space');
expect('nor while choosing in a drop-down list or typing a label', captures(p).length === 0);
p = makePage(); p.handlers.state(S.ok); p.$('clear').focus(); const onClear = p.key(p.$('clear'), 'Space'); const up = p.keyup(p.$('clear'), 'Space');
expect('SPACE with the Clear button focused starts a capture, does NOT clear the table, and its key release cannot click the button', captures(p).length === 1 && cmds(p).filter((c) => c.action === 'clear').length === 0 && onClear.defaultPrevented && up.defaultPrevented);
p.click(p.$('capture')); p.click(p.$('clear'));
expect('clicking a button takes the focus off it, so a later SPACE cannot click it', p.d.activeElement !== p.$('clear') && p.d.activeElement !== p.$('capture'));
p = makePage(); p.handlers.state(S.capturing); p.key(p.d.body, 'Space'); p.click(p.$('capture'));
expect('while a capture is running SPACE and the button do nothing (no second capture)', captures(p).length === 0 && p.$('capture').disabled);
expect('and the page says what is being captured and how long is left: %s', p.$('progress').textContent.includes('door closed') && p.$('progress').textContent.includes('3V3') && /s left/.test(p.$('progress').textContent), p.$('progress').textContent);
p.handlers.state(S.ok);
expect('when the capture ends the button is available again and the message goes', !p.$('capture').disabled && p.$('progress').textContent === '');

console.log('4. the choices');
p = makePage(); p.handlers.state(S.ok); p.type(p.$('seconds'), '999'); p.click(p.$('capture'));
expect('a capture length of 999 is sent as 60 and shown as 60', captures(p)[0].seconds === 60 && p.$('seconds').value === '60');
p.type(p.$('seconds'), '0'); p.click(p.$('capture')); p.type(p.$('seconds'), 'abc'); p.click(p.$('capture'));
expect('0 and rubbish are sent as 1', captures(p)[1].seconds === 1 && captures(p)[2].seconds === 1);
p = makePage(); p.handlers.state(S.ok); p.type(p.$('supply'), '5V'); p.click(p.$('capture'));
expect('choosing 5V is sent as 5V', captures(p)[0].supply === '5V');
p = makePage({ supply: '5V' }); p.handlers.state(S.ok); p.click(p.$('capture'));
expect('the power supply chosen last time is remembered', captures(p)[0].supply === '5V');
p = makePage(); p.handlers.state(S.ok); p.type(p.$('label'), '__other');
expect('choosing "other…" shows a box to type in', !p.$('custom').hidden);
p.click(p.$('capture'));
expect('with nothing typed in it nothing is sent, and a warning says so', captures(p).length === 0 && p.$('notice').className.includes('warn') && p.$('notice').textContent.includes('Type what'));
p.type(p.$('custom'), 'door at 45 degrees'); p.click(p.$('capture'));
expect('with a label typed in, that label is sent', captures(p).length === 1 && captures(p)[0].label === 'door at 45 degrees');
p.type(p.$('label'), 'door closed'); expect('choosing a ready-made label hides the box again', p.$('custom').hidden);
expect('a typed label is sent with the kind "other"', captures(p)[0].kind === 'other');
p.type(p.$('label'), 'door fully open (nothing in front of the sensor)'); p.click(p.$('capture'));
expect('the "fully open" choice is sent with the kind "open" (so the verdict expects no echo)', captures(p)[1].kind === 'open' && captures(p)[1].label.startsWith('door fully open'));
p.type(p.$('label'), 'door pushed open about 3 cm'); p.click(p.$('capture'));
expect('a door pushed open a little is sent with the kind "ajar"', captures(p)[2].kind === 'ajar');
expect('"nothing in front" is no longer a separate choice (it is the same as a fully open door)', ![...p.$('label').options].some((o) => /nothing in front \(far wall\)/.test(o.text)) && [...p.$('label').options].filter((o) => o.dataset.kind === 'open').length === 1);

console.log('5. the table of captures');
p = makePage(); p.handlers.state(S.with_rows);
const trs = p.d.querySelectorAll('#rows tr');
expect('three captures give three rows, the newest first', trs.length === 3 && trs[0].children[1].textContent.includes('fully open') && trs[1].children[1].textContent.includes('door open') && trs[2].children[1].textContent === 'door closed');
expect('a label with HTML in it is shown as text, never as HTML (nothing is injected)', p.d.querySelectorAll('#rows b').length === 0 && trs[1].children[1].textContent === 'door open <b>x</b>');
expect('the verdict colours: GOOD green, BAD red, and NOTHING IN VIEW (its own colour, not red) for a fully open door that sees nothing', trs[2].children[9].className === 'v-GOOD' && trs[1].children[9].className === 'v-BAD' && trs[0].children[9].className === 'v-NOTHING', trs.length ? trs[0].children[9].className + ' / ' + trs[1].children[9].className + ' / ' + trs[2].children[9].className : '');
expect('a capture with no usable readings shows dashes, not zeros', trs[1].children[5].textContent === '–' && trs[1].children[8].textContent === '–' && trs[1].children[7].textContent === '– to –', trs[1].children[5].textContent);
expect('the numbers are shown: how many readings were usable, the average, the range', /^90 of 90 \(100(\.0)?%\)$/.test(trs[2].children[4].textContent) && trs[2].children[5].textContent === '143' && trs[2].children[7].textContent === '143 to 143', trs[2].children[4].textContent + ' | ' + trs[2].children[5].textContent + ' | ' + trs[2].children[7].textContent);
p.click(p.$('clear'));
expect('Clear asks the board to clear the table', JSON.stringify(cmds(p).pop()) === '{"action":"clear"}');

console.log('6. downloading the captures');
p = makePage(); p.handlers.state(S.with_rows); p.click(p.$('csv'));
const csv = p.downloads.length ? decodeURIComponent(p.downloads[0].href.replace('data:text/csv;charset=utf-8,', '')) : '';
expect('a CSV file is offered, with the header and one line per capture', p.downloads.length === 1 && p.downloads[0].name === 'ultrasonic_captures.csv' && csv.split('\n')[0] === 'time,label,kind,supply,seconds,n,valid,valid_pct,mean_mm,median_mm,min_mm,max_mm,std_mm,verdict' && csv.trim().split('\n').length === 4, csv.split('\n')[0]);
p = makePage(); const tricky = JSON.parse(JSON.stringify(S.with_rows)); tricky.rows[0].label = 'a, "b"'; p.handlers.state(tricky); p.click(p.$('csv'));
const csv2 = decodeURIComponent(p.downloads[0].href.replace('data:text/csv;charset=utf-8,', ''));
expect('a label with a comma and a quote is written safely: "a, ""b"""', csv2.includes('"a, ""b"""'));
p = makePage(); p.handlers.state(S.ok); p.click(p.$('csv'));
expect('with no captures nothing is downloaded, and a warning says so', p.downloads.length === 0 && p.$('notice').textContent.includes('Nothing to download'));

console.log('7. messages from the board');
p = makePage(); p.handlers.notice({ level: 'ok', text: 'Capture finished. GOOD: steady.' });
expect('a notice is shown with its colour', p.$('notice').textContent === 'Capture finished. GOOD: steady.' && p.$('notice').className.includes('ok'));
p.handlers.notice({ level: 'warn', text: 'A capture is already running: wait until it finishes.' });
expect('a warning replaces it', p.$('notice').className.includes('warn') && p.$('notice').textContent.includes('already running'));

console.log('\n' + (problems === 0 ? 'ALL PASSED' : problems + ' CHECK(S) FAILED'));
process.exit(problems ? 1 : 0);
