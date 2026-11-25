import asyncio, sys, json, shutil, tempfile, datetime
import os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from helpers import *
from t_core import persistent, IPHONE
from playwright.async_api import async_playwright
RES=[]
def ok(name,cond,detail=''):
    RES.append((name,bool(cond))); print(('OK ' if cond else 'NG ')+name+('  '+str(detail) if detail else ''))
async def setup_main(pg, url=URL):
    await pg.goto(url); await pg.wait_for_timeout(600)
    if await pg.locator('[data-a="setRole"]').count(): await pg.click('[data-a="setRole"][data-v="main"]')
async def rec(pg, mood):
    await pg.click(f'[data-a="quickMood"][data-v="{mood}"]'); await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(300)
async def main():
    async with async_playwright() as p:
        allerr=[]
        # ---- 日付（日本時間0時区切り・端末が別のタイムゾーンでも） ----
        for start,label,tz in [('2026-11-22T23:59:00+09:00','日','America/Los_Angeles'),('2026-11-30T23:59:00+09:00','月','Asia/Tokyo'),('2026-12-31T23:59:00+09:00','年','UTC')]:
            d=tempfile.mkdtemp(); ctx,pg,e=await persistent(p,d,tz=tz); allerr+=e
            await set_clock(pg, start)
            await setup_main(pg); t0=await pg.evaluate("__app.today()")
            await pg.click('[data-a="quickMood"][data-v="3"]')   # 書きかけ（0時をまたぐ）
            await pg.clock.run_for(120000); await pg.wait_for_timeout(200)
            t1=await pg.evaluate("__app.today()"); draft_date=await pg.evaluate("__R.state.draft&&__R.state.draft.date")
            exp0=start[:10]; exp1=(datetime.date.fromisoformat(exp0)+datetime.timedelta(days=1)).isoformat()
            ok(f'{label}をまたぐ（端末の時間帯 {tz}）', t0==exp0 and t1==exp1, f'{t0}→{t1}')
            ok(f'{label}をまたいでも書きかけは元の日付', draft_date==exp0)
            await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(300)
            ok(f'{label}をまたいだ書きかけは元の日に保存', await pg.evaluate(f"!!__R.state.days['{exp0}'] && !__R.state.days['{exp1}']"))
            await ctx.close(); shutil.rmtree(d,ignore_errors=True)
        # ---- 更新：変換あり（版1→版2） ----
        d=tempfile.mkdtemp(); ctx,pg,e=await persistent(p,d); allerr+=e
        await setup_main(pg); await rec(pg,4)
        await pg.evaluate(f"__app.go('day',{{date:'{days_ago(3)}'}})"); await pg.click('[data-a="openRec"]'); await pg.click('.sheet [data-a="set"][data-k="mood"][data-v="2"]'); await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(400)
        v1=await pg.evaluate("JSON.stringify(__R.state.days)")
        await pg.goto(URL+'v2ok/'); await pg.wait_for_timeout(800)
        ok('版2に更新しても記録が同じ', await pg.evaluate("JSON.stringify(__R.state.days)")==v1)
        ok('版2の変換が反映', await pg.evaluate("__R.meta.schema===2 && __R.state.prefs.migratedToV2===true"))
        snaps=await pg.evaluate("__app.listSnapshots().then(a=>a.map(x=>x.reason))")
        ok('更新の直前の写しがある', any('更新の直前' in x for x in snaps), snaps)
        await pg.goto(URL); await pg.wait_for_timeout(800)
        ok('古い版で開くと変更しない（新しい版の記録）', await pg.evaluate("__R.readOnly")=='newer')
        await pg.click('[data-a="quickMood"][data-v="5"]') if await pg.locator('[data-a="quickMood"]').count() else None
        ok('古い版では記録を書き換えない', await pg.evaluate("JSON.stringify(__R.state.days)")==v1)
        await ctx.close(); shutil.rmtree(d,ignore_errors=True)
        # ---- 更新：変換に失敗 ----
        d=tempfile.mkdtemp(); ctx,pg,e=await persistent(p,d); allerr+=e
        await setup_main(pg); await rec(pg,3); v1=await pg.evaluate("JSON.stringify(__R.state)")
        await pg.goto(URL+'v2ng/'); await pg.wait_for_timeout(800)
        ok('変換に失敗したら変更せず表示', await pg.evaluate("__R.readOnly")=='migrate' and '変換に失敗' in await pg.locator('#banner').inner_text())
        await pg.goto(URL); await pg.wait_for_timeout(800)
        ok('元の版に戻すと記録はそのまま', await pg.evaluate("JSON.stringify(__R.state)")==v1 and await pg.evaluate("__R.meta.schema")==1 and not await pg.evaluate("__R.readOnly"))
        await ctx.close(); shutil.rmtree(d,ignore_errors=True)
        # ---- 天気：失敗しても記録できる・あとで補完・前日差・確定前 ----
        d=tempfile.mkdtemp(); ctx,pg,e=await persistent(p,d); allerr+=e
        await ctx.unroute('https://api.open-meteo.com/**'); await ctx.route('https://api.open-meteo.com/**', lambda r: r.abort())
        await setup_main(pg); await rec(pg,4); await pg.wait_for_timeout(300)
        ok('天気が取れなくても記録できる', await pg.evaluate("!!__R.state.days[__app.today()] && __R.wx.state==='error'"), await pg.evaluate("__R.wx.msg"))
        await ctx.unroute('https://api.open-meteo.com/**')
        async def route(r):
            import urllib.parse as up
            q=dict(up.parse_qsl(up.urlparse(r.request.url).query)); await r.fulfill(status=200,content_type='application/json',body=json.dumps(fake_wx(jst_today(),int(q.get('past_days','0')))))
        await ctx.route('https://api.open-meteo.com/**',route)
        await pg.evaluate("__app.fetchWeather(true)"); await pg.wait_for_timeout(500)
        w=await pg.evaluate("__R.weather"); t=await pg.evaluate("__app.today()")
        ok('つながったら天気を補完（直近14日）', len(w)>=14, len(w))
        ok('今日の天気は「確定前」', w[t]['prov']==True and w[days_ago(1,t)]['prov']==False)
        ok('湿度・気圧は1時間ごとの値の平均、前日差あり', w[days_ago(1,t)]['hum'] is not None and w[days_ago(1,t)]['dp'] is not None, {k:w[days_ago(1,t)][k] for k in ('l','hum','pres','dp')})
        await pg.evaluate(f"__app.go('day',{{date:'{t}'}})"); chip=await pg.locator('.weather').first.inner_text()
        ok('記録の詳細に天気を表示', '湿度' in chip and '気圧' in chip, chip)
        await pg.screenshot(path=tmp('day_wx.png'))
        # ---- デモと本人の記録の分離 ----
        real_before=await pg.evaluate("JSON.stringify(__R.state.days)")
        await pg.evaluate("__app.go('settings')"); await pg.click('[data-a="enterDemo"]'); await pg.wait_for_timeout(300)
        ok('デモ中の表示', 'デモ表示中' in await pg.locator('#banner').inner_text() and await pg.evaluate("__app.mode()")=='demo')
        await pg.evaluate("__demo.set('rich')"); await pg.wait_for_timeout(200)
        await pg.click('[data-a="quickMood"][data-v="1"]'); await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(300)
        demo_days=await pg.evaluate("Object.keys(__app.S().days).length")
        # 自動分類が出ないこと（デモでも）
        await pg.evaluate("__app.tab('insights')"); ins=await pg.locator('#view').inner_text()
        await pg.evaluate("__demo.A.look({sym:'skin'})"); lk=await pg.locator('#view').inner_text()
        await pg.evaluate("__app.go('exp',{id:'e2'})"); ex=await pg.locator('#view').inner_text()
        await pg.evaluate("__app.tab('home')"); hm=await pg.locator('#view').inner_text()
        bad=[w for w in ['不調の日に多かった','落ち着いた日に多かった','共通点がありました','記録上は、'] if w in ins+lk+ex+hm]
        ok('自動分類・気づき・判定文を表示しない', not bad, bad)
        await pg.click('#banner [data-a="exitDemo"]'); await pg.wait_for_timeout(300)
        ok('デモを出ると自分の記録はそのまま', await pg.evaluate("JSON.stringify(__R.state.days)")==real_before and demo_days>20)
        idb=await pg.evaluate("""new Promise(r=>{const q=indexedDB.open('karada-real');q.onsuccess=()=>{const g=q.result.transaction('kv').objectStore('kv').get('state');g.onsuccess=()=>r(Object.keys(g.result.days).length)}})""")
        ok('端末内の本人用データにデモが混ざらない', idb==len(json.loads(real_before)), idb)
        b=await pg.evaluate("__app.makeBackup().then(b=>JSON.parse(b.body).data.days)")
        ok('バックアップにデモが含まれない', len(b)==len(json.loads(real_before)))
        # ---- 7日ごとのバックアップ案内 ----
        await pg.evaluate("__R.meta.firstRecordAt=new Date(Date.now()-8*864e5).toISOString(); __R.meta.lastBackupAt=null; __app.tab('home')")
        c1=await pg.locator('.bkcard').count(); txt=await pg.locator('.bkcard').inner_text() if c1 else ''
        await pg.evaluate("__R.meta.lastBackupAt=new Date(Date.now()-3*864e5).toISOString(); __app.tab('home')"); c2=await pg.locator('.bkcard').count()
        await pg.evaluate("__R.meta.lastBackupAt=new Date(Date.now()-7*864e5-60e3).toISOString(); __app.tab('home')"); c3=await pg.locator('.bkcard').inner_text() if await pg.locator('.bkcard').count() else ''
        ok('7日たつと案内、3日では出ない', c1==1 and c2==0 and '7日' in c3, txt.split('\n')[1][:30])
        await ctx.close(); shutil.rmtree(d,ignore_errors=True)
        # ---- 通信できない時も開ける（ホーム画面アプリ） ----
        d=tempfile.mkdtemp(); ctx,pg,e=await persistent(p,d); allerr+=e
        await setup_main(pg); await rec(pg,4)
        await pg.evaluate("navigator.serviceWorker.ready"); await pg.reload(); await pg.wait_for_timeout(800)
        ctrl=await pg.evaluate("!!navigator.serviceWorker.controller")
        await ctx.set_offline(True); await pg.reload(); await pg.wait_for_timeout(900)
        ok('通信なしでも開けて記録が見える', ctrl and await pg.evaluate("Object.keys(__R.state.days).length")==1)
        await rec(pg,2) if await pg.locator('[data-a="quickMood"]').count() else await pg.click('[data-a="openRec"]')
        await ctx.close(); shutil.rmtree(d,ignore_errors=True)
        ok('エラーなし', not allerr, allerr[:3])
    print('---', sum(1 for r in RES if r[1]), '/', len(RES), '件 合格')
asyncio.run(main())
