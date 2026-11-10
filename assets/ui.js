/* Shared UI layer: light/dark theme, Ukrainian/Czech language, sliding thumbs on segmented controls */
(function(){
  var root = document.documentElement;
  var THEME_KEY = 'dvur-theme', LANG_KEY = 'dvur-lang';
  var reduce = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  var tgApp = window.Telegram && window.Telegram.WebApp;
  var tg = (tgApp && tgApp.platform && tgApp.platform !== 'unknown') ? tgApp : null;
  function get(k){ try { return localStorage.getItem(k); } catch(e){ return null; } }
  function put(k, v){ try { localStorage.setItem(k, v); } catch(e){} }
  function haptic(kind){ try { if (tg && tg.HapticFeedback){ if (kind) tg.HapticFeedback.impactOccurred(kind); else tg.HapticFeedback.selectionChanged(); } } catch(e){} }

  /* language: saved choice, else the Telegram account's language, else the browser's; anything but Czech -> Ukrainian */
  function defaultLang(){
    var code = '';
    try { code = (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.language_code) || ''; } catch(e){}
    if (!code) code = (navigator.language || '');
    return /^(cs|sk)/i.test(code) ? 'cs' : 'uk';
  }
  var lang = get(LANG_KEY);
  if (lang !== 'uk' && lang !== 'cs') lang = defaultLang();
  root.lang = lang;
  var LABELS = {
    uk: {dark: 'Увімкнути темну тему', light: 'Увімкнути світлу тему'},
    cs: {dark: 'Zapnout tmavý režim', light: 'Zapnout světlý režim'}
  };

  /* theme */
  function systemTheme(){ return (window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light'; }
  function current(){ return root.getAttribute('data-theme') || systemTheme(); }
  function paintTg(){
    if (!tg) return;
    try {
      var bg = getComputedStyle(root).getPropertyValue('--bg').trim();
      if (!bg) return;
      if (tg.setHeaderColor) tg.setHeaderColor(bg);
      if (tg.setBackgroundColor) tg.setBackgroundColor(bg);
    } catch(e){}
  }
  function label(){
    var b = document.getElementById('themebtn'); if (!b) return;
    var text = LABELS[lang][current() === 'dark' ? 'light' : 'dark'];
    b.setAttribute('aria-label', text); b.setAttribute('title', text);
  }
  function setTheme(t, animate){
    var apply = function(){ root.setAttribute('data-theme', t); label(); paintTg(); };
    if (root.getAttribute('data-theme') === t){ label(); paintTg(); return; }
    if (!animate || reduce){ apply(); return; }
    if (document.startViewTransition){ try { document.startViewTransition(apply); return; } catch(e){} }
    root.classList.add('theme-fade');
    apply();
    setTimeout(function(){ root.classList.remove('theme-fade'); }, 480);
  }
  function sync(animate){
    var t = get(THEME_KEY) || (tg ? (tg.colorScheme === 'dark' ? 'dark' : 'light') : systemTheme());
    setTheme(t, animate);
  }

  /* segmented controls: the thumb sits under the pressed button */
  function place(seg, instant){
    if (!seg) return;
    var thumb = seg.querySelector('.thumb'), active = seg.querySelector('[aria-pressed="true"]');
    if (!thumb || !active) return;
    if (instant) seg.classList.add('no-anim');
    thumb.style.width = active.offsetWidth + 'px';
    thumb.style.transform = 'translateX(' + active.offsetLeft + 'px)';
    if (instant){ void thumb.offsetWidth; seg.classList.remove('no-anim'); }
  }
  function placeAll(instant){ Array.prototype.forEach.call(document.querySelectorAll('.seg'), function(s){ place(s, instant); }); }
  function press(seg, attr, value){
    Array.prototype.forEach.call(seg.querySelectorAll('button[' + attr + ']'), function(b){ b.setAttribute('aria-pressed', String(b.getAttribute(attr) === value)); });
    place(seg);
  }

  function setLang(l){
    if (l === lang) return;
    lang = l; root.lang = l; put(LANG_KEY, l);
    var seg = document.querySelector('.seg.lang'); if (seg) press(seg, 'data-lang', l);
    label();
    document.dispatchEvent(new CustomEvent('langchange', {detail: l}));
  }

  function init(){
    // iOS Safari and Telegram on iPhone apply :active (the pressed look) only when a touch listener exists
    document.addEventListener('touchstart', function(){}, {passive: true});
    var b = document.getElementById('themebtn');
    if (b) b.addEventListener('click', function(){
      var t = current() === 'dark' ? 'light' : 'dark';
      put(THEME_KEY, t); setTheme(t, true); haptic('light');
    });
    if (window.matchMedia){
      var mq = matchMedia('(prefers-color-scheme: dark)');
      var onSys = function(){ if (!get(THEME_KEY) && !tg) setTheme(systemTheme(), true); };
      if (mq.addEventListener) mq.addEventListener('change', onSys); else if (mq.addListener) mq.addListener(onSys);
    }
    if (tg){ try { tg.onEvent('themeChanged', function(){ if (!get(THEME_KEY)) sync(true); else paintTg(); }); } catch(e){} }
    sync(false);

    var ls = document.querySelector('.seg.lang');
    if (ls){
      press(ls, 'data-lang', lang);
      ls.addEventListener('click', function(e){
        var btn = e.target.closest('button[data-lang]'); if (!btn) return;
        setLang(btn.getAttribute('data-lang')); haptic();
      });
    }
    placeAll(true);
    window.addEventListener('resize', function(){ placeAll(true); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function(){ placeAll(true); });
  }

  window.UI = { lang: function(){ return lang; }, setLang: setLang, press: press, place: place, haptic: haptic, tg: tg, reduce: reduce };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
