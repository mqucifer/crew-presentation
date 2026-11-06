// crew:replay-player
// The replay player: play/pause toggle, speed control (1x, 30x, 60x),
// skip-idle, timeline scrubber, event ticker, and board-state rendering.
// Vanilla JS, no framework, no build step.

(function () {
  'use strict';

  var dataEl = document.getElementById('replay-data');
  if (!dataEl) return;

  var data;
  try { data = JSON.parse(dataEl.textContent); } catch (e) { return; }

  var events = data.events || [];
  var cards = data.cards || [];

  var timelineSection = document.querySelector('[aria-label="Timeline"]');
  var boardSection = document.querySelector('[aria-label="Board"]');
  var whoSection = document.querySelector('[aria-label="Who\'s working"]');
  var tickerSection = document.querySelector('[aria-label="Event ticker"]');

  // --- Ensure standard columns exist in the board ---
  var STANDARD_COLUMNS = ['In Progress', 'Reviewing', 'QAing', 'Merging', 'Done'];
  function ensureColumns() {
    if (!boardSection) return;
    var existing = {};
    boardSection.querySelectorAll('.replay-col__header').forEach(function (h) {
      existing[h.textContent.trim()] = true;
    });
    for (var i = 0; i < STANDARD_COLUMNS.length; i++) {
      var name = STANDARD_COLUMNS[i];
      if (!existing[name]) {
        var col = document.createElement('div');
        col.className = 'replay-col';
        var h = document.createElement('div');
        h.className = 'replay-col__header';
        h.textContent = name;
        var c = document.createElement('div');
        c.className = 'replay-col__cards';
        col.appendChild(h);
        col.appendChild(c);
        boardSection.appendChild(col);
      }
    }
  }
  ensureColumns();

  // --- Capture initial board state (for seek/reset) ---
  var initialState = {};
  if (boardSection) {
    boardSection.querySelectorAll('.replay-col').forEach(function (col) {
      var h = col.querySelector('.replay-col__header');
      if (!h) return;
      var name = h.textContent.trim();
      var cardsDiv = col.querySelector('.replay-col__cards');
      var entries = [];
      if (cardsDiv) {
        cardsDiv.querySelectorAll('.replay-card').forEach(function (card) {
          entries.push(card.cloneNode(true));
        });
      }
      initialState[name] = entries;
    });
  }

  // --- State ---
  var currentIndex = 0;
  var playing = false;
  var speed = 30;
  var skipIdle = false;
  var timer = null;

  // --- Controls ---
  var playBtn = null;
  var scrubberTrack = null;
  var scrubberProgress = null;

  function createControls() {
    if (!events.length) return;

    var container = document.createElement('div');
    container.className = 'replay-controls';

    playBtn = document.createElement('button');
    playBtn.type = 'button';
    playBtn.className = 'replay-controls__play';
    playBtn.setAttribute('aria-label', 'Play');
    playBtn.textContent = '\u25B6';
    playBtn.addEventListener('click', function () {
      if (playing) { pause(); } else { play(); }
    });
    container.appendChild(playBtn);

    var speedGroup = document.createElement('div');
    speedGroup.className = 'replay-controls__speed';
    speedGroup.setAttribute('role', 'group');
    speedGroup.setAttribute('aria-label', 'Speed');

    ['1', '30', '60'].forEach(function (s) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'replay-controls__speed-btn' + (parseInt(s, 10) === speed ? ' is-active' : '');
      btn.textContent = s + '\u00D7';
      btn.addEventListener('click', function () {
        speed = parseInt(s, 10);
        speedGroup.querySelectorAll('.replay-controls__speed-btn').forEach(function (b) {
          b.classList.remove('is-active');
        });
        btn.classList.add('is-active');
      });
      speedGroup.appendChild(btn);
    });

    var skipBtn = document.createElement('button');
    skipBtn.type = 'button';
    skipBtn.className = 'replay-controls__skip';
    skipBtn.textContent = 'skip idle';
    skipBtn.setAttribute('aria-pressed', 'false');
    skipBtn.addEventListener('click', function () {
      skipIdle = !skipIdle;
      skipBtn.setAttribute('aria-pressed', String(skipIdle));
      skipBtn.classList.toggle('is-active', skipIdle);
    });
    speedGroup.appendChild(skipBtn);

    container.appendChild(speedGroup);

    if (timelineSection) {
      timelineSection.parentNode.insertBefore(container, timelineSection);
    }
  }

  function createScrubber() {
    if (!timelineSection || !events.length) return;

    var scrubber = document.createElement('div');
    scrubber.className = 'replay-scrubber';

    scrubberTrack = document.createElement('div');
    scrubberTrack.className = 'replay-scrubber__track';

    scrubberProgress = document.createElement('div');
    scrubberProgress.className = 'replay-scrubber__progress';
    scrubberProgress.style.width = '0%';

    scrubberTrack.appendChild(scrubberProgress);
    scrubber.appendChild(scrubberTrack);

    scrubberTrack.addEventListener('click', function (e) {
      var rect = scrubberTrack.getBoundingClientRect();
      if (rect.width === 0) return;
      var ratio = (e.clientX - rect.left) / rect.width;
      seek(Math.min(Math.floor(ratio * events.length), events.length - 1));
    });

    timelineSection.appendChild(scrubber);
  }

  function renderWho() {
    if (!whoSection || !events.length) return;
    var entry = document.createElement('div');
    entry.className = 'who-entry';
    entry.textContent = 'Ready';
    whoSection.appendChild(entry);
  }

  function addTickerPlaceholder() {
    if (!tickerSection || !events.length) return;
    var row = document.createElement('div');
    row.className = 'ticker-row ticker-row--placeholder';
    row.textContent = 'Ready';
    tickerSection.appendChild(row);
  }

  // --- Playback helpers ---

  function formatTime(iso) {
    if (!iso) return '';
    var m = iso.match(/T(\d{2}:\d{2})/);
    return m ? m[1] : '';
  }

  function formatEventText(ev) {
    var num = ev.card ? '#' + ev.card.number : '';
    var col = ev.to_column || '';
    var role = ev.role || '';
    if (ev.kind === 'move' || ev.kind === 'card_moved') {
      return (role ? role + ' ' : '') + 'moves ' + num + ' to ' + col;
    }
    if (ev.kind === 'merge') {
      return num + ' merged to ' + col;
    }
    return (num ? num + ' ' : '') + (ev.kind || 'event').replace(/_/g, ' ');
  }

  function findColumnCards(colName) {
    if (!boardSection || !colName) return null;
    var headers = boardSection.querySelectorAll('.replay-col__header');
    for (var i = 0; i < headers.length; i++) {
      if (headers[i].textContent.trim() === colName) {
        return headers[i].parentElement.querySelector('.replay-col__cards');
      }
    }
    return null;
  }

  function findCardIn(cardsDiv, cardNum) {
    if (!cardsDiv || cardNum == null) return null;
    var cards = cardsDiv.querySelectorAll('.replay-card');
    for (var i = 0; i < cards.length; i++) {
      if (cards[i].textContent.indexOf('#' + cardNum) !== -1) return cards[i];
    }
    return null;
  }

  function createCardEl(cardNum) {
    var el = document.createElement('div');
    el.className = 'replay-card';
    var numSpan = document.createElement('span');
    numSpan.className = 'num meta';
    numSpan.textContent = '#' + cardNum;
    el.appendChild(numSpan);
    for (var i = 0; i < cards.length; i++) {
      if (cards[i].number === cardNum && cards[i].title) {
        var titleSpan = document.createElement('span');
        titleSpan.textContent = cards[i].title;
        el.appendChild(titleSpan);
        break;
      }
    }
    return el;
  }

  function processEvent(idx) {
    var ev = events[idx];
    var cardNum = ev.card ? ev.card.number : null;
    var fromCol = ev.from_column;
    var toCol = ev.to_column;

    // Move card in the board
    if (cardNum != null && toCol) {
      if (fromCol) {
        var srcDiv = findColumnCards(fromCol);
        if (srcDiv) {
          var cardEl = findCardIn(srcDiv, cardNum);
          if (cardEl) srcDiv.removeChild(cardEl);
        }
      }
      var dstDiv = findColumnCards(toCol);
      if (dstDiv) {
        dstDiv.appendChild(createCardEl(cardNum));
      }
    }

    // Ticker
    if (tickerSection) {
      var placeholder = tickerSection.querySelector('.ticker-row--placeholder');
      if (placeholder) placeholder.remove();

      var row = document.createElement('div');
      row.className = 'ticker-row';
      var timeSpan = document.createElement('span');
      timeSpan.className = 'ticker-row__time';
      timeSpan.textContent = formatTime(ev.at);
      var textSpan = document.createElement('span');
      textSpan.className = 'ticker-row__text';
      textSpan.textContent = formatEventText(ev);
      row.appendChild(timeSpan);
      row.appendChild(textSpan);
      tickerSection.appendChild(row);

      var rows = tickerSection.querySelectorAll('.ticker-row');
      while (rows.length > 5) {
        rows[0].remove();
      }
    }

    // Scrubber
    if (scrubberProgress) {
      scrubberProgress.style.width = ((idx + 1) / events.length * 100) + '%';
    }

    // Who's working
    if (whoSection && ev.role) {
      var entry = whoSection.querySelector('[data-role="' + ev.role + '"]');
      if (!entry) {
        entry = document.createElement('div');
        entry.className = 'who-entry';
        entry.setAttribute('data-role', ev.role);
        whoSection.appendChild(entry);
      }
      var num = ev.card ? '#' + ev.card.number : '';
      entry.textContent = ev.role + (num ? ' \u00B7 ' + num : '');
    }
  }

  function tick() {
    if (!playing) return;
    if (currentIndex >= events.length) {
      pause();
      return;
    }
    processEvent(currentIndex);
    currentIndex++;
    if (currentIndex < events.length) {
      var delay = skipIdle ? 1 : 1000 / speed;
      timer = setTimeout(tick, delay);
    }
  }

  function play() {
    if (playing || !events.length) return;
    if (tickerSection) {
      var ph = tickerSection.querySelector('.ticker-row--placeholder');
      if (ph) ph.remove();
    }
    playing = true;
    if (playBtn) {
      playBtn.setAttribute('aria-label', 'Pause');
      playBtn.textContent = '\u23F8';
    }
    tick();
  }

  function pause() {
    playing = false;
    if (timer) { clearTimeout(timer); timer = null; }
    if (playBtn) {
      playBtn.setAttribute('aria-label', 'Play');
      playBtn.textContent = '\u25B6';
    }
  }

  function finish() {
    pause();
    while (currentIndex < events.length) {
      processEvent(currentIndex);
      currentIndex++;
    }
  }

  function seek(idx) {
    pause();
    resetBoard();
    currentIndex = 0;
    if (tickerSection) {
      tickerSection.querySelectorAll('.ticker-row').forEach(function (r) { r.remove(); });
    }
    if (whoSection) {
      whoSection.querySelectorAll('.who-entry[data-role]').forEach(function (e) { e.remove(); });
    }
    var target = Math.min(idx, events.length);
    while (currentIndex < target) {
      processEvent(currentIndex);
      currentIndex++;
    }
  }

  function resetBoard() {
    if (!boardSection) return;
    boardSection.querySelectorAll('.replay-col').forEach(function (col) {
      var h = col.querySelector('.replay-col__header');
      if (!h) return;
      var name = h.textContent.trim();
      var cardsDiv = col.querySelector('.replay-col__cards');
      if (!cardsDiv) return;
      cardsDiv.innerHTML = '';
      var initial = initialState[name];
      if (initial) {
        initial.forEach(function (el) {
          cardsDiv.appendChild(el.cloneNode(true));
        });
      }
    });
  }

  // --- Init ---
  createControls();
  createScrubber();
  renderWho();
  addTickerPlaceholder();

  // Expose API
  window.replay = {
    play: play,
    pause: pause,
    finish: finish,
    seek: seek,
  };
})();
