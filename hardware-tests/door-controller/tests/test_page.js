// Tests for assets/index.html + assets/app.js in a simulated browser (jsdom).   npm install jsdom  &&  node test_page.js
// It renders the REAL payloads that python/main.py produces (state_samples.json, written by test_door.py).
const { JSDOM, VirtualConsole } = require('jsdom');
const fs = require('fs');
const path = require('path');
const assets = path.join(__dirname, '..', 'assets');
let problems = 0;
function expect(label, cond, detail) { console.log('  ' + (cond ? 'ok  ' : 'FAIL') + ' ' + label + (detail !== undefined ? '   [' + detail + ']' : '')); if (!cond) problems++; }
const samplesFile = path.join(__dirname, 'state_samples.json');
if (!fs.existsSync(samplesFile)) { console.log('state_samples.json not found: run `python test_door.py` first'); process.exit(1); }
const S = JSON.parse(fs.readFileSync(samplesFile, 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));

function makePage() {
  const html = fs.readFileSync(path.join(assets, 'index.html'), 'utf8').replace(/<script[^>]*><\/script>/g, '');
  const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true, url: 'http://board.local:7000/', virtualConsole: new VirtualConsole() });
  const w = dom.window, handlers = {}, emitted = [], downloads = [], drawn = { lines: 0, rects: 0, texts: [] };
  w.io = () => ({ on: (e, f) => { handlers[e] = f; }, emit: (e, d) => emitted.push([e, d]) });
  w.HTMLCanvasElement.prototype.getContext = () => new Proxy({}, { get: (t, k) => (k === 'lineTo' ? () => { drawn.lines++; } : k === 'fillRect' ? () => { drawn.rects++; } : k === 'fillText' ? (s) => { drawn.texts.push(s); } : () => {}), set: () => true });
  w.HTMLAnchorElement.prototype.click = function () { downloads.push({ href: this.href, name: this.download }); };
  w.eval(fs.readFileSync(path.join(assets, 'app.js'), 'utf8'));
  const d = w.document, $ = (id) => d.getElementById(id);
  const click = (e) => e.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true }));
  const key = (target, code) => { const ev = new w.KeyboardEvent('keydown', { code, key: code === 'Escape' ? 'Escape' : (code === 'Space' ? ' ' : code), bubbles: true, cancelable: true }); target.dispatchEvent(ev); return ev; };
  const keyup = (target, code) => { const ev = new w.KeyboardEvent('keyup', { code, bubbles: true, cancelable: true }); target.dispatchEvent(ev); return ev; };
  const type = (e, v) => { e.value = v; e.dispatchEvent(new w.Event('input', { bubbles: true })); e.dispatchEvent(new w.Event('change', { bubbles: true })); };
  return { w, d, $, click, key, keyup, type, handlers, emitted, drawn, downloads };
}
const cmds = (p) => p.emitted.filter((e) => e[0] === 'cmd').map((e) => e[1]);
const lastCmd = (p) => cmds(p).pop();

console.log('1. connecting');
let p = makePage(); p.handlers.connect();
expect('"connected" in green, and it asks the board for the state', p.$('conn').textContent === 'connected' && p.$('conn').className.includes('good') && JSON.stringify(lastCmd(p)) === '{"action":"refresh"}');
p.handlers.disconnect(); expect('a dropped connection is shown in red', p.$('conn').textContent === 'disconnected' && p.$('conn').className.includes('bad'));

console.log('2. what the door is doing');
p = makePage(); p.handlers.state(S.waiting);
expect('before the sensor has said anything: "WAITING FOR THE SENSOR" and a yellow chip', p.$('headline').textContent === 'WAITING FOR THE SENSOR' && p.$('sensor').textContent === 'sensor: waiting for readings' && p.$('sensor').className.includes('warn') && p.$('mm').textContent === '–');
p = makePage(); p.handlers.state(S.locked);
expect('a closed door: LOCKED in green, 106 mm, "door reads: closed", a green sensor chip', p.$('headline').textContent === 'LOCKED' && p.$('headline').className.includes('locked') && p.$('mm').textContent === '106' && p.$('band').textContent === 'door reads: closed' && p.$('sensor').textContent === 'sensor: OK' && p.$('sensor').className.includes('good'));
expect('the main button offers to OPEN a closed door, and the buttons are available', p.$('toggleBtn').textContent === 'Open the door (Space bar)' && !p.$('toggleBtn').disabled && !p.$('openBtn').disabled && !p.$('closeBtn').disabled && !p.$('calBtn').disabled && !p.$('stopBtn').disabled);
expect('the chart is drawn: a line through the history, the shaded closed band, and labels for the band and the open limit', p.drawn.lines > 10 && p.drawn.rects >= 1 && p.drawn.texts.includes('116 mm') && p.drawn.texts.includes('96 mm') && p.drawn.texts.includes('open 250'), p.drawn.lines + ' segments, texts ' + p.drawn.texts.join(' | '));
p = makePage(); p.handlers.state(S.moving);
expect('while it moves: "MOVING: opening" in blue, and Open, Close, the main button and Calibrate are switched off, but STOP is not', p.$('headline').textContent === 'MOVING: opening' && p.$('headline').className.includes('moving') && p.$('toggleBtn').disabled && p.$('openBtn').disabled && p.$('closeBtn').disabled && p.$('calBtn').disabled && !p.$('stopBtn').disabled);
p = makePage(); p.handlers.state(S.unlocked);
expect('an open door (no echo): UNLOCKED, a dash for the distance, "door reads: open (no echo)", and the main button offers to CLOSE it', p.$('headline').textContent === 'UNLOCKED' && p.$('mm').textContent === '–' && p.$('band').textContent === 'door reads: open (no echo)' && p.$('toggleBtn').textContent === 'Close the door (Space bar)');
p = makePage(); p.handlers.state(S.tamper);
expect('a forced door: TAMPER in red, blinking', p.$('headline').textContent === 'TAMPER' && p.$('headline').className.includes('tamper') && p.$('band').textContent === 'door reads: ajar');
p = makePage(); p.handlers.state(S.fault);
expect('a move that did not work: FAULT, with what happened', p.$('headline').textContent === 'FAULT' && p.$('sub').textContent.includes('did not open'), p.$('sub').textContent);
p = makePage(); p.handlers.state(S.lost);
expect('a sensor that went quiet: SENSOR LOST and a red chip', p.$('headline').textContent === 'SENSOR LOST' && p.$('sensor').textContent === 'sensor: lost' && p.$('sensor').className.includes('bad'));

console.log('3. the buttons');
p = makePage(); p.handlers.state(S.locked);
p.click(p.$('toggleBtn')); expect('the main button sends "toggle"', JSON.stringify(lastCmd(p)) === '{"action":"toggle"}');
p.click(p.$('openBtn')); expect('Open sends "open"', JSON.stringify(lastCmd(p)) === '{"action":"open"}');
p.click(p.$('closeBtn')); expect('Close sends "close"', JSON.stringify(lastCmd(p)) === '{"action":"close"}');
p.click(p.$('calBtn')); expect('Calibrate sends "calibrate"', JSON.stringify(lastCmd(p)) === '{"action":"calibrate"}');
p.click(p.$('stopBtn')); expect('STOP sends "stop"', JSON.stringify(lastCmd(p)) === '{"action":"stop"}');
p.click(p.$('toggleBtn')); expect('clicking a button takes the focus off it, so a later SPACE cannot click it', p.d.activeElement !== p.$('toggleBtn') && p.d.activeElement !== p.$('stopBtn'));
p = makePage(); p.handlers.state(S.moving); p.click(p.$('toggleBtn')); p.click(p.$('openBtn')); p.click(p.$('closeBtn')); p.click(p.$('calBtn'));
expect('while it moves the move buttons and Calibrate send nothing', cmds(p).length === 0); p.click(p.$('stopBtn')); expect('but STOP still does', JSON.stringify(lastCmd(p)) === '{"action":"stop"}');

console.log('4. the keyboard (the Space bar is the push-button, Esc is the emergency stop)');
p = makePage(); p.handlers.state(S.locked); const ev = p.key(p.d.body, 'Space');
expect('SPACE with the door at rest is the push-button ("toggle"), and does not scroll the page', JSON.stringify(cmds(p)) === '[{"action":"toggle"}]' && ev.defaultPrevented);
p = makePage(); p.handlers.state(S.moving); p.key(p.d.body, 'Space'); expect('SPACE while the door moves STOPS it (and does not ask for another move)', JSON.stringify(cmds(p)) === '[{"action":"stop"}]');
p = makePage(); p.handlers.state(S.locked); p.key(p.d.body, 'Escape'); expect('ESC stops the motor', JSON.stringify(cmds(p)) === '[{"action":"stop"}]');
p = makePage(); p.handlers.state(S.moving); p.$('openMs').focus(); p.key(p.$('openMs'), 'Escape'); expect('ESC stops it even while the cursor is in a settings box', JSON.stringify(cmds(p)) === '[{"action":"stop"}]');
p = makePage(); p.handlers.state(S.locked); p.$('openMs').focus(); const typed = p.key(p.$('openMs'), 'Space'); p.key(p.$('openDir'), 'Space'); p.key(p.$('pushBack'), 'Space');
expect('SPACE while typing in a settings box, choosing in the direction list, or on the push-back box does nothing, and is not blocked', cmds(p).length === 0 && !typed.defaultPrevented);
p = makePage(); p.handlers.state(S.locked); p.$('evClear').focus(); const onBtn = p.key(p.$('evClear'), 'Space'); const up = p.keyup(p.$('evClear'), 'Space');
expect('SPACE with the "Clear the list" button focused is the push-button, does NOT clear the list, and the key release cannot click the button', JSON.stringify(cmds(p)) === '[{"action":"toggle"}]' && onBtn.defaultPrevented && up.defaultPrevented);
p.key(p.d.body, 'KeyA'); expect('another key does nothing', cmds(p).length === 1);

console.log('5. the settings');
p = makePage(); p.handlers.state(S.locked);
expect('the boxes are filled from the board at the start: closed 106, band 10, open 250, speed 100, soft start 250, 600 ms, 600 ms, direction -1', p.$('closedMm').value === '106' && p.$('tolMm').value === '10' && p.$('openMm').value === '250' && p.$('pwm').value === '100' && p.$('ramp').value === '250' && p.$('openMs').value === '600' && p.$('closeMs').value === '600' && p.$('openDir').value === '-1');
p.type(p.$('openMs'), '321'); p.handlers.state(S.locked); p.handlers.state(S.moving);
expect('the board repeating its settings never overwrites what you typed (321 stays)', p.$('openMs').value === '321');
const cal = clone(S.locked); cal.settings.closed_mm = 101; p.handlers.state(cal);
expect('but when the board changes a value (after "calibrate") the box follows: closed distance 101, and the other box you typed in is left alone', p.$('closedMm').value === '101' && p.$('openMs').value === '321');
p = makePage(); p.handlers.state(S.locked); p.type(p.$('closedMm'), '5000'); p.type(p.$('tolMm'), '1'); p.type(p.$('openMm'), 'abc'); p.type(p.$('pwm'), '300'); p.type(p.$('openDir'), '1'); p.click(p.$('saveBtn'));
const sv = lastCmd(p);
expect('"Save settings" sends them cut to their limits (5000 becomes 1000, 1 becomes 5, 300 becomes 255), text that is not a number keeps the board value (250), and the direction chosen (+1)', sv.action === 'settings' && sv.settings.closed_mm === 1000 && sv.settings.closed_tol_mm === 5 && sv.settings.open_mm === 250 && sv.settings.pwm === 255 && sv.settings.open_dir === 1 && sv.settings.ramp_ms === 250 && sv.settings.open_ms === 600 && sv.settings.close_ms === 600, JSON.stringify(sv));
expect('and the boxes show the cut values', p.$('closedMm').value === '1000' && p.$('pwm').value === '255' && p.$('openMm').value === '250');
p = makePage(); p.handlers.state(S.locked); p.$('pushBack').checked = true; p.type(p.$('pushBack'), undefined);
expect('the "Push back when forced" switch sends just that setting, at once', JSON.stringify(lastCmd(p)) === '{"action":"settings","settings":{"push_back":true}}', JSON.stringify(lastCmd(p)));
const pb = clone(S.locked); pb.settings.push_back = true; p.handlers.state(pb); expect('and follows the board when it says push back is on', p.$('pushBack').checked);

console.log('6. the events');
p = makePage(); p.handlers.state(S.tamper);
let trs = p.d.querySelectorAll('#events tr');
expect('the events are listed, the newest first (%d events)' % S.tamper.events.length, trs.length === S.tamper.events.length && trs[0].children[1].textContent === S.tamper.events[S.tamper.events.length - 1].kind);
expect('a tamper event is shown in red (its class), and the distance of each is shown', [...trs].some((tr) => tr.children[1].textContent === 'tamper' && tr.children[1].className === 'k-tamper') && [...trs].some((tr) => tr.children[3].textContent === '123'));
p.handlers.state(clone(S.tamper)); expect('the same state arriving again does not rebuild the list', p.d.querySelectorAll('#events tr')[0] === trs[0]);
p = makePage(); const noecho = clone(S.tamper); noecho.events[0].mm = null; p.handlers.state(noecho); expect('an event with no distance says "no echo"', [...p.d.querySelectorAll('#events tr')].some((tr) => tr.children[3].textContent === 'no echo'));
p = makePage(); p.handlers.state(S.tamper); p.click(p.$('evCsv'));
const csv = p.downloads.length ? decodeURIComponent(p.downloads[0].href.replace('data:text/csv;charset=utf-8,', '')) : '';
expect('a CSV file of the events is offered, with the header and one line per event', p.downloads.length === 1 && p.downloads[0].name === 'door_events.csv' && csv.split('\n')[0] === 'time,kind,text,mm' && csv.trim().split('\n').length === S.tamper.events.length + 1 && csv.includes('TAMPER'), csv.split('\n')[0]);
p = makePage(); p.handlers.state(S.waiting); p.click(p.$('evCsv')); expect('with no events nothing is downloaded, and a warning says so', p.downloads.length === 0 && p.$('notice').textContent.includes('Nothing to download'));
p.click(p.$('evClear')); expect('"Clear the list" sends "clear_events"', JSON.stringify(lastCmd(p)) === '{"action":"clear_events"}');

console.log('7. messages from the board');
p = makePage(); p.handlers.notice({ level: 'warn', text: 'TAMPER: the locked door reads ajar (123 mm): the door was forced.' });
expect('a notice is shown with its colour', p.$('notice').className.includes('warn') && p.$('notice').textContent.includes('TAMPER'));
p.handlers.notice({ level: 'ok', text: 'Stopped.' }); expect('the next notice replaces it', p.$('notice').textContent === 'Stopped.' && p.$('notice').className.includes('ok'));

console.log('\n' + (problems === 0 ? 'ALL PASSED' : problems + ' CHECK(S) FAILED'));
process.exit(problems ? 1 : 0);
