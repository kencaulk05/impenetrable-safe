// Tests for assets/index.html + assets/app.js in a simulated browser (jsdom).   npm install jsdom  &&  node test_page.js
// It renders the REAL payloads that python/main.py produces (state_samples.json, written by test_motortest.py).
const { JSDOM, VirtualConsole } = require('jsdom');
const fs = require('fs');
const path = require('path');
const assets = path.join(__dirname, '..', 'assets');
let problems = 0;
function expect(label, cond, detail) { console.log('  ' + (cond ? 'ok  ' : 'FAIL') + ' ' + label + (detail !== undefined ? '   [' + detail + ']' : '')); if (!cond) problems++; }
const samplesFile = path.join(__dirname, 'state_samples.json');
if (!fs.existsSync(samplesFile)) { console.log('state_samples.json not found: run `python test_motortest.py` first'); process.exit(1); }
const S = JSON.parse(fs.readFileSync(samplesFile, 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));

function makePage() {
  const html = fs.readFileSync(path.join(assets, 'index.html'), 'utf8').replace(/<script[^>]*><\/script>/g, '');
  const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true, url: 'http://board.local:7000/', virtualConsole: new VirtualConsole() });
  const w = dom.window, handlers = {}, emitted = [], downloads = [];
  w.io = () => ({ on: (e, f) => { handlers[e] = f; }, emit: (e, d) => emitted.push([e, d]) });
  w.HTMLAnchorElement.prototype.click = function () { downloads.push({ href: this.href, name: this.download }); };
  w.eval(fs.readFileSync(path.join(assets, 'app.js'), 'utf8'));
  const d = w.document, $ = (id) => d.getElementById(id);
  const click = (e) => e.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true }));
  const key = (target, code) => { const ev = new w.KeyboardEvent('keydown', { code, key: code === 'Escape' ? 'Escape' : (code === 'Space' ? ' ' : code), bubbles: true, cancelable: true }); target.dispatchEvent(ev); return ev; };
  const keyup = (target, code) => { const ev = new w.KeyboardEvent('keyup', { code, bubbles: true, cancelable: true }); target.dispatchEvent(ev); return ev; };
  const type = (e, v) => { e.value = v; e.dispatchEvent(new w.Event('input', { bubbles: true })); e.dispatchEvent(new w.Event('change', { bubbles: true })); };
  return { w, d, $, click, key, keyup, type, handlers, emitted, downloads };
}
const cmds = (p) => p.emitted.filter((e) => e[0] === 'cmd').map((e) => e[1]);
const lastCmd = (p) => cmds(p).pop();
const DEFAULT = '{"pwm":150,"ramp_ms":250,"open_ms":600,"close_ms":600,"open_dir":1}';

console.log('1. connecting');
let p = makePage(); p.handlers.connect();
expect('"connected" in green, and it asks the board for the state', p.$('conn').textContent === 'connected' && p.$('conn').className.includes('good') && JSON.stringify(lastCmd(p)) === '{"action":"refresh"}');
p.handlers.disconnect();
expect('a dropped connection is shown in red', p.$('conn').textContent === 'disconnected' && p.$('conn').className.includes('bad'));

console.log('2. an idle motor');
p = makePage(); p.handlers.state(S.idle);
expect('it shows the door belief and the next move, a green "stopped" chip, and no countdown', p.$('door').textContent === 'closed' && p.$('next').textContent === 'open' && p.$('motor').textContent === 'motor: stopped' && p.$('motor').className.includes('good') && p.$('remaining').textContent === '');
expect('Next, Open and Close are available, and STOP is too', !p.$('nextBtn').disabled && !p.$('openBtn').disabled && !p.$('closeBtn').disabled && !p.$('stopBtn').disabled);
expect('the boxes are filled from what the board remembered: speed 150, soft start 250, 600 ms, 600 ms, direction not swapped', p.$('pwm').value === '150' && p.$('ramp').value === '250' && p.$('openMs').value === '600' && p.$('closeMs').value === '600' && !p.$('swap').checked && p.$('pwmVal').textContent === '150');

console.log('3. a running motor');
p = makePage(); p.handlers.state(S.running);
expect('a blue "running" chip with the direction, and how long is left', p.$('motor').textContent === 'motor: running → (+1)' && p.$('motor').className.includes('run') && p.$('remaining').textContent === '400 ms left', p.$('motor').textContent + ' | ' + p.$('remaining').textContent);
expect('Next, Open and Close are switched off while it runs, but STOP is not', p.$('nextBtn').disabled && p.$('openBtn').disabled && p.$('closeBtn').disabled && !p.$('stopBtn').disabled);
const run2 = clone(S.running); run2.run_dir = -1; p.handlers.state(run2);
expect('moving the other way shows the left arrow', p.$('motor').textContent === 'motor: running ← (-1)');
p.click(p.$('nextBtn')); p.click(p.$('openBtn')); p.click(p.$('closeBtn'));
expect('clicking the move buttons while it runs sends nothing', cmds(p).length === 0);
p.handlers.state(S.idle);
expect('when it stops the buttons come back and the chip is green again', !p.$('nextBtn').disabled && p.$('motor').className.includes('good') && p.$('remaining').textContent === '');

console.log('4. the buttons');
p = makePage(); p.handlers.state(S.idle); p.click(p.$('nextBtn'));
expect('Next sends "next" with the current settings', JSON.stringify(lastCmd(p)) === '{"action":"next","settings":' + DEFAULT + '}', JSON.stringify(lastCmd(p)));
p.click(p.$('openBtn')); expect('Open sends a move "open" with the settings', JSON.stringify(lastCmd(p)) === '{"action":"move","which":"open","settings":' + DEFAULT + '}');
p.click(p.$('closeBtn')); expect('Close sends a move "close"', lastCmd(p).which === 'close');
p.click(p.$('stopBtn')); expect('STOP sends "stop"', JSON.stringify(lastCmd(p)) === '{"action":"stop"}');
p.click(p.$('isOpen')); expect('"the door is now open" sends set_door open', JSON.stringify(lastCmd(p)) === '{"action":"set_door","door":"open"}');
p.click(p.$('isClosed')); expect('"closed" sends set_door closed', JSON.stringify(lastCmd(p)) === '{"action":"set_door","door":"closed"}');
p.click(p.$('clear')); expect('Clear sends clear', JSON.stringify(lastCmd(p)) === '{"action":"clear"}');
p.click(p.$('nextBtn'));
expect('clicking a button takes the focus off it, so a later SPACE cannot click it', p.d.activeElement !== p.$('nextBtn') && p.d.activeElement !== p.$('stopBtn'));

console.log('5. the keyboard (the Space bar is the push-button, Esc is the emergency stop)');
p = makePage(); p.handlers.state(S.idle); const ev = p.key(p.d.body, 'Space');
expect('SPACE with the motor stopped asks for the next move, and does not scroll the page', JSON.stringify(lastCmd(p)) === '{"action":"next","settings":' + DEFAULT + '}' && ev.defaultPrevented);
p = makePage(); p.handlers.state(S.running); p.key(p.d.body, 'Space');
expect('SPACE while the motor is running STOPS it (and does not ask for another move)', JSON.stringify(cmds(p)) === '[{"action":"stop"}]');
p = makePage(); p.handlers.state(S.idle); p.key(p.d.body, 'Escape');
expect('ESC stops the motor, also when it is idle (a harmless stop)', JSON.stringify(cmds(p)) === '[{"action":"stop"}]');
p = makePage(); p.handlers.state(S.running); p.$('openMs').focus(); p.key(p.$('openMs'), 'Escape');
expect('ESC stops it even while the cursor is in a settings box', JSON.stringify(cmds(p)) === '[{"action":"stop"}]');
p = makePage(); p.handlers.state(S.idle); p.$('openMs').focus(); const typed = p.key(p.$('openMs'), 'Space'); p.key(p.$('pwm'), 'Space'); p.key(p.$('swap'), 'Space');
expect('SPACE while typing in a settings box (or on a slider or the checkbox) does nothing, and is not blocked', cmds(p).length === 0 && !typed.defaultPrevented);
p = makePage(); p.handlers.state(S.idle); p.$('openBtn').focus(); const onBtn = p.key(p.$('openBtn'), 'Space'); const up = p.keyup(p.$('openBtn'), 'Space');
expect('SPACE with the Open button focused asks for the NEXT move (not Open), and its key release cannot click the button', JSON.stringify(cmds(p)) === '[{"action":"next","settings":' + DEFAULT + '}]' && onBtn.defaultPrevented && up.defaultPrevented);
p.key(p.d.body, 'KeyA'); expect('another key does nothing', cmds(p).length === 1);

console.log('6. the settings');
p = makePage(); p.handlers.state(S.idle); p.$('swap').checked = true; p.click(p.$('nextBtn'));
expect('"Swap direction" sends the opposite motor direction', lastCmd(p).settings.open_dir === -1);
p = makePage(); p.handlers.state(S.idle); p.type(p.$('openMs'), '9999'); p.type(p.$('closeMs'), '0'); p.type(p.$('pwm'), '999'); p.type(p.$('ramp'), '5000'); p.click(p.$('nextBtn'));
const s1 = lastCmd(p).settings;
expect('values beyond the limits are cut before they are sent: 9999 ms becomes 3000, 0 ms becomes 50, speed 999 becomes 255, soft start 5000 becomes 1000, and the boxes show the cut values', s1.open_ms === 3000 && s1.close_ms === 50 && s1.pwm === 255 && s1.ramp_ms === 1000 && p.$('openMs').value === '3000' && p.$('closeMs').value === '50', JSON.stringify(s1));
p = makePage(); p.handlers.state(S.idle); p.type(p.$('openMs'), 'abc'); p.click(p.$('nextBtn'));
expect('text that is not a number falls back to the last good value (600)', lastCmd(p).settings.open_ms === 600);
p = makePage(); p.handlers.state(S.idle); p.type(p.$('openMs'), '321'); p.handlers.state(S.idle); p.handlers.state(S.running);
expect('the board repeating its old settings never overwrites what you typed (321 stays)', p.$('openMs').value === '321');
p.type(p.$('pwm'), '120'); expect('moving the speed slider updates the number beside it', p.$('pwmVal').textContent === '120');

console.log('7. the table of moves');
p = makePage(); p.handlers.state(S.with_moves);
let trs = p.d.querySelectorAll('#rows tr');
expect('two moves give two rows, the newest first (#2 close, then #1 open)', trs.length === 2 && trs[0].children[0].textContent === '2' && trs[0].children[2].textContent === 'close' && trs[1].children[0].textContent === '1' && trs[1].children[2].textContent === 'open');
expect('each row shows the motor direction, the time, the speed, the soft start and whether the board confirmed', trs[1].children[3].textContent === '+1' && trs[0].children[3].textContent === '-1' && trs[1].children[4].textContent === '600' && trs[1].children[5].textContent === '150' && trs[1].children[6].textContent === '250' && trs[1].children[7].textContent === 'yes');
const sel0 = trs[0].querySelector('select'), sel1 = trs[1].querySelector('select');
expect('every row has a drop-down with the four outcomes, showing what was chosen', [...sel0.options].map((o) => o.value).join('|') === '|reached the end|stopped short|went too far|grinding or jammed' && sel0.value === 'grinding or jammed' && sel1.value === 'reached the end');
p.type(sel0, 'stopped short');
expect('choosing an outcome sends it for that move', JSON.stringify(lastCmd(p)) === '{"action":"rate","id":2,"outcome":"stopped short"}');
p.handlers.state(clone(S.with_moves));
expect('the same state arriving again does NOT rebuild the table (a drop-down someone is using is not closed)', p.d.querySelectorAll('#rows tr')[0] === trs[0] && p.d.querySelector('#rows select') === sel0);
const changed = clone(S.with_moves); changed.moves[1].outcome = 'went too far'; p.handlers.state(changed);
expect('a real change does rebuild it: move #2 (the first row, newest first) now shows the new outcome', p.d.querySelectorAll('#rows tr')[0].children[0].textContent === '2' && p.d.querySelectorAll('#rows tr')[0].querySelector('select').value === 'went too far' && p.d.querySelectorAll('#rows tr')[1].querySelector('select').value === 'reached the end');
p = makePage(); p.handlers.state(S.unconfirmed); trs = p.d.querySelectorAll('#rows tr');
expect('a move the board never confirmed shows NOT CONFIRMED in red', trs[0].children[7].textContent === 'NOT CONFIRMED' && trs[0].children[7].className === 'bad');
p = makePage(); const waiting = clone(S.running); waiting.moves[0].confirmed = null; p.handlers.state(waiting);
expect('a move still waiting for the board shows "waiting…"', p.d.querySelectorAll('#rows tr')[0].children[7].textContent === 'waiting…');

console.log('8. downloading the moves');
p = makePage(); p.handlers.state(S.with_moves); p.click(p.$('csv'));
const csv = p.downloads.length ? decodeURIComponent(p.downloads[0].href.replace('data:text/csv;charset=utf-8,', '')) : '';
expect('a CSV file is offered with the header and one line per move', p.downloads.length === 1 && p.downloads[0].name === 'motor_moves.csv' && csv.split('\n')[0] === 'id,time,action,dir,ms,pwm,ramp_ms,confirmed,outcome' && csv.trim().split('\n').length === 3 && csv.includes('grinding or jammed'), csv.split('\n')[0]);
p = makePage(); p.handlers.state(S.idle); p.click(p.$('csv'));
expect('with no moves nothing is downloaded, and a warning says so', p.downloads.length === 0 && p.$('notice').textContent.includes('Nothing to download'));

console.log('9. messages from the board');
p = makePage(); p.handlers.notice({ level: 'warn', text: 'The motor is running: press STOP (Esc) first, or wait for the move to end.' });
expect('a notice is shown with its colour', p.$('notice').className.includes('warn') && p.$('notice').textContent.includes('press STOP'));
p.handlers.notice({ level: 'ok', text: 'Stopped.' }); expect('the next notice replaces it', p.$('notice').textContent === 'Stopped.' && p.$('notice').className.includes('ok'));

console.log('\n' + (problems === 0 ? 'ALL PASSED' : problems + ' CHECK(S) FAILED'));
process.exit(problems ? 1 : 0);
