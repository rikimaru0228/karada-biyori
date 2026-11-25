# 保存・下書き・取り消し・強制終了・日付・PCの閲覧専用・バックアップ・復元
import asyncio, sys, json, shutil, tempfile, os
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from helpers import *
from playwright.async_api import async_playwright
IPHONE='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'
RES=[]
def ok(name,cond,detail=''):
    RES.append((name,bool(cond),detail)); print(('OK ' if cond else 'NG ')+name+('  '+str(detail) if detail else ''))
async def persistent(p, d, ua=IPHONE, w=390, h=844, tz=None):
    kw=dict(executable_path=CHROME,args=['--no-sandbox'],viewport={'width':w,'height':h},reduced_motion='reduce',accept_downloads=True,user_agent=ua)
    if tz: kw['timezone_id']=tz
    ctx=await p.chromium.launch_persistent_context(d,**kw)
    async def route(r):
        import urllib.parse as up
        q=dict(up.parse_qsl(up.urlparse(r.request.url).query)); await r.fulfill(status=200,content_type='application/json',body=json.dumps(fake_wx(ctx._today,int(q.get('past_days','0')))))
    ctx._today=jst_today(); await ctx.route('https://api.open-meteo.com/**',route)
    pg=ctx.pages[0] if ctx.pages else await ctx.new_page(); await set_clock(pg); errs=[]; pg.on('pageerror',lambda e:errs.append(str(e))); return ctx,pg,errs
async def main():
    P2=days_ago(2)   # 「過去の日」は実行日の2日前（日付を固定しない）
    async with async_playwright() as p:
        d=tempfile.mkdtemp()
        # ---- 1) 記録・下書き・取り消し・強制終了 ----
        ctx,pg,errs=await persistent(p,d)
        await pg.goto(URL); await pg.wait_for_timeout(600)
        await pg.click('[data-a="setRole"][data-v="main"]')
        await pg.click('[data-a="quickMood"][data-v="3"]'); await pg.click('.sh-foot [data-a="step"][data-v="2"]')
        await pg.click('[data-a="slot"][data-v="d"]'); await pg.fill('#mealIn','肉じゃが'); await pg.wait_for_timeout(400)
        await ctx.close()   # 強制終了（閉じる操作をしない）
        ctx,pg,errs2=await persistent(p,d); await pg.goto(URL); await pg.wait_for_timeout(800)
        ok('強制終了後に「続きから」が出る', await pg.locator('[data-a="resume"]').count()==1)
        await pg.click('[data-a="resume"]'); await pg.click('.steps [data-a="step"][data-v="2"]'); await pg.click('[data-a="slot"][data-v="d"]')
        ok('入力途中の食事（追加前）が残る', await pg.input_value('#mealIn')=='肉じゃが')
        await pg.click('.sh-foot [data-a="saveRec"]'); await pg.click('[data-a="savePendingAdd"]'); await pg.wait_for_timeout(400)
        day=await pg.evaluate("__R.state.days[__app.today()]")
        ok('保存（調子と夕食）', day and day['mood']==3 and day['meals']['d']['items']==['肉じゃが'])
        await pg.click('#toast [data-a="undo"]'); await pg.wait_for_timeout(400)
        ok('保存の取り消し→書きかけに戻る', await pg.evaluate("!__R.state.days[__app.today()] && !!__R.state.draft"))
        await pg.click('[data-a="resume"]'); await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(300)
        if await pg.locator('[data-a="savePendingAdd"]').count(): await pg.click('[data-a="savePendingAdd"]')
        await pg.wait_for_timeout(500)
        # 過去の日の修正と削除の取り消し
        await pg.evaluate(f"__app.go('day',{{date:'{P2}'}})"); await pg.click('[data-a="openRec"]')
        await pg.click('.sheet [data-a="set"][data-k="mood"][data-v="2"]'); await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(300)
        ok(f'過去の日（{P2}）を記録', await pg.evaluate(f"__R.state.days['{P2}'].mood")==2)
        await pg.click('[data-a="askDelete"]'); await pg.click('[data-a="doDelete"]'); await pg.wait_for_timeout(300)
        gone=await pg.evaluate(f"!__R.state.days['{P2}']"); await pg.click('#toast [data-a="undo"]'); await pg.wait_for_timeout(400)
        ok('削除→取り消しで戻る', gone and await pg.evaluate(f"!!__R.state.days['{P2}']"))
        await pg.reload(); await pg.wait_for_timeout(800)
        ok('再読み込み後も2日分残る', await pg.evaluate("Object.keys(__R.state.days).length")==2)
        # ---- 2) バックアップ書き出し ----
        await pg.evaluate("__app.go('settings')")
        async with pg.expect_download() as dl:
            await pg.click('[data-a="exportBackup"]')
        f=await (await dl.value).path(); txt=open(f,encoding='utf-8').read(); bk=json.loads(txt)
        ok('書き出したファイルの形式', bk['format']=='karada-biyori-backup' and bk['kind']=='real' and bk['summary']['days']==2, bk['summary'])
        ok('書き出し日時を記録', await pg.evaluate("!!__R.meta.lastBackupAt"))
        open(tmp('backup_ok.json'),'w',encoding='utf-8').write(txt)
        orig=await pg.evaluate("JSON.stringify(__R.state.days)")
        # 壊れたファイル・デモ・新しい版を断る
        bad=dict(bk); bad['body']=bk['body'].replace('肉じゃが','カレー'); open(tmp('bk_bad.json'),'w').write(json.dumps(bad))
        demo=dict(bk); demo['kind']='demo'; open(tmp('bk_demo.json'),'w').write(json.dumps(demo))
        newer=dict(bk); newer['schema']=99; open(tmp('bk_new.json'),'w').write(json.dumps(newer))
        for path,label in [(tmp('bk_bad.json'),'壊れた'),(tmp('bk_demo.json'),'デモの'),(tmp('bk_new.json'),'新しい版の')]:
            await pg.set_input_files('#fileIn',path); await pg.wait_for_timeout(400)
            t=await pg.locator('.dialog').inner_text(); await pg.click('[data-a="dlgClose"]')
            ok(f'{label}ファイルを断り、記録は変えない', '読み込めませんでした' in t and await pg.evaluate("JSON.stringify(__R.state.days)")==orig, t.split('\n')[1][:40])
        # ---- 3) 全削除→復元（別の端末を想定） ----
        await ctx.close()
        d2=tempfile.mkdtemp(); ctx,pg,errs3=await persistent(p,d2); await pg.goto(URL); await pg.wait_for_timeout(600)
        await pg.click('[data-a="setRole"][data-v="main"]')
        await pg.click('[data-a="quickMood"][data-v="1"]'); await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(300)
        await pg.set_input_files('#fileIn',tmp('backup_ok.json')); await pg.wait_for_timeout(400)
        prev=await pg.locator('.dialog').inner_text()
        await pg.click('[data-a="doImport"]'); await pg.wait_for_timeout(600)
        ok('復元で記録が一致', await pg.evaluate("JSON.stringify(__R.state.days)")==orig, prev.replace('\n',' ')[:90])
        await pg.click('#toast [data-a="undoRestore"]'); await pg.wait_for_timeout(600)
        ok('「復元前に戻す」で元の1日に戻る', await pg.evaluate("Object.values(__R.state.days).length===1 && Object.values(__R.state.days)[0].mood===1"))
        await ctx.close()
        # ---- 4) PC：閲覧専用 ----
        d3=tempfile.mkdtemp(); ctx,pg,errs4=await persistent(p,d3,ua='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36 Edg/131.0',w=1440,h=900)
        await pg.goto(URL); await pg.wait_for_timeout(600)
        await pg.click('[data-a="setRole"][data-v="viewer"]')
        await pg.set_input_files('#fileIn',tmp('backup_ok.json')); await pg.wait_for_timeout(400); await pg.click('[data-a="doImport"]'); await pg.wait_for_timeout(600)
        ok('PCで読み込んだ記録を表示', await pg.evaluate("JSON.stringify(__R.state.days)")==orig)
        ban=await pg.locator('#banner').inner_text(); ok('閲覧専用の表示（読み込み日時）', '閲覧専用' in ban and '読み込んだ記録' in ban, ban[:60])
        before=await pg.evaluate("JSON.stringify(__R.state)")
        await pg.evaluate(f"__app.go('day',{{date:'{P2}'}})"); await pg.click('[data-a="openRec"]'); await pg.wait_for_timeout(200)
        t=await pg.locator('#toast').inner_text()
        ok('PCで修正しようとすると止める', '閲覧専用' in t and await pg.locator('.sheet').count()==0, t)
        await pg.evaluate("__app.tab('home')")
        ok('PCのホームに記録ボタンがない', await pg.locator('[data-a="quickMood"]').count()==0)
        await pg.reload(); await pg.wait_for_timeout(700)
        ok('PCの状態は変わらない', await pg.evaluate("JSON.stringify(__R.state)")==before)
        await pg.screenshot(path=tmp('pc_viewer.png'))
        await ctx.close()
        # ---- 5) 記録のある端末は閲覧専用にできない ----
        ctx,pg,errs5=await persistent(p,d); await pg.goto(URL); await pg.wait_for_timeout(600)
        await pg.evaluate("__app.go('settings')"); await pg.click('[data-a="roleToViewer"]'); await pg.wait_for_timeout(200)
        ok('記録のある端末は閲覧専用に切り替えない', 'できません' in await pg.locator('.dialog').inner_text() and await pg.evaluate("__R.meta.role")=='main')
        await ctx.close()
        allerr=errs+errs2+errs3+errs4+errs5; ok('エラーなし', not allerr, allerr[:3])
        for x in (d,d2,d3): shutil.rmtree(x,ignore_errors=True)
    print('---', sum(1 for r in RES if r[1]), '/', len(RES), '件 合格')
if __name__=="__main__": asyncio.run(main())
