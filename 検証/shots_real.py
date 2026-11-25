import asyncio, sys, json, tempfile, shutil
import os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from helpers import *
from t_core import persistent, IPHONE
from playwright.async_api import async_playwright
O=(sys.argv[1] if len(sys.argv)>1 else os.path.join(HERE,'画面出力'))+'/'; os.makedirs(O,exist_ok=True)
async def shot(pg,n,full=False):
    await pg.wait_for_timeout(350); await pg.evaluate("document.getElementById('toast').classList.remove('show')"); await pg.screenshot(path=O+n+'.png',full_page=full)
async def main():
    D3=days_ago(3)
    async with async_playwright() as p:
        d=tempfile.mkdtemp(); ctx,pg,errs=await persistent(p,d)
        await pg.goto(URL); await pg.wait_for_timeout(700); await shot(pg,'sp_01_はじめに_使い方を選ぶ')
        await pg.click('[data-a="setRole"][data-v="main"]'); await shot(pg,'sp_02_初回ホーム')
        for dd,m,sk,ti in [(days_ago(4),3,2,1),(days_ago(3),2,3,2),(days_ago(2),4,1,0),(days_ago(1),3,2,2)]:
            await pg.evaluate(f"__app.go('day',{{date:'{dd}'}})"); await pg.click('[data-a="openRec"]')
            await pg.click(f'.sheet [data-a="set"][data-k="mood"][data-v="{m}"]'); await pg.click(f'.sheet [data-a="set"][data-k="sym.skin"][data-v="{sk}"]'); await pg.click(f'.sheet [data-a="set"][data-k="sym.tired"][data-v="{ti}"]')
            await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(250)
        await pg.evaluate("__app.tab('home')"); await pg.click('[data-a="quickMood"][data-v="4"]'); await shot(pg,'sp_03_記録_体調')
        await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(300)
        await pg.evaluate("__R.meta.firstRecordAt=new Date(Date.now()-8*864e5).toISOString(); __app.tab('home')"); await shot(pg,'sp_04_ホーム_バックアップ案内',True)
        await pg.evaluate(f"__app.go('day',{{date:'{D3}'}})"); await shot(pg,'sp_05_日の詳細_天気',True)
        await pg.evaluate("__app.tab('insights')"); await shot(pg,'sp_06_振り返り_自動分類なし')
        await pg.evaluate(f"__demo.A.look({{sym:'skin',date:'{D3}'}})"); await pg.click('details[data-k="f_days"] summary'); await shot(pg,'sp_07_重なり_件数と前後の表',True)
        await pg.evaluate("__app.go('settings')"); await shot(pg,'sp_08_設定',True)
        async with pg.expect_download() as dl: await pg.click('[data-a="exportBackup"]')
        f=await (await dl.value).path(); shutil.copy(f,tmp('bk_shots.json'))
        await pg.set_input_files('#fileIn',tmp('bk_shots.json')); await pg.wait_for_timeout(400); await shot(pg,'sp_09_復元の確認')
        await pg.click('[data-a="dlgClose"]')
        await pg.click('[data-a="enterDemo"]'); await pg.wait_for_timeout(300); await shot(pg,'sp_10_デモ表示中')
        await ctx.close()
        d2=tempfile.mkdtemp(); ctx,pg,e2=await persistent(p,d2,ua='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36 Edg/131.0',w=1440,h=900)
        await pg.goto(URL); await pg.wait_for_timeout(700); await shot(pg,'pc_01_はじめに')
        await pg.click('[data-a="setRole"][data-v="viewer"]'); await pg.set_input_files('#fileIn',tmp('bk_shots.json')); await pg.wait_for_timeout(400); await pg.click('[data-a="doImport"]'); await pg.wait_for_timeout(600)
        await shot(pg,'pc_02_閲覧専用_ホーム')
        await pg.evaluate(f"__demo.A.look({{sym:'tired',date:'{D3}'}})"); await shot(pg,'pc_03_閲覧専用_重なり',True)
        await pg.evaluate("__app.go('settings')"); await shot(pg,'pc_04_閲覧専用_設定')
        print('errors',errs+e2); await ctx.close()
asyncio.run(main())
