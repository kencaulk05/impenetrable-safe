// Tests for assets/index.html + assets/app.js in a simulated browser (jsdom).   npm install jsdom  &&  node test_page.js
// It renders the REAL messages that python/main.py produces (state_samples.json, written by test_vision.py), including real camera JPEGs.
const { JSDOM, VirtualConsole } = require('jsdom');
const fs = require('fs');
const path = require('path');
const assets = path.join(__dirname, '..', 'assets');
let problems = 0;
function expect(label, cond, detail) { console.log('  ' + (cond ? 'ok  ' : 'FAIL') + ' ' + label + (detail !== undefined ? '   [' + detail + ']' : '')); if (!cond) problems++; }
const samplesFile = path.join(__dirname, 'state_samples.json');
if (!fs.existsSync(samplesFile)) { console.log('state_samples.json not found: run `python test_vision.py` first'); process.exit(1); }
const S = JSON.parse(fs.readFileSync(samplesFile, 'utf8'));

function makePage() {
  const html = fs.readFileSync(path.join(assets, 'index.html'), 'utf8').replace(/<script[^>]*><\/script>/g, '');
  const dom = new JSDOM(html, { runScripts: 'outside-only', pretendToBeVisual: true, url: 'http://board.local:7000/', virtualConsole: new VirtualConsole() });
  const w = dom.window, handlers = {}, emitted = [], downloads = [];
  w.io = () => ({ on: (e, f) => { handlers[e] = f; }, emit: (e, d) => emitted.push([e, d]) });
  w.HTMLAnchorElement.prototype.click = function () { downloads.push({ href: this.href, name: this.download }); };
  w.eval(fs.readFileSync(path.join(assets, 'app.js'), 'utf8'));
  const d = w.document, $ = (id) => d.getElementById(id);
  const click = (e) => e.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true }));
  const key = (target, k, extra) => { const ev = new w.KeyboardEvent('keydown', Object.assign({ key: k, bubbles: true, cancelable: true }, extra || {})); target.dispatchEvent(ev); return ev; };
  return { w, d, $, click, key, handlers, emitted, downloads };
}
const cmds = (p) => p.emitted.filter((e) => e[0] === 'cmd').map((e) => e[1]);
const lastCmd = (p) => cmds(p).pop();
const pct = (el) => parseFloat(el.style.width);

console.log('1. connecting');
let p = makePage(); p.handlers.connect();
expect('"connected" in green, and it asks the board for the view', p.$('conn').textContent === 'connected' && p.$('conn').className.includes('good') && JSON.stringify(lastCmd(p)) === '{"action":"refresh"}');
p.handlers.disconnect(); expect('a dropped connection is shown in red', p.$('conn').textContent === 'disconnected' && p.$('conn').className.includes('bad'));

console.log('2. no camera yet');
p = makePage(); p.handlers.view(S.no_camera);
expect('a yellow "no camera found yet" chip, a dash for the answer, no picture, and "no camera picture yet" over the frame', p.$('camera').textContent.startsWith('no camera found yet') && p.$('camera').className.includes('warn') && p.$('digit').textContent === '–' && !p.$('frame').getAttribute('src') && p.$('nopic').style.display !== 'none' && p.$('steady').textContent === 'steady answer: –');
expect('the training square is drawn where it belongs on the 640 x 480 picture (x 108, y 163, side 317, as percentages of the frame)', Math.abs(parseFloat(p.$('roi').style.left) - 100 * 108 / 640) < 0.01 && Math.abs(parseFloat(p.$('roi').style.top) - 100 * 163 / 480) < 0.01 && Math.abs(parseFloat(p.$('roi').style.width) - 100 * 317 / 640) < 0.01 && Math.abs(parseFloat(p.$('roi').style.height) - 100 * 317 / 480) < 0.01, p.$('roi').style.left + ' ' + p.$('roi').style.top);
expect('it says where the square comes from', p.$('roiSource').textContent.includes('the training square') && p.$('roiSource').textContent.includes('x 108, y 163, side 317'));
expect('the six bars are there and empty', p.d.querySelectorAll('#bars .bar').length === 6 && [...p.d.querySelectorAll('#bars .fill')].every((f) => parseFloat(f.style.width) === 0));

console.log('3. a steady answer');
p = makePage(); p.handlers.view(S.steady);
expect('the real camera picture and the 64 x 64 crop are shown (data:image/jpeg), and the "no picture" text is gone', p.$('frame').src.startsWith('data:image/jpeg;base64,') && p.$('crop').src.startsWith('data:image/jpeg;base64,') && p.$('nopic').style.display === 'none' && p.$('frame').src.length > 1000);
expect('the answer is 5, with how sure the network is, and a green "steady answer: 5" chip', p.$('digit').textContent === '5' && /^sure to \d+%$/.test(p.$('conf').textContent) && p.$('steady').textContent === 'steady answer: 5' && p.$('steady').className.includes('good'), p.$('conf').textContent);
const fills = [...p.d.querySelectorAll('#bars .fill')], rows = [...p.d.querySelectorAll('#bars .bar')];
expect('the bars follow the six probabilities (bar 5 is the longest) and the likeliest one is highlighted', pct(fills[5]) === Math.max(...fills.map(pct)) && Math.abs(pct(fills[5]) - 100 * S.steady.probs[5]) < 0.01 && rows[5].className.includes('top') && !rows[0].className.includes('top'), fills.map(pct).join(', '));
expect('the camera chip names the webcam and its device', p.$('camera').className.includes('good') && p.$('camera').textContent.includes('Diccik') && p.$('camera').textContent.includes('/dev/video3'));
expect('the speed panel shows the numbers: steps a second, camera pictures a second, the two times, and the age of the picture', p.$('fps').textContent !== '–' && p.$('camfps').textContent === '10.0' && /^\d+\.\d$/.test(p.$('prep').textContent) && /^\d+\.\d$/.test(p.$('infer').textContent) && p.$('age').textContent !== '–', [p.$('fps').textContent, p.$('prep').textContent, p.$('infer').textContent, p.$('age').textContent].join(' | '));

console.log('4. an answer that is not steady, a lost camera, a benchmark running');
p = makePage(); p.handlers.view(S.unsure);
expect('an unsure answer shows 1 but the chip says "not steady yet" in yellow', p.$('digit').textContent === '1' && p.$('steady').textContent === 'not steady yet' && p.$('steady').className.includes('warn') && p.$('conf').textContent === 'sure to 30%');
p = makePage(); p.handlers.view(S.lost); expect('a lost camera is shown in red and says what to do', p.$('camera').textContent === 'camera lost: plug it in again' && p.$('camera').className.includes('bad'));
p = makePage(); p.handlers.view(S.benchmarking);
expect('while measuring, the Benchmark button is switched off and says "Measuring…"', p.$('bench').disabled && p.$('bench').textContent === 'Measuring…');
p.click(p.$('bench')); expect('and pressing it does nothing', cmds(p).length === 0);
p.handlers.view(S.steady); expect('when the measuring ends the button comes back', !p.$('bench').disabled && p.$('bench').textContent.startsWith('Benchmark'));

console.log('4b. the camera format');
p = makePage(); p.handlers.view(S.steady);
expect('the format list shows the board\'s setting (MJPG to begin with)', p.$('fmt').value === 'MJPG' && [...p.$('fmt').options].map((o) => o.value).join() === 'MJPG,YUYV,');
p.$('fmt').value = 'YUYV'; p.click(p.$('applyFmt')); expect('Apply sends the chosen format', JSON.stringify(lastCmd(p)) === '{"action":"camera_mode","fourcc":"YUYV"}');
p.$('fmt').value = ''; p.click(p.$('applyFmt')); expect('"the camera chooses" is sent as an empty format', JSON.stringify(lastCmd(p)) === '{"action":"camera_mode","fourcc":""}');
p = makePage(); p.handlers.view(S.steady); p.$('fmt').value = 'YUYV'; p.handlers.view(S.steady); p.handlers.view(S.steady);
expect('the board repeating its setting never overwrites a choice you are making', p.$('fmt').value === 'YUYV');
const yuyv = JSON.parse(JSON.stringify(S.steady)); yuyv.camera.mode = 'YUYV'; p.handlers.view(yuyv);
expect('but when the board\'s setting changes the list follows it', p.$('fmt').value === 'YUYV' && !p.$('camera').textContent.includes('MJPG'));
const withfmt = JSON.parse(JSON.stringify(S.steady)); withfmt.camera.format = 'MJPG 640x480, the camera says 30.0 fps'; p = makePage(); p.handlers.view(withfmt);
expect('what the camera really agreed to is shown in the camera chip and under the list', p.$('camera').textContent.includes('MJPG 640x480, the camera says 30.0 fps') && p.$('fmtNote').textContent.includes('the camera says 30.0 fps'));

console.log('4c. pausing the network');
p = makePage(); p.handlers.view(S.steady);
expect('the button offers to pause the network', p.$('pauseBtn').textContent === 'Pause the network');
p.click(p.$('pauseBtn')); expect('pressing it asks the board to pause', JSON.stringify(lastCmd(p)) === '{"action":"pause","paused":true}');
p.handlers.view(S.paused);
expect('while paused: the button says Resume, the picture is still shown, there is no answer (dashes), the speed of the network steps is 0, and a note says the camera number is now the camera\'s own', p.$('pauseBtn').textContent === 'Resume the network' && p.$('frame').src.startsWith('data:image/jpeg') && p.$('digit').textContent === '–' && p.$('steady').textContent === 'steady answer: –' && p.$('fps').textContent === '0.0' && p.$('pauseNote').textContent.includes('PAUSED') && p.$('pauseNote').textContent.includes('camera'));
p.click(p.$('pauseBtn')); expect('pressing it again asks the board to resume', JSON.stringify(lastCmd(p)) === '{"action":"pause","paused":false}');
p.handlers.view(S.steady); expect('when it runs again the button goes back', p.$('pauseBtn').textContent === 'Pause the network' && p.$('digit').textContent === '5');

console.log('5. moving the square');
p = makePage(); p.handlers.view(S.steady);
[['left', '{"action":"nudge","dx":-4,"dy":0,"ds":0}'], ['right', '{"action":"nudge","dx":4,"dy":0,"ds":0}'], ['up', '{"action":"nudge","dx":0,"dy":-4,"ds":0}'], ['down', '{"action":"nudge","dx":0,"dy":4,"ds":0}'], ['smaller', '{"action":"nudge","dx":0,"dy":0,"ds":-4}'], ['bigger', '{"action":"nudge","dx":0,"dy":0,"ds":4}']].forEach(([id, want]) => {
  p.click(p.$(id)); expect('the "' + id + '" button sends ' + want, JSON.stringify(lastCmd(p)) === want, JSON.stringify(lastCmd(p)));
});
p = makePage(); p.handlers.view(S.steady); let ev = p.key(p.d.body, 'ArrowLeft');
expect('the left arrow key moves the square 4 pixels and does not scroll the page', JSON.stringify(lastCmd(p)) === '{"action":"nudge","dx":-4,"dy":0,"ds":0}' && ev.defaultPrevented);
p.key(p.d.body, 'ArrowDown', { shiftKey: true }); expect('with Shift it moves 16 pixels', JSON.stringify(lastCmd(p)) === '{"action":"nudge","dx":0,"dy":16,"ds":0}');
p.key(p.d.body, '+'); expect('+ makes it bigger by 4', JSON.stringify(lastCmd(p)) === '{"action":"nudge","dx":0,"dy":0,"ds":4}');
p.key(p.d.body, '-'); expect('- makes it smaller by 4', JSON.stringify(lastCmd(p)) === '{"action":"nudge","dx":0,"dy":0,"ds":-4}');
p.key(p.d.body, '='); p.key(p.d.body, '_'); expect('= and _ (the + and - keys without Shift) work too', cmds(p).slice(-2).map((c) => c.ds).join() === '4,-4');
const n = cmds(p).length; p.key(p.d.body, 'a'); p.key(p.d.body, 'Enter'); expect('other keys do nothing', cmds(p).length === n);
p.key(p.$('color'), 'ArrowDown'); expect('the arrow keys do not move the square while the tape-colour list has the keyboard', cmds(p).length === n);
p.click(p.$('left')); p.click(p.$('left')); expect('clicking a button takes the focus off it (a key press cannot click it again)', p.d.activeElement !== p.$('left'));

console.log('6. finding, saving and resetting the square');
p = makePage(); p.handlers.view(S.steady); p.click(p.$('find'));
expect('"Find the tape square" asks for blue by default', JSON.stringify(lastCmd(p)) === '{"action":"find_tape","color":"blue"}');
p.$('color').value = 'green'; p.click(p.$('find')); expect('with another colour chosen it asks for that colour', JSON.stringify(lastCmd(p)) === '{"action":"find_tape","color":"green"}');
p.click(p.$('save')); expect('Save sends "save_roi"', JSON.stringify(lastCmd(p)) === '{"action":"save_roi"}');
p.click(p.$('reset')); expect('"Back to the training square" sends "reset_roi"', JSON.stringify(lastCmd(p)) === '{"action":"reset_roi"}');
const moved = JSON.parse(JSON.stringify(S.steady)); moved.roi = { x: 158, y: 100, side: 200 }; moved.roi_source = 'found from the blue tape (not saved yet)'; p.handlers.view(moved);
expect('the square is redrawn where the board says it now is, and the page says it is not saved yet', Math.abs(parseFloat(p.$('roi').style.left) - 100 * 158 / 640) < 0.01 && Math.abs(parseFloat(p.$('roi').style.width) - 100 * 200 / 640) < 0.01 && p.$('roiSource').textContent.includes('not saved yet'));
const small = JSON.parse(JSON.stringify(S.steady)); small.frame = { w: 320, h: 240 }; small.roi = { x: 54, y: 82, side: 158 }; p.handlers.view(small);
expect('on a 320 x 240 camera the same square lands in the same place on the picture (percentages, not pixels)', Math.abs(parseFloat(p.$('roi').style.left) - 100 * 54 / 320) < 0.01 && Math.abs(parseFloat(p.$('roi').style.top) - 100 * 82 / 240) < 0.01);

console.log('7. the benchmark table');
p = makePage(); p.handlers.bench({ rows: S.bench_rows, csv: 'board_speed.csv' });
let trs = p.d.querySelectorAll('#benchRows tr');
expect('every benchmark is a row, the newest first (%d rows)' % S.bench_rows.length, trs.length === S.bench_rows.length && trs[0].children[1].textContent === 'camera picture' && trs[1].children[1].textContent === 'made-up picture');
const lastRow = S.bench_rows[S.bench_rows.length - 1];
expect('a row shows the time of one step, the two parts, the slow end, the steps a second, the machine and Python', trs[0].children[3].textContent === String(lastRow.total_median_ms) && trs[0].children[5].textContent === String(lastRow.infer_median_ms) && trs[0].children[8].textContent === String(lastRow.fps_estimate) && trs[0].children[9].textContent === lastRow.machine && trs[0].children[10].textContent === lastRow.python);
p.click(p.$('bench')); expect('the Benchmark button sends "benchmark"', JSON.stringify(lastCmd(p)) === '{"action":"benchmark"}');
p.click(p.$('csv'));
const csv = p.downloads.length ? decodeURIComponent(p.downloads[0].href.replace('data:text/csv;charset=utf-8,', '')) : '';
expect('a CSV file is offered with the header and one line per benchmark, with the machine and library versions', p.downloads.length === 1 && p.downloads[0].name === 'board_speed.csv' && csv.split('\n')[0] === 'time,what,frame,n,prep_median_ms,infer_median_ms,infer_p95_ms,infer_max_ms,total_median_ms,fps_estimate,machine,python,numpy,opencv' && csv.trim().split('\n').length === S.bench_rows.length + 1, csv.split('\n')[0]);
p = makePage(); p.handlers.bench({ rows: [] }); p.click(p.$('csv')); expect('with no benchmark yet nothing is downloaded, and a warning says so', p.downloads.length === 0 && p.$('notice').textContent.includes('Nothing to download'));
p = makePage(); p.handlers.bench({ rows: [{ time: '1', what: '<b>x</b>', frame: '640x480', machine: 'aarch64', python: '3.11' }] });
expect('text from the board is shown as text, never as HTML', p.d.querySelectorAll('#benchRows b').length === 0 && p.d.querySelector('#benchRows tr').children[1].textContent === '<b>x</b>');

console.log('8. messages from the board');
p = makePage(); p.handlers.notice({ level: 'ok', text: 'The square is saved (roi.json) and will be used the next time the app starts.' });
expect('a notice is shown with its colour', p.$('notice').className.includes('ok') && p.$('notice').textContent.includes('saved'));
p.handlers.notice({ level: 'warn', text: 'No blue square found in the picture.' }); expect('the next one replaces it', p.$('notice').className.includes('warn') && p.$('notice').textContent.startsWith('No blue square'));

console.log('\n' + (problems === 0 ? 'ALL PASSED' : problems + ' CHECK(S) FAILED'));
process.exit(problems ? 1 : 0);
