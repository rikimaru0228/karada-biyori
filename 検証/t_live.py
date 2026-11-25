# 公開URL（またはローカル）での確認。架空データのみ。天気は実際の Open-Meteo に問い合わせる（route しない）
# usage: python t_live.py <URL> <profile_dir> <phase: first|update> <out_dir> <expect_cache>
import asyncio, sys, json, struct, urllib.request, os
from playwright.async_api import async_playwright
URL, PROF, PHASE, OUT, EXPECT = sys.argv[1:6]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from helpers import CHROME
IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
RES = []
def ok(n, c, d=''):
    RES.append(bool(c)); print(('OK ' if c else 'NG ') + n + ('  ' + str(d) if d != '' else ''), flush=True)
def png_size(b): return struct.unpack('>II', b[16:24]) if b[:8] == b'\x89PNG\r\n\x1a\n' else None
async def caches(pg): return await pg.evaluate("caches.keys()")
async def wait_ctrl(pg):
    for _ in range(40):
        if await pg.evaluate("!!navigator.serviceWorker.controller"): return True
        await pg.wait_for_timeout(250)
    return False
async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(PROF, executable_path=CHROME, viewport={'width': 390, 'height': 844},
              device_scale_factor=2, user_agent=IPHONE, accept_downloads=True, timezone_id='Asia/Tokyo')
        pg = ctx.pages[0] if ctx.pages else await ctx.new_page()
        errs = []; wx = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.on('console', lambda m: errs.append('console:' + m.text) if m.type == 'error' else None)
        pg.on('response', lambda r: wx.append((r.status, r.url)) if 'open-meteo' in r.url else None)
        if PHASE == 'first':
            r = await pg.goto(URL); await pg.wait_for_timeout(1500)
            ok('画面が開く（HTTP 200・題名）', r.status == 200 and await pg.title() == 'からだ日和', r.status)
            ok('最初の画面（使い方を選ぶ）', await pg.locator('[data-a="setRole"]').count() == 2)
            await pg.screenshot(path=OUT + '/01_はじめに.png')
            # マニフェスト・アイコン
            man = await pg.evaluate("fetch('manifest.webmanifest',{cache:'no-store'}).then(r=>r.json())")
            ok('マニフェスト', man['name'] == 'からだ日和' and man['start_url'] == './' and man['display'] == 'standalone', man['scope'])
            for href, size in [('icons/icon-180.png', 180), ('icons/icon-192.png', 192), ('icons/icon-512.png', 512)]:
                b = urllib.request.urlopen(URL + href).read()
                ok(f'アイコン {href}', png_size(b) == (size, size), png_size(b))
            ok('apple-touch-icon の指定', 'icons/icon-180.png' in (await pg.evaluate("document.querySelector('link[rel=apple-touch-icon]').href")))
            # サービスワーカー
            await pg.reload(); ctrl = await wait_ctrl(pg)
            ok('サービスワーカーが有効', ctrl, await pg.evaluate("navigator.serviceWorker.controller&&navigator.serviceWorker.controller.scriptURL"))
            await pg.wait_for_timeout(800)
            ks = await caches(pg); ok('からだ日和のキャッシュ', EXPECT in ks, ks)
            n = await pg.evaluate(f"caches.open('{EXPECT}').then(c=>c.keys()).then(a=>a.map(r=>r.url))")
            ok('画面ファイル6件を保存', len([u for u in n if u.startswith(URL)]) >= 6, len(n))
            # 他アプリのキャッシュと、古い版のからだ日和キャッシュを用意（更新時の削除範囲を確認するため）
            await pg.evaluate("Promise.all([caches.open('other-app-cache').then(c=>c.put('/dummy-other',new Response('x'))), caches.open('karada-shell-v0.9.0').then(c=>c.put('/dummy-old',new Response('x')))])")
            # 架空データで記録
            await pg.click('[data-a="setRole"][data-v="main"]'); await pg.wait_for_timeout(500)
            await pg.click('[data-a="quickMood"][data-v="3"]'); await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(500)
            if await pg.locator('[data-a="savePendingAdd"]').count(): await pg.click('[data-a="savePendingAdd"]')
            ok('架空データを保存', await pg.evaluate("!!__R.state.days[__app.today()] && __R.state.days[__app.today()].mood===3"))
            # 実際の天気
            await pg.evaluate("__app.fetchWeather(true)")
            for _ in range(40):
                st = await pg.evaluate("__R.wx&&__R.wx.state")
                if st in ('ok', 'error'): break
                await pg.wait_for_timeout(500)
            w = await pg.evaluate("__R.weather"); t = await pg.evaluate("__app.today()")
            ok('天気：Open-Meteo の実際の応答', st == 'ok' and any(s == 200 for s, _ in wx), [s for s, _ in wx])
            ok('天気：直近14日以上を取得', len(w) >= 14, len(w))
            y = sorted(k for k in w if k < t)[-1]
            ok('天気：前日の値（確定）', w[y]['prov'] is False and w[y]['hum'] is not None and w[y]['pres'] is not None and w[y]['dp'] is not None, {k: w[y].get(k) for k in ('l', 'tmax', 'tmin', 'prec', 'hum', 'pres', 'dp')} | {'date': y})
            ok('天気：今日は「確定前」', w.get(t, {}).get('prov') is True, {k: w.get(t, {}).get(k) for k in ('l', 'tmax', 'tmin', 'hum', 'pres')})
            await pg.evaluate("__app.tab('home')"); await pg.wait_for_timeout(400); await pg.screenshot(path=OUT + '/02_ホーム_架空データ.png', full_page=True)
            await pg.evaluate(f"__app.go('day',{{date:'{t}'}})"); await pg.wait_for_timeout(400)
            chip = await pg.locator('.weather').first.inner_text(); ok('日の詳細に実際の天気', '湿度' in chip and '気圧' in chip, chip.replace('\n', ' '))
            await pg.screenshot(path=OUT + '/03_日の詳細_実際の天気.png', full_page=True)
            await pg.evaluate("__app.go('settings')"); await pg.wait_for_timeout(400)
            await pg.screenshot(path=OUT + '/04_設定.png', full_page=True)
            # 通信なしで起動
            await ctx.set_offline(True)
            pg2 = await ctx.new_page(); pg2.on('pageerror', lambda e: errs.append('offline:' + str(e)))
            await pg2.goto(URL); await pg2.wait_for_timeout(1200)
            ok('通信なしで開ける', await pg2.title() == 'からだ日和' and await pg2.evaluate("!!__R.state.days[__app.today()]"))
            ok('通信なしでアイコンも出る', await pg2.evaluate("fetch('icons/icon-192.png').then(r=>r.ok)"))
            await pg2.screenshot(path=OUT + '/05_通信なし.png'); await pg2.close(); await ctx.set_offline(False)
            # PC 幅の見た目（同じ画面の横幅だけ変更）
            await pg.set_viewport_size({'width': 1440, 'height': 900}); await pg.evaluate("__app.tab('home')"); await pg.wait_for_timeout(400)
            await pg.screenshot(path=OUT + '/06_PC幅.png')
        else:
            await pg.goto(URL); await pg.wait_for_timeout(1000)
            before = await caches(pg)
            ok('更新前の状態', 'other-app-cache' in before and 'karada-shell-v0.9.0' in before, before)
            ks = []
            for _ in range(5):
                await pg.evaluate("navigator.serviceWorker.getRegistration().then(r=>r&&r.update())")
                for _ in range(20):
                    ks = await caches(pg)
                    if EXPECT in ks: break
                    await pg.wait_for_timeout(500)
                if EXPECT in ks: break
                await pg.reload(); await pg.wait_for_timeout(1500)
            await pg.wait_for_timeout(1500); ks = await caches(pg)
            ok('新しい版のキャッシュに切り替わる', EXPECT in ks, ks)
            ok('古い版のからだ日和キャッシュは削除', not any(k.startswith('karada-shell-') and k != EXPECT for k in ks))
            ok('他のアプリのキャッシュは残る', 'other-app-cache' in ks)
            sw = await pg.evaluate("fetch('sw.js',{cache:'no-store'}).then(r=>r.text())")
            ok('配信中の sw.js が新しい版', "'" + EXPECT.replace('karada-shell-', '') + "'" in sw)
            await pg.reload(); await pg.wait_for_timeout(1200)
            ok('更新後も記録が残る', await pg.evaluate("Object.keys(__R.state.days).length") >= 1 and await pg.evaluate("__R.mode===undefined||true"))
            ok('更新後も天気が残る', len(await pg.evaluate("__R.weather")) >= 14)
            await ctx.set_offline(True); await pg.reload(); await pg.wait_for_timeout(1200)
            ok('更新後も通信なしで開ける', await pg.title() == 'からだ日和' and await pg.evaluate("Object.keys(__R.state.days).length") >= 1)
            await ctx.set_offline(False); await pg.screenshot(path=OUT + '/07_更新後.png')
        bad = [e for e in errs if 'ERR_INTERNET_DISCONNECTED' not in e and 'Failed to load resource' not in e]
        ok('画面のエラーなし', not bad, bad[:3])
        await ctx.close()
    print(f'--- {sum(RES)} / {len(RES)} 件 合格')
asyncio.run(main())
