// Tests for assets/index.html + assets/app.js in a simulated browser (jsdom).   npm install jsdom  &&  node test_page.js
// It renders the REAL messages the app produces (lock_samples.json from test_lockbox.py, view_samples.json from test_vision_core.py), including real camera JPEGs.
const { JSDOM, VirtualConsole } = require('jsdom');
const fs = require('fs');
const path = require('path');
const assets = path.join(__dirname, '..', 'assets');
let problems = 0;
function expect(label, cond, detail) { console.log('  ' + (cond ? 'ok  ' : 'FAIL') + ' ' + label + (detail !== undefined ? '   [' + detail + ']' : '')); if (!cond) problems++; }
for (const f of ['lock_samples.json', 'view_samples.json']) if (!fs.existsSync(path.join(__dirname, f))) { console.log(f + ' not found: run test_lockbox.py and test_vision_core.py first'); process.exit(1); }
const L = JSON.parse(fs.readFileSync(path.join(__dirname, 'lock_samples.json'), 'utf8'));
const V = JSON.parse(fs.readFileSync(path.join(__dirname, 'view_samples.json'), 'utf8'));
const clone = (o) => JSON.parse(JSON.stringify(o));
const popcount = (rows) => rows.reduce((n, r) => n + r.toString(2).split('1').length - 1, 0);

function makePage() {
  const html = fs.readFileSync(path.join(assets, 'index.html'), 'utf8').replace(/<script[^>]*><\/script>/g, '');
  const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true, url: 'http://board.local:7000/', virtualConsole: new VirtualConsole() });
  const w = dom.window, handlers = {}, emitted = [], downloads = [];
  w.io = () => ({ on: (e, f) => { handlers[e] = f; }, emit: (e, d) => emitted.push([e, d]) });
  w.HTMLAnchorElement.prototype.click = function () { downloads.push({ href: this.href, name: this.download }); };
  w.eval(fs.readFileSync(path.join(assets, 'app.js'), 'utf8'));
  const d = w.document, $ = (id) => d.getElementById(id);
  const click = (e) => e.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true }));
  const key = (target, k, extra) => { const ev = new w.KeyboardEvent('keydown', Object.assign({ key: k, code: k === ' ' ? 'Space' : k, bubbles: true, cancelable: true }, extra || {})); target.dispatchEvent(ev); return ev; };
  const keyup = (target, k) => { const ev = new w.KeyboardEvent('keyup', { key: k, code: k === ' ' ? 'Space' : k, bubbles: true, cancelable: true }); target.dispatchEvent(ev); return ev; };
  const set = (e, v) => { e.value = v; e.dispatchEvent(new w.Event('input', { bubbles: true })); e.dispatchEvent(new w.Event('change', { bubbles: true })); };
  return { w, d, $, click, key, keyup, set, handlers, emitted, downloads };
}
const cmds = (p) => p.emitted.filter((e) => e[0] === 'cmd').map((e) => e[1]);
const lastCmd = (p) => cmds(p).pop();
const ledsMatch = (p, rows) => { const leds = [...p.d.querySelectorAll('#matrix .led')]; if (leds.length !== 104) return false; for (let r = 0; r < 8; r++) for (let c = 0; c < 13; c++) if (leds[r * 13 + c].classList.contains('on') !== (((rows[r] >> (12 - c)) & 1) === 1)) return false; return true; };

console.log('1. connecting');
let p = makePage(); p.handlers.connect();
expect('"connected" in green, and it asks the board for the state', p.$('conn').textContent === 'connected' && p.$('conn').className.includes('good') && JSON.stringify(lastCmd(p)) === '{"action":"refresh"}');
p.handlers.disconnect(); expect('a dropped connection is shown in red', p.$('conn').textContent === 'disconnected' && p.$('conn').className.includes('bad'));

console.log('2. before a code is set');
p = makePage(); p.handlers.lock(L.setup);
expect('"SET A CODE" in grey, the hint says to set a code, the chip says no code, and the policy line says none is set', p.$('banner').textContent === 'SET A CODE' && p.$('banner').className.includes('unknown') && p.$('hint').textContent.startsWith('Set a code first') && p.$('codechip').textContent === 'no code set yet' && p.$('codechip').className.includes('warn') && p.$('policy').textContent.startsWith('No code is set yet'));

console.log('3. the lock in each state');
p = makePage(); p.handlers.lock(L.idle);
expect('locked: the banner says LOCKED, the code chip is green, the door chip says closed', p.$('banner').textContent === 'LOCKED' && p.$('banner').className.includes('locked') && p.$('codechip').textContent === 'code is set' && p.$('codechip').className.includes('good') && p.$('doorchip').textContent === 'door: closed');
expect('the LED matrix on the page shows exactly the picture sent to the board: all 104 LEDs match (the closed padlock, %d lit)' % popcount(L.idle.picture), ledsMatch(p, L.idle.picture) && p.d.querySelectorAll('#matrix .led.on').length === popcount(L.idle.picture) && popcount(L.idle.picture) === 41);
expect('no challenge digit and no progress dots are shown when nothing is going on', p.$('challengebox').hidden && p.$('dotsbox').hidden);
expect('the policy line says: 3 digits, a live challenge of 1 digit from 1, 3, 5, 3 wrong tries, a first lockout of 30 s, the door locking after 10 s, and the tamper lockout of 15 s', ['3 different digits', '1 digit(s) from 1, 3, 5', '3 wrong tries', 'lockout of 30 s', 'locks again after 10 s', 'tamper blocks finger entry for 15 s'].every((t) => p.$('policy').textContent.includes(t)), p.$('policy').textContent);
expect('the door panel shows the distance (106), "door reads: closed", and the closed colour', p.$('mm').textContent === '106' && p.$('band').textContent === 'door reads: closed' && p.$('band').className.includes('closed'));
p.handlers.lock(L.challenge);
expect('the challenge: the banner says so, and the digit to show first is displayed big (%s)' % L.challenge.challenge_digit, p.$('banner').textContent === 'CHALLENGE: show the digit' && !p.$('challengebox').hidden && p.$('bigChallenge').textContent === String(L.challenge.challenge_digit) && p.$('dotsbox').hidden);
expect('and the matrix shows it (all 104 LEDs match)', ledsMatch(p, L.challenge.picture));
p.handlers.lock(L.entering);
expect('entering the code: "SHOW YOUR CODE: 2 of 3" after one digit, three progress dots with exactly one lit, and the challenge digit is gone', p.$('banner').textContent === 'SHOW YOUR CODE: 2 of 3' && p.$('challengebox').hidden && !p.$('dotsbox').hidden && p.d.querySelectorAll('#dots .dot').length === 3 && p.d.querySelectorAll('#dots .dot.on').length === 1);
expect('the dots never show WHICH digits were read (no text in them), and the matrix shows the digit with its progress dot', p.d.querySelector('#dots').textContent === '' && ledsMatch(p, L.entering.picture));
p.handlers.lock(L.unlocked);
expect('unlocked: green, with the seconds left, the door chip says open, and the matrix shows the open padlock', /^UNLOCKED: \d+ s$/.test(p.$('banner').textContent) && p.$('banner').className.includes('unlocked') && p.$('doorchip').textContent === 'door: open' && ledsMatch(p, L.unlocked.picture), p.$('banner').textContent);
p.handlers.lock(L.lockout);
expect('a lockout: "LOCKED OUT" with the seconds left, and the cross-bar picture', p.$('banner').textContent === 'LOCKED OUT: ' + Math.ceil(L.lockout.display.lockout_left) + ' s' && p.$('banner').className.includes('lockout') && ledsMatch(p, L.lockout.picture), p.$('banner').textContent);
p.handlers.lock(L.tamper);
expect('tamper: red and blinking, with how long finger entry is blocked, the door says it was forced, and the matrix shows the "!"', /^TAMPER: entry blocked \d+ s$/.test(p.$('banner').textContent) && p.$('banner').className.includes('tamper') && p.$('doorinfo').textContent.includes('TAMPER') && ledsMatch(p, L.tamper.picture), p.$('banner').textContent);
p.handlers.lock(L.fault);
expect('a door that did not open: the chip says "door problem" in red, the door panel says what happened, the hint repeats it, and the matrix shows the "X"', p.$('doorchip').textContent === 'door problem' && p.$('doorchip').className.includes('bad') && p.$('doorinfo').textContent.includes('did not open') && p.$('hint').textContent.includes('The door has a problem') && ledsMatch(p, L.fault.picture));
p.handlers.lock(L.mismatch); expect('a door left open while the lock is locked: the hint says how to put it right', p.$('hint').textContent.includes('The door is open but the lock is locked') && p.$('hint').textContent.includes('Close button'));
const lostS = clone(L.idle); lostS.door.sensor = 'lost'; p.handlers.lock(lostS); expect('a door sensor that went quiet is shown in red', p.$('doorchip').textContent === 'door sensor lost' && p.$('doorchip').className.includes('bad'));

console.log('4. the button, the keys and the door buttons');
p = makePage(); p.handlers.lock(L.idle); p.click(p.$('pushBtn'));
expect('the big button sends "button"', JSON.stringify(lastCmd(p)) === '{"action":"button"}');
p = makePage(); p.handlers.lock(L.idle); let ev = p.key(p.d.body, ' ');
expect('the SPACE bar is the button, and does not scroll the page', JSON.stringify(cmds(p)) === '[{"action":"button"}]' && ev.defaultPrevented);
p.$('code').focus(); const typed = p.key(p.$('code'), ' '); p.key(p.$('pool'), ' '); p.key(p.$('challenge'), ' ');
expect('SPACE while typing a code or choosing in a list does not press the button (and is not blocked)', cmds(p).length === 1 && !typed.defaultPrevented);
p = makePage(); p.handlers.lock(L.idle); p.$('openBtn').focus(); const onBtn = p.key(p.$('openBtn'), ' '); const up = p.keyup(p.$('openBtn'), ' ');
expect('SPACE with the Open button focused presses the lock button (NOT the door), and its key release cannot click the focused button', JSON.stringify(cmds(p)) === '[{"action":"button"}]' && onBtn.defaultPrevented && up.defaultPrevented);
expect('the same for a focused "Maintenance" heading (its release cannot open it by accident)', p.keyup(p.d.querySelector('summary'), ' ').defaultPrevented);
p = makePage(); p.handlers.lock(L.idle); p.key(p.d.body, 'Escape'); p.$('code').focus(); p.key(p.$('code'), 'Escape');
expect('ESC stops the door motor, also while typing in a box', JSON.stringify(cmds(p)) === '[{"action":"stop"},{"action":"stop"}]');
p = makePage(); p.handlers.lock(L.idle);
[['stopBtn', '{"action":"stop"}'], ['openBtn', '{"action":"door_open"}'], ['closeBtn', '{"action":"door_close"}'], ['calBtn', '{"action":"calibrate"}'], ['clearLog', '{"action":"clear_log"}']].forEach(([id, want]) => { p.click(p.$(id)); expect('the "' + id + '" button sends ' + want, JSON.stringify(lastCmd(p)) === want); });
p.$('pushBack').checked = true; p.set(p.$('pushBack'), undefined); p.$('pushBack').checked = true; p.$('pushBack').dispatchEvent(new p.w.Event('change', { bubbles: true }));
expect('the "Push back when forced" box sends its state', JSON.stringify(lastCmd(p)) === '{"action":"push_back","on":true}');
p.click(p.$('pushBtn')); expect('clicking a button takes the focus off it', p.d.activeElement !== p.$('pushBtn') && p.d.activeElement !== p.$('stopBtn'));
p.key(p.d.body, 'a'); p.key(p.d.body, 'Enter'); expect('other keys do nothing', cmds(p).filter((c) => c.action === 'button').length === 1);
const pb = clone(L.idle); pb.door.settings.push_back = true; p.handlers.lock(pb); expect('the box follows the board when it says push back is on', p.$('pushBack').checked);

console.log('5. moving the square (only while "Camera and square" is open)');
p = makePage(); p.handlers.view(V.steady); const n0 = cmds(p).length; p.key(p.d.body, 'ArrowLeft'); p.key(p.d.body, '+');
expect('the arrow keys and + do nothing while that part is closed (so they cannot be pressed by accident)', cmds(p).length === n0);
p.$('squareBox').open = true; ev = p.key(p.d.body, 'ArrowLeft');
expect('open: the left arrow moves the square 4 pixels and does not scroll the page', JSON.stringify(lastCmd(p)) === '{"action":"nudge","dx":-4,"dy":0,"ds":0}' && ev.defaultPrevented);
p.key(p.d.body, 'ArrowDown', { shiftKey: true }); expect('with Shift it moves 16', JSON.stringify(lastCmd(p)) === '{"action":"nudge","dx":0,"dy":16,"ds":0}');
p.key(p.d.body, '+'); p.key(p.d.body, '-'); expect('+ and − resize it by 4', cmds(p).slice(-2).map((c) => c.ds).join() === '4,-4');
[['left', '{"action":"nudge","dx":-4,"dy":0,"ds":0}'], ['up', '{"action":"nudge","dx":0,"dy":-4,"ds":0}'], ['bigger', '{"action":"nudge","dx":0,"dy":0,"ds":4}']].forEach(([id, want]) => { p.click(p.$(id)); expect('the "' + id + '" button sends ' + want, JSON.stringify(lastCmd(p)) === want); });
p.click(p.$('find')); expect('"Find the tape square" asks for blue by default', JSON.stringify(lastCmd(p)) === '{"action":"find_tape","color":"blue"}');
p.click(p.$('saveRoi')); p.click(p.$('resetRoi')); expect('Save and "Back to the training square" send save_roi and reset_roi', JSON.stringify(cmds(p).slice(-2)) === '[{"action":"save_roi"},{"action":"reset_roi"}]');
p.$('fmt').value = 'YUYV'; p.click(p.$('applyFmt')); expect('the camera format is sent', JSON.stringify(lastCmd(p)) === '{"action":"camera_mode","fourcc":"YUYV"}');

console.log('6. choosing a code');
p = makePage(); p.handlers.lock(L.idle); p.set(p.$('code'), '245'); p.set(p.$('confirm'), '245'); p.set(p.$('challenge'), '2'); p.set(p.$('pool'), '12345'); p.click(p.$('saveCode'));
expect('a good code is sent with the challenge settings as numbers', JSON.stringify(lastCmd(p)) === '{"action":"set_code","code":"245","confirm":"245","challenge":2,"pool":"12345"}', JSON.stringify(lastCmd(p)));
expect('and the boxes are emptied at once, so the digits do not stay on the page', p.$('code').value === '' && p.$('confirm').value === '');
for (const [a, b, why] of [['244', '244', 'a repeated digit'], ['240', '240', 'a zero'], ['24', '24', 'two digits'], ['abc', 'abc', 'letters'], ['245', '254', 'two codes that differ']]) {
  p = makePage(); p.set(p.$('code'), a); p.set(p.$('confirm'), b); p.click(p.$('saveCode'));
  expect('a code with ' + why + ' is not sent: a warning says what is wrong, and the boxes are emptied', cmds(p).length === 0 && p.$('notice').className.includes('warn') && p.$('code').value === '' && p.$('confirm').value === '');
}
p = makePage(); p.set(p.$('code'), '314'); p.set(p.$('confirm'), '314'); p.click(p.$('saveCode'));
expect('by default the live challenge is 1 digit from 1, 3, 5', lastCmd(p).challenge === 1 && lastCmd(p).pool === '135');

console.log('7. the log');
p = makePage(); const withLog = clone(L.idle); withLog.log = [{ time: '03:00:00', source: 'door', kind: 'locked', text: 'The door is closed: locked.' }, { time: '03:00:05', source: 'lock', kind: 'tamper_lockout', text: 'TAMPER: <b>x</b>, "quoted"' }, { time: '03:00:09', source: 'lock', kind: 'unlocked', text: 'UNLOCKED' }];
p.handlers.lock(withLog); let trs = p.d.querySelectorAll('#logRows tr');
expect('every entry is a row, the newest first, with its time, where it came from, its kind and what happened', trs.length === 3 && trs[0].children[2].textContent === 'unlocked' && trs[2].children[1].textContent === 'door' && trs[2].children[0].textContent === '03:00:00');
expect('text from the board is shown as text, never as HTML, and the kinds have their colours', p.d.querySelectorAll('#logRows b').length === 0 && trs[1].children[3].textContent === 'TAMPER: <b>x</b>, "quoted"' && trs[1].children[2].className === 'k-tamper_lockout' && trs[0].children[2].className === 'k-unlocked');
p.click(p.$('csv')); const csv = p.downloads.length ? decodeURIComponent(p.downloads[0].href.replace('data:text/csv;charset=utf-8,', '')) : '';
expect('a CSV of the log is offered with a header, one line per entry, and a text with a comma and quotes written safely', p.downloads.length === 1 && p.downloads[0].name === 'lockbox_log.csv' && csv.split('\n')[0] === 'time,source,kind,text' && csv.trim().split('\n').length === 4 && csv.includes('"TAMPER: <b>x</b>, ""quoted"""'), csv.split('\n')[0]);
p = makePage(); const emptyL = clone(L.idle); emptyL.log = []; p.handlers.lock(emptyL); p.click(p.$('csv'));
expect('with an empty log nothing is downloaded, and a warning says so', p.downloads.length === 0 && p.$('notice').textContent.includes('Nothing to download'));

console.log('8. the camera view');
p = makePage(); p.handlers.view(V.steady);
expect('the real camera picture and the crop are shown, the answer is 5, steady, sure to some %, and the camera chip names the webcam', p.$('frame').src.startsWith('data:image/jpeg;base64,') && p.$('crop').src.startsWith('data:image/jpeg;base64,') && p.$('digit').textContent === '5' && p.$('steady').textContent === 'steady: 5' && p.$('steady').className.includes('good') && /^sure to \d+%$/.test(p.$('conf').textContent) && p.$('camera').textContent.startsWith('camera: icspring camera') && p.$('camera').className.includes('good'));
const fills = [...p.d.querySelectorAll('#bars .fill')]; expect('the bars follow the probabilities and the likeliest is highlighted', parseFloat(fills[5].style.width) === Math.max(...fills.map((f) => parseFloat(f.style.width))) && p.d.querySelectorAll('#bars .bar.top').length === 1);
expect('the square is drawn over the picture where it belongs (x 108, y 163, side 317 on 640 x 480, as percentages)', Math.abs(parseFloat(p.$('roi').style.left) - 100 * 108 / 640) < 0.01 && Math.abs(parseFloat(p.$('roi').style.width) - 100 * 317 / 640) < 0.01 && p.$('roiSource').textContent.includes('x 108, y 163, side 317'));
p.handlers.view(V.no_camera); expect('with no camera: a yellow chip, a dash for the answer, and "no camera picture yet" over the frame', p.$('camera').textContent === 'no camera found yet' && p.$('camera').className.includes('warn') && p.$('digit').textContent === '–' && p.$('nopic').style.display !== 'none');
p.handlers.view(V.unsure); expect('an unsure answer says "not steady yet"', p.$('digit').textContent === '1' && p.$('steady').textContent === 'not steady yet' && p.$('steady').className.includes('warn'));
p.handlers.view(V.lost); expect('a lost camera is shown in red', p.$('camera').textContent === 'camera lost: plug it in again' && p.$('camera').className.includes('bad'));
const yuyv = clone(V.steady); yuyv.camera.mode = 'YUYV'; yuyv.camera.format = 'YUYV 640x480, the camera says 30.0 fps'; p.handlers.view(yuyv);
expect('the camera format list follows the board, and the chip shows what the camera agreed to', p.$('fmt').value === 'YUYV' && p.$('camera').textContent.includes('YUYV 640x480'));
p.$('fmt').value = ''; p.handlers.view(yuyv); expect('but the board repeating its setting never overwrites a choice being made', p.$('fmt').value === '');

console.log('8b. the measurements');
p = makePage(); const stl = clone(L.idle); stl.stats = { sessions: 10, unlocked: 8, denied_code: 1, denied_challenge: 1, timeouts: 0, lockouts: 0, tamper: 1, faults: 0, unlock_s: { n: 8, last: 5.6, median: 5.2 }, open_s: { n: 8, last: 1.5, median: 1.4 }, check_ms: { n: 9, last: 612.4, slowest: 640.1 }, locked_for_s: 125.4, uptime_s: 3725.0 };
p.handlers.lock(stl);
expect('the tally is shown: 10 tries, 8 opened the door, 1 wrong code, 1 wrong challenge digit, 0 too slow, 0 lockouts, 1 tamper alarm, 0 faults', ['sSessions', 'sUnlocked', 'sCode', 'sChallenge', 'sTimeouts', 'sLockouts', 'sTamper', 'sFaults'].map((i) => p.$(i).textContent).join(',') === '10,8,1,1,0,0,1,0');
expect('the times are in plain words: button to unlocked, unlocked to door open, and the code check with its slowest', p.$('sUnlock').textContent === '5.2 s (last 5.6 s, 8 measured)' && p.$('sOpen').textContent === '1.4 s (last 1.5 s, 8 measured)' && p.$('sCheck').textContent === '612.4 ms (slowest 640.1 ms)', p.$('sUnlock').textContent + ' | ' + p.$('sCheck').textContent);
expect('"locked with no alarm for" and "the app has been running for" are shown as minutes and seconds (2:05 and 62:05)', p.$('sLocked').textContent === '2:05' && p.$('sUptime').textContent === '62:05');
const none = clone(L.idle); none.stats = { sessions: 0, unlocked: 0, denied_code: 0, denied_challenge: 0, timeouts: 0, lockouts: 0, tamper: 0, faults: 0, unlock_s: { n: 0, last: null, median: null }, open_s: { n: 0, last: null, median: null }, check_ms: { n: 0, last: null, slowest: null }, locked_for_s: 0, uptime_s: 4 };
p.handlers.lock(none); expect('with nothing measured yet the times show a dash, not zero', p.$('sUnlock').textContent === '–' && p.$('sOpen').textContent === '–' && p.$('sCheck').textContent === '–' && p.$('sLocked').textContent === '0:00' && p.$('sUptime').textContent === '0:04');
p.handlers.view(V.steady); expect('the camera pictures a second and the network steps a second are shown next to each other', p.$('sSpeed').textContent === (V.steady.camera.fps).toFixed(1) + ' / ' + (V.steady.timing.fps).toFixed(1), p.$('sSpeed').textContent);
p.click(p.$('resetStats')); expect('"Reset the tally" sends reset_stats', JSON.stringify(lastCmd(p)) === '{"action":"reset_stats"}');
p.click(p.$('wholeLog')); expect('"Download the whole log" asks the board for it', JSON.stringify(lastCmd(p)) === '{"action":"log_full"}');
p.handlers.fulllog({ rows: [{ time: '03:00:00', source: 'system', kind: 'started', text: 'The app started.' }, { time: '03:00:09', source: 'lock', kind: 'unlocked', text: 'UNLOCKED' }] });
const fcsv = p.downloads.length ? decodeURIComponent(p.downloads[0].href.replace('data:text/csv;charset=utf-8,', '')) : '';
expect('when the board sends it, the page offers it as a CSV file with a header and every row', p.downloads.length === 1 && p.downloads[0].name === 'lockbox_log_full.csv' && fcsv.split('\n')[0] === 'time,source,kind,text' && fcsv.trim().split('\n').length === 3);
p.handlers.fulllog({ rows: [] }); expect('an empty log gives a warning, not an empty file', p.downloads.length === 1 && p.$('notice').textContent.includes('log is empty'));

console.log('9. messages from the board');
p = makePage(); p.handlers.notice({ level: 'warn', text: 'Set a code first (the Code section).' });
expect('a notice is shown with its colour', p.$('notice').className.includes('warn') && p.$('notice').textContent.startsWith('Set a code first'));
p.handlers.notice({ level: 'ok', text: 'The code is saved (a salted hash: the digits are not stored).' }); expect('the next one replaces it', p.$('notice').className.includes('ok'));

console.log('\n' + (problems === 0 ? 'ALL PASSED' : problems + ' CHECK(S) FAILED'));
process.exit(problems ? 1 : 0);
