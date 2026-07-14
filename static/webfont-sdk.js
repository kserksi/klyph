(function (global) {
  'use strict';
  if (global.WebFont && global.WebFont.version === 2) return;

  var states = new Map();
  var excluded = 'script,style,template,noscript,[hidden],[aria-hidden="true"]';
  var sdkScript = document.currentScript;
  var defaultBaseUrl = sdkScript && sdkScript.src
    ? new URL(sdkScript.src, global.location.href).origin
    : global.location.origin;

  function normalize(text) {
    var set = new Set(Array.from((text || '').normalize('NFC')));
    return Array.from(set).filter(function (character) {
      var code = character.codePointAt(0);
      return character === ' ' || (code >= 0x20 && code !== 0x7f);
    }).sort(function (a, b) {
      return a.codePointAt(0) - b.codePointAt(0);
    }).join('');
  }

  function isExcluded(node) {
    var parent = node.parentElement;
    if (!parent || parent.closest(excluded)) return true;
    var style = global.getComputedStyle(parent);
    return style.display === 'none' || style.visibility === 'hidden';
  }

  function collect(selectors, root) {
    var text = '';
    var scope = root || document;
    var requested = selectors ? (Array.isArray(selectors) ? selectors : [selectors]) : [];
    var elements = [];
    if (!requested.length) {
      elements.push(scope === document ? document.body : scope);
    } else {
      requested.forEach(function (selector) {
        if (scope !== document && scope.matches && scope.matches(selector)) elements.push(scope);
        scope.querySelectorAll(selector).forEach(function (element) { elements.push(element); });
      });
    }
    Array.from(new Set(elements)).forEach(function (element) {
        var walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
        var node;
        while ((node = walker.nextNode())) {
          if (!isExcluded(node) && node.nodeValue) text += node.nodeValue;
        }
    });
    return normalize(text);
  }

  function stateFor(font) {
    if (!states.has(font)) states.set(font, { loaded: new Set(), requests: new Map(), faces: [] });
    return states.get(font);
  }

  function missingCharacters(state, characters) {
    return Array.from(characters).filter(function (character) {
      return !state.loaded.has(character);
    }).join('');
  }

  async function requestSubset(options, characters) {
    var baseUrl = (options.baseUrl || defaultBaseUrl).replace(/\/$/, '');
    var controller = new AbortController();
    var timeout = setTimeout(function () { controller.abort(); }, options.timeout || 8000);
    try {
      var response = await fetch(baseUrl + '/v2/subsets', {
        method: 'POST',
        mode: 'cors',
        credentials: 'omit',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({font: options.font, characters: characters}),
        signal: controller.signal
      });
      if (!response.ok) throw new Error('font subset request failed: ' + response.status);
      return response.json();
    } finally {
      clearTimeout(timeout);
    }
  }

  async function load(options) {
    if (!options || !options.font || !options.family) throw new TypeError('font and family are required');
    var characters = options.characters
      ? normalize(options.characters)
      : collect(options.selectors || (options.root ? null : 'body'), options.root);
    var state = stateFor(options.font);
    var missing = missingCharacters(state, characters);
    if (!missing) return {cached: true, characters: 0};

    var requestKey = normalize(missing);
    if (state.requests.has(requestKey)) return state.requests.get(requestKey);

    var promise = (async function () {
      var result = await requestSubset(options, requestKey);
      var face = new FontFace(options.family, 'url("' + result.url + '") format("woff2")', {
        weight: String(options.weight || result.weight || 400),
        style: options.style || result.style || 'normal',
        unicodeRange: result.unicodeRange
      });
      await face.load();
      document.fonts.add(face);
      Array.from(requestKey).forEach(function (character) { state.loaded.add(character); });
      state.faces.push(face);
      return result;
    })();

    state.requests.set(requestKey, promise);
    try {
      return await promise;
    } finally {
      state.requests.delete(requestKey);
    }
  }

  function observe(options) {
    var root = typeof options.root === 'string' ? document.querySelector(options.root) : options.root;
    if (!root) throw new Error('font observation root was not found');
    var timer = 0;
    var run = function () {
      clearTimeout(timer);
      timer = setTimeout(function () {
        load(Object.assign({}, options, {root: root})).catch(function (error) {
          if (options.onError) options.onError(error);
        });
      }, options.debounce || 800);
    };
    var observer = new MutationObserver(run);
    observer.observe(root, {childList: true, subtree: true, characterData: true});
    run();
    return {disconnect: function () { clearTimeout(timer); observer.disconnect(); }};
  }

  global.WebFont = {version: 2, load: load, observe: observe};
})(window);
