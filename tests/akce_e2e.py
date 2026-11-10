"""The deals page in headless Chrome.

  python3 tests/akce_e2e.py           page checks, no internet needed
  python3 tests/akce_e2e.py --live    also opens every flyer link on the chains' sites
                                      (CHROME=/path/to/chrome to use a system browser)

Covers: the right chains and stores per category, the category and language choices are remembered,
Czech is picked for a Czech Telegram account, the product search and the word chips open kupi.cz,
every link goes to an official chain domain (or Google Maps) and opens in a new tab, inside Telegram
links open in the phone's browser, and the page fits a 340 px screen. Exits 1 if a check fails.
"""
import asyncio, functools, http.server, os, re, sys, threading, urllib.request
from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OFFICIAL = (r'^https://(prodejny\.kaufland\.cz|www\.lidl\.cz|www\.itesco\.cz|www\.billa\.cz|www\.penny\.cz|www\.coopclub\.cz|'
            r'www\.dm\.cz|www\.rossmann\.cz|www\.tetadrogerie\.cz|www\.action\.com)/')
MAPS = r'^https://www\.google\.com/maps/search/\?api=1&query=.+Dv%C5%AFr%20Kr%C3%A1lov%C3%A9%20nad%20Labem$'
def tg_stub(lang):
    return ("window.Telegram = {WebApp: {platform: 'android', colorScheme: 'light', initData: 'x', initDataUnsafe: {user: {id: 1, language_code: '" + lang + "'}},"
            " ready() {}, expand() {}, onEvent() {}, setHeaderColor() {}, setBackgroundColor() {}, openLink(u) { window.__opened = u; },"
            " HapticFeedback: {selectionChanged() {}, impactOccurred() {}, notificationOccurred() {}}}};")
fails = []

def check(name, ok, detail=''):
    print(('PASS ' if ok else 'FAIL ') + name + (f'  ({detail})' if detail else ''))
    if not ok: fails.append(name)

def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=ROOT))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f'http://127.0.0.1:{srv.server_address[1]}/'

STATE = """() => [...document.querySelectorAll('.chain')].map(c => ({name: c.querySelector('h2').textContent,
  stores: c.querySelectorAll('.store').length, storeLinks: c.querySelectorAll('.store a.go').length, pins: c.querySelectorAll('.store a.pin').length,
  chainLink: !!c.querySelector(':scope > a.go')}))"""
LINKS = "() => [...document.querySelectorAll('#list a, #find a')].map(a => [a.href, a.target, a.rel])"

async def newctx(browser, tg_lang=None, width=340, tz=None):
    ctx = await browser.new_context(viewport={'width': width, 'height': 760}, timezone_id=tz)
    body = tg_stub(tg_lang) if tg_lang else ''
    await ctx.route('**/telegram.org/**', lambda r: r.fulfill(body=body, content_type='text/javascript'))
    await ctx.route('**/fonts.googleapis.com/**', lambda r: r.fulfill(body='', content_type='text/css'))
    await ctx.add_init_script('window.open = (u) => { window.__opened = u; return {}; };')
    pg = await ctx.new_page(); pg.on('pageerror', lambda e: fails.append(f'page error: {e}'))
    return ctx, pg

async def main():
    url = serve()
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=os.environ.get('CHROME') or None, args=['--no-sandbox'])
        ctx, pg = await newctx(browser)
        await pg.goto(url); await pg.wait_for_timeout(300)

        food = {c['name']: c for c in await pg.evaluate(STATE)}
        check('Ukrainian by default outside Telegram', await pg.get_attribute('html', 'lang') == 'uk' and await pg.text_content('h1') == 'Акції тижня')
        check('food: chains', list(food) == ['Kaufland', 'Lidl', 'Tesco', 'BILLA', 'PENNY', 'COOP'], str(list(food)))
        check('food: COOP has a flyer per store, the rest one per chain',
              food['COOP']['storeLinks'] == 2 and not food['COOP']['chainLink'] and all(food[n]['chainLink'] and not food[n]['storeLinks'] for n in food if n != 'COOP'))
        check('every store has a map pin', all(c['pins'] == c['stores'] for c in food.values()))
        check('fits 340 px, no sideways scrolling', await pg.evaluate('document.documentElement.scrollWidth') <= 340)
        links = await pg.evaluate(LINKS)

        await pg.click('#cats button[data-cat="drug"]')
        drug = {c['name']: c for c in await pg.evaluate(STATE)}
        check('drugstores: dm, Rossmann, two Teta', list(drug) == ['dm', 'ROSSMANN', 'Teta'] and drug['Teta']['stores'] == 2, str(drug))
        links += await pg.evaluate(LINKS)
        await pg.click('#cats button[data-cat="home"]')
        home = [c['name'] for c in await pg.evaluate(STATE)]
        check('home: Action', home == ['Action'], str(home))
        links += await pg.evaluate(LINKS)
        thumb = await pg.evaluate("(() => { const s = document.getElementById('cats'), t = s.querySelector('.thumb'), b = s.querySelector('[aria-pressed=true]'); return [t.style.width, b.offsetWidth + 'px']; })()")
        check('category thumb sits under the chosen tab', thumb[0] == thumb[1], str(thumb))

        await pg.click('.seg.lang button[data-lang="cs"]'); await pg.wait_for_timeout(200)
        cs = await pg.evaluate("({lang: document.documentElement.lang, h1: document.querySelector('h1').textContent, title: document.title, btn: document.querySelector('.chain > a.go').textContent.trim(), gloss: document.getElementById('gloss').hidden, cat: document.querySelector('#cats [aria-pressed=true]').textContent})")
        check('switch to Czech: texts, flyer button, category kept, glossary hidden',
              cs['lang'] == 'cs' and cs['h1'] == 'Akce týdne' and cs['btn'].startswith('Leták') and cs['gloss'] and cs['cat'] == 'Domácnost', str(cs))
        await pg.reload(); await pg.wait_for_timeout(300)
        check('language and category remembered', await pg.get_attribute('html', 'lang') == 'cs' and await pg.get_attribute('#cats button[data-cat="home"]', 'aria-pressed') == 'true')

        await pg.fill('#q', 'olivový olej'); await pg.press('#q', 'Enter'); await pg.wait_for_timeout(100)
        check('search opens kupi.cz', await pg.evaluate('window.__opened') == 'https://www.kupi.cz/hledej?f=olivov%C3%BD%20olej', await pg.evaluate('window.__opened'))
        await pg.click('.chip[data-q="máslo"]')
        check('word chip opens kupi.cz for that word', await pg.evaluate('window.__opened') == 'https://www.kupi.cz/hledej?f=m%C3%A1slo')

        bad = [h for h, t, r in links if not (re.match(OFFICIAL, h) or re.match(MAPS, h))]
        check('every link goes to an official chain site or Google Maps', not bad, str(bad))
        check('links open in a new tab', all(t == '_blank' and 'noopener' in r for h, t, r in links))
        await ctx.close()

        ctx, pg = await newctx(browser, 'cs', 390)
        await pg.goto(url); await pg.wait_for_timeout(300)
        check('inside Telegram: Czech account gets Czech', await pg.get_attribute('html', 'lang') == 'cs')
        href = await pg.get_attribute('.chain a.go', 'href')
        await pg.click('.chain a.go'); await pg.wait_for_timeout(300)
        check('inside Telegram: flyer opens in the phone browser', await pg.evaluate('window.__opened') == href and pg.url == url, href)
        await ctx.close()
        ctx, pg = await newctx(browser, 'uk', 390)
        await pg.goto(url); await pg.wait_for_timeout(300)
        check('inside Telegram: Ukrainian account gets Ukrainian', await pg.get_attribute('html', 'lang') == 'uk')
        await ctx.close()


        # the week strip and flyer tags follow the day in Prague, whatever the phone's own time zone
        for when, day, tag, summary in [('2026-11-10T23:30:00+01:00', '10', 'tomorrow', 'Завтра нові акції: Kaufland, Tesco, BILLA, PENNY, Action.'),
                                        ('2026-11-11T00:30:00+01:00', '11', 'today', 'Сьогодні нові акції: Kaufland, Tesco, BILLA, PENNY, Action. Завтра нові акції: Lidl.'),
                                        ('2026-11-13T10:00:00+01:00', '13', None, 'Наступні нові акції у понеділок: Lidl.')]:
            ctx, pg = await newctx(browser, width=340, tz='America/New_York')
            await pg.clock.set_fixed_time(when)
            await pg.goto(url); await pg.wait_for_timeout(300)
            wk = await pg.evaluate("""() => ({today: document.querySelector('.day.today .dd').textContent, days: document.querySelectorAll('.day').length,
              change: [...document.querySelectorAll('.day.change .dd')].map(d => d.textContent), sum: document.getElementById('weeksum').textContent,
              kaufland: document.querySelector('.chain[aria-label="Kaufland"]').dataset.status || null, coop: document.querySelector('.chain[aria-label="COOP"]').dataset.status || null})""")
            check(f'week {when[:10]}: today {day}, tags {tag}', wk['today'] == day and wk['days'] == 7 and wk['kaufland'] == tag and wk['coop'] is None and wk['sum'] == summary, str(wk))
            await ctx.close()

        ctx, pg = await newctx(browser, width=340)
        await pg.goto(url); await pg.wait_for_timeout(300)
        check('Monday, Wednesday and Thursday marked as flyer days', await pg.evaluate("[...document.querySelectorAll('.day')].map(d => d.classList.contains('change'))") == [True, False, True, True, False, False, False])
        shown = await pg.is_visible('#hint')
        await pg.click('#hintok'); await pg.reload(); await pg.wait_for_timeout(300)
        check('kupi.cz city hint shown until dismissed', shown and not await pg.is_visible('#hint'))
        await ctx.close()

        if '--live' in sys.argv:   # several chain sites block plain HTTP clients, so a real browser opens each page
            for h in sorted({h for h, t, r in links if re.match(OFFICIAL, h)}):
                ctx = await browser.new_context(locale='cs-CZ', user_agent='Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36')
                live = await ctx.new_page()
                try:
                    r = await live.goto(h, timeout=40000)
                    await live.wait_for_timeout(1500)
                    title, status = await live.title(), r.status
                    if status == 403:   # Tesco turns away headless Chrome but serves a normal phone browser; ask once more as one
                        req = urllib.request.Request(h, headers={'User-Agent': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36', 'Accept-Language': 'cs-CZ'})
                        with urllib.request.urlopen(req, timeout=30) as resp:
                            status = resp.status
                            title = (re.search(r'<title>([^<]*)', resp.read().decode('utf-8', 'ignore')) or [None, ''])[1] + ' (plain request)'
                    check(f'live: {h}', status < 400 and not re.search(r'404|nenalezen|not found', title, re.I), f'{status} {title[:60]}')
                except Exception as e:
                    check(f'live: {h}', False, str(e)[:80])
                await ctx.close(); await asyncio.sleep(2)
        await browser.close()

asyncio.run(main())
print('ALL PASS' if not fails else f'{len(fails)} FAILED: {fails}')
sys.exit(1 if fails else 0)
