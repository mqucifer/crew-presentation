// crew:placeholder
// The replay player: play/pause toggle, speed control (1x, 30x, 60x),
// skip-idle, timeline scrubber, event ticker, and board-state rendering.
// Vanilla JS, no framework, no build step.

(function () {
  'use strict';

  var dataEl = document.getElementById('replay-data');
  if (!dataEl) return;

  var data;
  try {
    data = JSON.parse(dataEl.textContent);
  } catch (e) {
    return;
  }
  var events = data.events || [];
  var cards = data.cards || [];

  var controlsEl = document.getElementById('replay-controls');
  var timelineEl = document.getElementById('replay-timeline');
  var whoEl = document.getElementById('replay-who');
  var tickerEl = document.getElementById('replay-ticker');
  var boardEl = document.getElementById('replay-board');

  if (!controlsEl || !timelineEl || !tickerEl) return;

  // ---- Time model ----
  var eventTimes = events.map(function (e) {
    return new Date(e.at).getTime();
  });
  var timeStart = eventTimes.length > 0 ? eventTimes[0] : 0;
  var timeEnd = eventTimes.length > 0 ? eventTimes[eventTimes.length - 1] : 0;
  var totalDuration = timeEnd - timeStart;

  var virtualTime = timeStart;
  var currentIndex = 0;
  var playing = false;
  var speed = 1;
  var skipIdle = false;
  var animFrame = null;
  var lastRealTime = 0;

  // ---- Board indexing ----
  var cardElements = {};
  var columnElements = {};
  var initialBoardHTML = '';
  var initialWhoHTML = '';

  function indexColumns() {
    columnElements = {};
    if (!boardEl) return;
    var cols = boardEl.querySelectorAll('.replay-col');
    for (var i = 0; i < cols.length; i++) {
      var colEl = cols[i];
      var header = colEl.querySelector('.replay-col__header');
      if (!header) continue;
      var name = header.textContent.trim();
      columnElements[name] = {
        col: colEl,
        cards: colEl.querySelector('.replay-col__cards'),
      };
    }
  }

  function indexCards() {
    cardElements = {};
    if (!boardEl) return;
    var cardEls = boardEl.querySelectorAll('.replay-card');
    for (var i = 0; i < cardEls.length; i++) {
      var cardEl = cardEls[i];
      var link = cardEl.querySelector('a.num');
      if (!link) continue;
      var text = link.textContent || '';
      var hashIdx = text.lastIndexOf('#');
      if (hashIdx === -1) continue;
      var num = parseInt(text.substring(hashIdx + 1), 10);
      if (!isNaN(num)) {
        cardElements[num] = cardEl;
      }
    }
  }

  function moveCard(cardNumber, toColumn) {
    var cardEl = cardElements[cardNumber];
    if (!cardEl) return;
    var colInfo = columnElements[toColumn];
    if (!colInfo || !colInfo.cards) return;
    colInfo.cards.appendChild(cardEl);
  }

  // ---- Helpers ----
  function formatTime(isoString) {
    var match = isoString.match(/T(\d{2}):(\d{2})/);
    if (match) return match[1] + ':' + match[2];
    return '';
  }

  function esc(s) {
    var d = document.createElement('span');
    d.textContent = s;
    return d.innerHTML;
  }

  // ---- Ticker ----
  function addTickerRow(time, text, emphasis) {
    var row = document.createElement('div');
    row.className = 'ticker-row' + (emphasis ? ' ticker-row--emphasis' : '');
    var timeEl = document.createElement('span');
    timeEl.className = 'ticker-time num';
    timeEl.textContent = time;
    var textEl = document.createElement('span');
    textEl.className = 'ticker-text';
    textEl.textContent = text;
    row.appendChild(timeEl);
    row.appendChild(textEl);
    tickerEl.appendChild(row);
  }

  function clearTicker() {
    if (tickerEl) tickerEl.innerHTML = '';
  }

  // ---- Who's working ----
  function updateWho(event) {
    if (!whoEl) return;
    var role = event.role || event.by;
    if (!role) return;
    var cardRef = event.card;
    var cardNum = cardRef && cardRef.number != null ? '#' + cardRef.number : '';

    var entry = whoEl.querySelector('[data-role="' + esc(role) + '"]');
    if (!entry) {
      entry = document.createElement('div');
      entry.className = 'who-entry';
      entry.setAttribute('data-role', role);
      var avatar = document.createElement('span');
      avatar.className = 'who-avatar';
      avatar.setAttribute('aria-hidden', 'true');
      avatar.textContent = role
        .replace(/[^A-Z]/g, '')
        .substring(0, 2)
        .toUpperCase();
      var nameEl = document.createElement('span');
      nameEl.className = 'who-name';
      nameEl.textContent = role;
      var cardEl = document.createElement('span');
      cardEl.className = 'who-card num';
      entry.appendChild(avatar);
      entry.appendChild(nameEl);
      entry.appendChild(cardEl);
      whoEl.appendChild(entry);
    }
    var cardSpan = entry.querySelector('.who-card');
    if (cardSpan && cardNum) {
      cardSpan.textContent = cardNum;
    }
  }

  function initWho() {
    if (!whoEl) return;
    if (events.length === 0) {
      var empty = document.createElement('div');
      empty.className = 'who-empty';
      empty.textContent = 'No activity';
      whoEl.appendChild(empty);
    } else {
      var firstEvent = events[0];
      var role = firstEvent.role || firstEvent.by;
      if (role) {
        var entry = document.createElement('div');
        entry.className = 'who-entry who-entry--placeholder';
        entry.setAttribute('data-role', role);
        var avatar = document.createElement('span');
        avatar.className = 'who-avatar';
        avatar.setAttribute('aria-hidden', 'true');
        avatar.textContent = role
          .replace(/[^A-Z]/g, '')
          .substring(0, 2)
          .toUpperCase();
        var nameEl = document.createElement('span');
        nameEl.className = 'who-name';
        nameEl.textContent = role;
        entry.appendChild(avatar);
        entry.appendChild(nameEl);
        whoEl.appendChild(entry);
      } else {
        var placeholder = document.createElement('div');
        placeholder.className = 'who-empty';
        placeholder.textContent = 'Press play to start';
        whoEl.appendChild(placeholder);
      }
    }
  }

  function resetWho() {
    if (!whoEl) return;
    var saved = initialWhoHTML;
    whoEl.innerHTML = saved;
  }

  // ---- Timeline ----
  function initTimeline() {
    if (!timelineEl) return;
    if (events.length === 0) {
      var empty = document.createElement('div');
      empty.className = 'timeline-empty';
      empty.textContent = 'No events to replay';
      timelineEl.appendChild(empty);
      return;
    }
    var bar = document.createElement('div');
    bar.className = 'timeline-bar';
    var track = document.createElement('div');
    track.className = 'timeline-track';
    var progress = document.createElement('div');
    progress.className = 'timeline-progress';
    progress.id = 'replay-timeline-progress';
    track.appendChild(progress);
    var dots = document.createElement('div');
    dots.className = 'timeline-dots';
    for (var i = 0; i < events.length; i++) {
      var t = eventTimes[i];
      var fraction =
        totalDuration > 0 ? (t - timeStart) / totalDuration : 0;
      var dot = document.createElement('div');
      dot.className = 'timeline-dot';
      dot.style.left = (fraction * 100) + '%';
      dots.appendChild(dot);
    }
    track.appendChild(dots);
    bar.appendChild(track);
    timelineEl.appendChild(bar);
    var labels = document.createElement('div');
    labels.className = 'timeline-labels';
    var startLabel = document.createElement('span');
    startLabel.className = 'num';
    startLabel.textContent = formatTime(events[0].at);
    var endLabel = document.createElement('span');
    endLabel.className = 'num';
    endLabel.textContent = formatTime(events[events.length - 1].at);
    labels.appendChild(startLabel);
    labels.appendChild(endLabel);
    timelineEl.appendChild(labels);
  }

  // ---- Ticker init ----
  function initTicker() {
    if (!tickerEl) return;
    if (events.length > 0) {
      var placeholder = document.createElement('div');
      placeholder.className = 'ticker-row ticker-row--placeholder';
      placeholder.id = 'replay-ticker-placeholder';
      var text = document.createElement('span');
      text.className = 'ticker-text';
      text.textContent = 'Press play to watch the day unfold';
      placeholder.appendChild(text);
      tickerEl.appendChild(placeholder);
    }
  }

  // ---- Controls ----
  function createControls() {
    if (!controlsEl) return;

    var playBtn = document.createElement('button');
    playBtn.type = 'button';
    playBtn.className = 'replay-play';
    playBtn.id = 'replay-play-btn';
    playBtn.setAttribute('aria-label', 'Play');
    playBtn.innerHTML =
      '<svg width="18" height="18" viewBox="0 0 18 18" fill="currentColor" aria-hidden="true"><polygon points="4,2 16,9 4,16"/></svg>';
    controlsEl.appendChild(playBtn);

    var speedGroup = document.createElement('div');
    speedGroup.className = 'replay-speed-group';
    speedGroup.setAttribute('role', 'group');
    speedGroup.setAttribute('aria-label', 'Speed');

    var speeds = [1, 30, 60];
    for (var i = 0; i < speeds.length; i++) {
      var s = speeds[i];
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'replay-speed-btn';
      btn.setAttribute('data-speed', String(s));
      btn.textContent = s + '\u00D7';
      if (s === 1) btn.setAttribute('aria-pressed', 'true');
      speedGroup.appendChild(btn);
    }

    var skipBtn = document.createElement('button');
    skipBtn.type = 'button';
    skipBtn.className = 'replay-skip-idle';
    skipBtn.setAttribute('aria-pressed', 'false');
    skipBtn.textContent = 'skip idle';
    speedGroup.appendChild(skipBtn);

    controlsEl.appendChild(speedGroup);

    var scrubber = document.createElement('input');
    scrubber.type = 'range';
    scrubber.className = 'replay-scrubber';
    scrubber.id = 'replay-scrubber';
    scrubber.min = '0';
    scrubber.max = '1000';
    scrubber.value = '0';
    scrubber.setAttribute('aria-label', 'Timeline position');
    controlsEl.appendChild(scrubber);

    playBtn.addEventListener('click', function () {
      if (playing) {
        pause();
      } else {
        play();
      }
    });

    var speedBtns = speedGroup.querySelectorAll('.replay-speed-btn');
    for (var j = 0; j < speedBtns.length; j++) {
      speedBtns[j].addEventListener('click', function () {
        var newSpeed = parseInt(this.getAttribute('data-speed'), 10);
        for (var k = 0; k < speedBtns.length; k++) {
          speedBtns[k].setAttribute('aria-pressed', 'false');
        }
        this.setAttribute('aria-pressed', 'true');
        speed = newSpeed;
      });
    }

    skipBtn.addEventListener('click', function () {
      skipIdle = !skipIdle;
      skipBtn.setAttribute('aria-pressed', String(skipIdle));
    });

    scrubber.addEventListener('input', function () {
      var fraction = parseInt(scrubber.value, 10) / 1000;
      seek(fraction);
    });
  }

  // ---- Progress update ----
  function updateProgress() {
    var fraction =
      totalDuration > 0 ? (virtualTime - timeStart) / totalDuration : 0;
    var clamped = Math.max(0, Math.min(1, fraction));
    var scrubber = document.getElementById('replay-scrubber');
    if (scrubber) scrubber.value = String(Math.round(clamped * 1000));
    var progress = document.getElementById('replay-timeline-progress');
    if (progress) progress.style.width = (clamped * 100) + '%';
  }

  // ---- Event processing ----
  function processEvent(event) {
    var time = formatTime(event.at);
    var cardRef = event.card;

    if (cardRef && cardRef.number != null) {
      var cardNum = cardRef.number;
      var cardLabel = '#' + cardNum;
      var roleText = event.role || event.by || '';
      var roleSuffix = roleText ? ' · ' + roleText : '';

      if (event.from_column && event.to_column) {
        moveCard(cardNum, event.to_column);
        addTickerRow(
          time,
          cardLabel + ' moved to ' + event.to_column + roleSuffix,
          false
        );
      } else if (event.kind === 'pull_merged') {
        addTickerRow(time, cardLabel + ' merged' + roleSuffix, true);
      } else {
        addTickerRow(time, cardLabel + roleSuffix, false);
      }
    }

    updateWho(event);
  }

  // ---- Playback engine ----
  function tick(realTimestamp) {
    if (!playing) return;

    if (lastRealTime === 0) {
      lastRealTime = realTimestamp;
      animFrame = requestAnimationFrame(tick);
      return;
    }

    var deltaReal = (realTimestamp - lastRealTime) / 1000;
    lastRealTime = realTimestamp;

    var effectiveSpeed = skipIdle ? speed * 10 : speed;
    var deltaVirtual = deltaReal * effectiveSpeed * 1000;
    virtualTime += deltaVirtual;

    while (
      currentIndex < events.length &&
      eventTimes[currentIndex] <= virtualTime
    ) {
      processEvent(events[currentIndex]);
      currentIndex++;
    }

    updateProgress();

    if (currentIndex >= events.length) {
      pause();
      return;
    }

    animFrame = requestAnimationFrame(tick);
  }

  function setPlayButton(playing) {
    var playBtn = document.getElementById('replay-play-btn');
    if (!playBtn) return;
    if (playing) {
      playBtn.setAttribute('aria-label', 'Pause');
      playBtn.innerHTML =
        '<svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><line x1="6" y1="3" x2="6" y2="15"></line><line x1="12" y1="3" x2="12" y2="15"></line></svg>';
    } else {
      playBtn.setAttribute('aria-label', 'Play');
      playBtn.innerHTML =
        '<svg width="18" height="18" viewBox="0 0 18 18" fill="currentColor" aria-hidden="true"><polygon points="4,2 16,9 4,16"/></svg>';
    }
  }

  function play() {
    if (playing) return;

    var placeholder = document.getElementById('replay-ticker-placeholder');
    if (placeholder) placeholder.remove();

    if (currentIndex >= events.length && events.length > 0) {
      resetBoard();
      resetWho();
      clearTicker();
      currentIndex = 0;
      virtualTime = timeStart;
    }

    playing = true;
    lastRealTime = 0;
    setPlayButton(true);
    animFrame = requestAnimationFrame(tick);
  }

  function pause() {
    if (!playing) return;
    playing = false;
    if (animFrame) {
      cancelAnimationFrame(animFrame);
      animFrame = null;
    }
    setPlayButton(false);
  }

  function finish() {
    pause();
    var placeholder = document.getElementById('replay-ticker-placeholder');
    if (placeholder) placeholder.remove();
    while (currentIndex < events.length) {
      processEvent(events[currentIndex]);
      currentIndex++;
    }
    virtualTime = timeEnd;
    updateProgress();
  }

  function seek(fraction) {
    pause();
    virtualTime = timeStart + fraction * totalDuration;
    resetBoard();
    resetWho();
    clearTicker();

    currentIndex = 0;
    while (
      currentIndex < events.length &&
      eventTimes[currentIndex] <= virtualTime
    ) {
      processEvent(events[currentIndex]);
      currentIndex++;
    }

    updateProgress();
  }

  function resetBoard() {
    if (boardEl && initialBoardHTML) {
      boardEl.innerHTML = initialBoardHTML;
      indexColumns();
      indexCards();
    }
  }

  // ---- Init ----
  function init() {
    indexColumns();
    indexCards();
    createControls();
    initTimeline();
    initWho();
    initTicker();
    initialBoardHTML = boardEl ? boardEl.innerHTML : '';
    initialWhoHTML = whoEl ? whoEl.innerHTML : '';
  }

  // Expose the API
  window.replay = {
    play: play,
    pause: pause,
    finish: finish,
    seek: seek,
  };

  init();
})();
