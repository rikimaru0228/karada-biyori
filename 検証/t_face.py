# 「顔のこわばり・緊張」の追加の確認（保存・修正・取り消し・過去・既存データ・バックアップ／復元・振り返り・画面）
import asyncio, sys, json, shutil, tempfile, os, hashlib
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from helpers import *
from t_core import persistent
from playwright.async_api import async_playwright
OUT=sys.argv[1] if len(sys.argv)>1 else TMP; os.makedirs(OUT,exist_ok=True)
RES=[]
# 画面の外、またはカード・記録画面・確認の枠の外にはみ出している要素を返す（横に動かせる表の中は除く）
OVERFLOW_JS="""()=>{const out=[];const vw=innerWidth;
 const scrollers=[...document.querySelectorAll('*')].filter(e=>/(auto|scroll)/.test(getComputedStyle(e).overflowX));
 document.querySelectorAll('#view *, .sheet *, .dialog *').forEach(e=>{if(!e.offsetParent&&getComputedStyle(e).position!=='fixed')return;
  if(scrollers.some(s=>s!==e&&s.contains(e)))return;
  const r=e.getBoundingClientRect(); if(!r.width)return;
  const box=e.parentElement&&e.parentElement.closest('.card,.sheet,.dialog,.daypanel');
  const lim=box?box.getBoundingClientRect():{left:0,right:vw};
  if(r.right>lim.right+0.5||r.left<lim.left-0.5||r.right>vw+0.5) out.push(e.tagName+'「'+(e.innerText||'').trim().slice(0,12)+'」'+Math.round(r.right)+'>'+Math.round(lim.right));});
 if(document.documentElement.scrollWidth>vw) out.push('ページ幅 '+document.documentElement.scrollWidth);
 return [...new Set(out)]}"""
def ok(name,cond,detail=''):
    RES.append((name,bool(cond))); print(('OK ' if cond else 'NG ')+name+('  '+str(detail) if detail else ''))
OLD_KEYS=['shoulder','tired','nose','skin','voice']
def old_day(mood,skin,tired,stress='mid',sleep=6.5):
    sym={k:None for k in OLD_KEYS}; sym['skin']=skin; sym['tired']=tired
    return {"mood":mood,"wake":None,"sym":sym,"tiredWhen":[],"meals":{k:{"items":[],"none":False} for k in 'blds'},"dinnerTime":None,"tags":[],"tagsNo":[],
            "sleep":sleep,"stress":stress,"activity":None,"posture":None,"seitai":None,"meds":[],"medsNone":False,"weight":"","memo":"前からある記録","savedAt":"2026-11-10T12:00:00Z"}
async def put_state(pg,state):
    await pg.evaluate("""st=>new Promise((res,rej)=>{const q=indexedDB.open('karada-real');q.onsuccess=()=>{const db=q.result;const tx=db.transaction('kv','readwrite');tx.objectStore('kv').put(st,'state');tx.oncomplete=()=>{db.close();res()};tx.onerror=()=>rej(tx.error)}})""",state)
async def body_text(pg): return await pg.locator('body').inner_text()
async def main():
    async with async_playwright() as p:
        d=tempfile.mkdtemp(); ctx,pg,errs=await persistent(p,d)
        await pg.goto(URL); await pg.wait_for_timeout(700)
        await pg.click('[data-a="setRole"][data-v="main"]'); await pg.wait_for_timeout(200)
        T=await pg.evaluate("__app.today()")
        # ---- 1) 既存データ（項目が無い形）を用意して読み込む ----
        days={}
        import datetime as dt
        for i in range(1,13):
            dd=(dt.date.fromisoformat(T)-dt.timedelta(days=i)).isoformat()
            days[dd]=old_day(2+i%3, i%4, (i+1)%4, 'high' if i%3==0 else 'mid', 5.5 if i%2 else 7.5)
        old_state={"days":days,"history":{"b":{},"l":{},"d":{},"s":{}},"experiments":[],"plans":[],"draft":None,"welcomeSeen":True,"prefs":{}}
        await put_state(pg,old_state); await pg.reload(); await pg.wait_for_timeout(800)
        st=await pg.evaluate("__R.state.days")
        ok('既存の記録：日数そのまま', len(st)==12)
        ok('既存の記録：顔のこわばりは「未記録」(null) として補う', all(v['sym'].get('face',1) is None for v in st.values()))
        ok('既存の記録：ほかの値は変わらない', all(st[k]['sym'][s]==days[k]['sym'][s] and st[k]['mood']==days[k]['mood'] and st[k]['memo']==days[k]['memo'] for k in days for s in OLD_KEYS))
        d1=sorted(days)[-1]
        await pg.evaluate(f"__app.go('day',{{date:'{d1}'}})"); await pg.wait_for_timeout(200)
        t=await body_text(pg)
        ok('既存の日の詳細：「顔のこわばり・緊張 未記録」、undefinedなし', '顔のこわばり・緊張\n未記録' in t and 'undefined' not in t)
        # ---- 2) 今日：顔のこわばりだけ記録（ほかは触れない） ----
        await pg.evaluate("__app.tab('home')"); await pg.wait_for_timeout(200)
        await pg.evaluate(f"__app.open('{T}')"); await pg.wait_for_timeout(300)
        sheet=await pg.locator('.sheet').inner_text()
        ok('記録画面に項目と「気になるときだけ」の表示', '顔のこわばり・緊張' in sheet and '気になるときだけ' in sheet)
        ok('記録画面：初めは「未記録」', await pg.locator('.symrow:has-text("顔のこわばり") .st').inner_text()=='未記録')
        ok('記録画面に「なし」を残す案内', '気にならなかった日も「なし」を残すと、振り返りやすくなります' in sheet and '押さなければ「未記録」のままです' in sheet)
        for i,l in enumerate(['なし','軽い','中','強い']):
            ok(f'強さの選択肢 {l}', await pg.locator(f'.sheet [data-k="sym.face"][data-v="{i}"]').inner_text()==l)
        await pg.screenshot(path=os.path.join(OUT,'p1_記録画面_顔のこわばり.png'))
        await pg.click('.sheet [data-k="sym.face"][data-v="2"]'); await pg.wait_for_timeout(100)
        await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(400)
        r=await pg.evaluate(f"__R.state.days['{T}']")
        ok('顔のこわばりだけで保存できる', r and r['sym']['face']==2 and all(r['sym'][k] is None for k in OLD_KEYS) and r['mood'] is None)
        # 取り消し
        await pg.click('#toast [data-a="undo"]'); await pg.wait_for_timeout(400)
        ok('保存の取り消しで消える', await pg.evaluate(f"!__R.state.days['{T}']"))
        await pg.click('[data-a="resume"]'); await pg.wait_for_timeout(200)
        await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(400)
        ok('書きかけから保存し直せる', await pg.evaluate(f"__R.state.days['{T}'].sym.face")==2)
        # ---- 3) 「残りをすべてなし」は顔のこわばりを変えない ----
        d2=sorted(days)[-2]
        await pg.evaluate(f"__app.go('day',{{date:'{d2}'}})"); await pg.click('[data-a="openRec"]'); await pg.wait_for_timeout(200)
        await pg.click('[data-a="allNone"]'); await pg.wait_for_timeout(100)
        await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(400)
        r=await pg.evaluate(f"__R.state.days['{d2}']")
        ok('「残りをすべてなし」でも顔のこわばりは未記録のまま', r['sym']['face'] is None and all(r['sym'][k] is not None for k in OLD_KEYS), r['sym'])
        # ---- 4) 修正：過去の日に記録→強さ変更→同じ強さをもう一度押して未記録に ----
        await pg.evaluate(f"__app.go('day',{{date:'{d2}'}})"); await pg.click('[data-a="openRec"]'); await pg.wait_for_timeout(200)
        await pg.click('.sheet [data-k="sym.face"][data-v="1"]'); await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(400)
        ok('過去の日に記録（軽い）', await pg.evaluate(f"__R.state.days['{d2}'].sym.face")==1)
        t=await body_text(pg); ok('日の詳細に「軽い」', '顔のこわばり・緊張\n軽い' in t)
        await pg.click('[data-a="openRec"]'); await pg.wait_for_timeout(200)
        await pg.click('.sheet [data-k="sym.face"][data-v="3"]'); await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(400)
        ok('修正（軽い→強い）', await pg.evaluate(f"__R.state.days['{d2}'].sym.face")==3)
        await pg.click('#toast [data-a="undo"]'); await pg.wait_for_timeout(400)
        ok('修正の取り消しで「軽い」に戻る', await pg.evaluate(f"__R.state.days['{d2}'].sym.face")==1)
        await pg.evaluate(f"__app.go('day',{{date:'{d2}'}})"); await pg.click('[data-a="openRec"]'); await pg.wait_for_timeout(200)
        cur=await pg.locator('.sheet [data-k="sym.face"][aria-pressed="true"]').get_attribute('data-v')
        await pg.click(f'.sheet [data-k="sym.face"][data-v="{cur}"]'); await pg.wait_for_timeout(100)
        stx=await pg.locator('.symrow:has-text("顔のこわばり") .st').inner_text()
        await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(400)
        ok('選んでいる強さをもう一度押すと「未記録」に戻せる', stx=='未記録' and await pg.evaluate(f"__R.state.days['{d2}'].sym.face") is None, f'押した強さ {cur}')
        # 「なし」と未記録は別の値として残る
        d3=sorted(days)[-3]
        await pg.evaluate(f"__app.go('day',{{date:'{d3}'}})"); await pg.click('[data-a="openRec"]'); await pg.wait_for_timeout(200)
        await pg.click('.sheet [data-k="sym.face"][data-v="0"]'); await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(400)
        v3=await pg.evaluate(f"__R.state.days['{d3}'].sym.face"); t=await body_text(pg)
        ok('「なし」は 0 として残り、未記録(null)とは別', v3==0 and '顔のこわばり・緊張\nなし' in t, v3)
        await pg.click('#toast [data-a="undo"]'); await pg.wait_for_timeout(400)
        ok('「なし」の保存を取り消すと未記録に戻る', await pg.evaluate(f"__R.state.days['{d3}'].sym.face") is None)
                # 削除→取り消し
        await pg.evaluate(f"__app.go('day',{{date:'{T}'}})"); await pg.click('[data-a="askDelete"]'); await pg.click('[data-a="doDelete"]'); await pg.wait_for_timeout(300)
        gone=await pg.evaluate(f"!__R.state.days['{T}']"); await pg.click('#toast [data-a="undo"]'); await pg.wait_for_timeout(400)
        ok('削除→取り消しで顔のこわばりも戻る', gone and await pg.evaluate(f"__R.state.days['{T}'].sym.face")==2)
        # 振り返り用に数日へ値を入れる（記録画面から）
        for i,dd in enumerate(sorted(days)[:8]):
            await pg.evaluate(f"__app.go('day',{{date:'{dd}'}})"); await pg.click('[data-a="openRec"]'); await pg.wait_for_timeout(120)
            await pg.click(f'.sheet [data-k="sym.face"][data-v="{[0,1,2,3,2,0,3,1][i]}"]'); await pg.click('.sh-foot [data-a="saveRec"]'); await pg.wait_for_timeout(250)
        await pg.reload(); await pg.wait_for_timeout(800)
        ok('再読み込み後も残る', await pg.evaluate(f"__R.state.days['{T}'].sym.face")==2 and await pg.evaluate("Object.keys(__R.state.days).length")==13)
        # ---- 5) ホームの要約：未記録の件数に含めない ----
        await pg.evaluate("__app.tab('home')"); await pg.wait_for_timeout(200)
        t=await body_text(pg); ok('ホームにエラー表示・undefinedなし', 'undefined' not in t and 'NaN' not in t)
        # ---- 6) 振り返り ----
        await pg.evaluate("__app.tab('insights')"); await pg.wait_for_timeout(200)
        t=await body_text(pg)
        ok('振り返りの入口に顔のこわばり（件数とボタン）', '顔のこわばり 5日' in t and await pg.locator('[data-a="look"][data-sym="face"]').count()==1, [x for x in t.split('\n') if '直近6週' in x])
        await pg.screenshot(path=os.path.join(OUT,'p2_振り返り_入口.png'))
        await pg.click('[data-a="look"][data-sym="face"]'); await pg.wait_for_timeout(300)
        t=await body_text(pg)
        ok('重なり画面：顔のこわばりの件数（中・強 5日／なし・軽い 4日）', '顔のこわばり・緊張が「中・強」の日 5日' in t and '「なし・軽い」の日 4日' in t, [x for x in t.split('\n') if '中・強' in x][:2])
        ok('重なり画面：原因は決めない表示を保つ', '原因' in t and 'おすすめではありません' in t)
        await pg.click('details[data-k="f_days"] summary'); await pg.wait_for_timeout(200)
        t=await body_text(pg)
        ok('前後の表に「顔のこわばり」の行、睡眠・仕事と並ぶ', '顔のこわばり' in t and '睡眠（前夜・時間）' in t and '仕事' in t)
        ok('日の様子に顔のこわばり', (await pg.locator('.daypanel').inner_text()).count('顔のこわばり・緊張')==1)
        await pg.screenshot(path=os.path.join(OUT,'p3_重なり_顔のこわばり.png'),full_page=True)
        # ---- 7) 試す：見る変化に選べる ----
        await pg.evaluate("__app.tab('try')"); await pg.wait_for_timeout(200)
        await pg.click('[data-a="expNew"]'); await pg.wait_for_timeout(200)
        ok('「試す」の見る変化に顔のこわばり', await pg.locator('[data-a="expWatch"][data-k="face"]').count()==1)
        await pg.evaluate("__app.tab('home')")
        # ---- 8) バックアップ→別の端末で復元 ----
        await pg.evaluate("__app.go('settings')")
        async with pg.expect_download() as dl: await pg.click('[data-a="exportBackup"]')
        f=await (await dl.value).path(); bk=json.loads(open(f,encoding='utf-8').read())
        bd=json.loads(bk['body'])['data']['days']
        ok('バックアップに顔のこわばりが入る', bd[T]['sym']['face']==2 and bd[d2]['sym']['face'] is None)
        orig=await pg.evaluate("JSON.stringify(__R.state.days)")
        # 旧形式（顔のこわばりの欄なし）のバックアップも作る
        ob=json.loads(bk['body']);
        for v in ob['data']['days'].values(): v['sym'].pop('face',None)
        obody=json.dumps(ob,ensure_ascii=False); oldbk=dict(bk); oldbk['body']=obody; oldbk['checksum']=hashlib.sha256(obody.encode('utf-8')).hexdigest()
        tmp=tempfile.mkdtemp(); fn=os.path.join(tmp,'new.json'); fo=os.path.join(tmp,'old.json')
        open(fn,'w',encoding='utf-8').write(json.dumps(bk,ensure_ascii=False)); open(fo,'w',encoding='utf-8').write(json.dumps(oldbk,ensure_ascii=False))
        await ctx.close()
        d3=tempfile.mkdtemp(); ctx,pg,errs2=await persistent(p,d3); await pg.goto(URL); await pg.wait_for_timeout(600)
        await pg.click('[data-a="setRole"][data-v="main"]')
        await pg.set_input_files('#fileIn',fn); await pg.wait_for_timeout(400); await pg.click('[data-a="doImport"]'); await pg.wait_for_timeout(600)
        ok('復元で顔のこわばりを含め一致', await pg.evaluate("JSON.stringify(__R.state.days)")==orig)
        await pg.set_input_files('#fileIn',fo); await pg.wait_for_timeout(400); await pg.click('[data-a="doImport"]'); await pg.wait_for_timeout(600)
        st2=await pg.evaluate("__R.state.days")
        ok('旧形式のバックアップも復元でき、顔のこわばりは未記録', len(st2)==13 and all(v['sym']['face'] is None for v in st2.values()) and st2[T]['memo']==json.loads(orig)[T]['memo'])
        await pg.click('#toast [data-a="undoRestore"]'); await pg.wait_for_timeout(600)
        ok('「復元前に戻す」で顔のこわばり入りに戻る', await pg.evaluate(f"__R.state.days['{T}'].sym.face")==2)
        await pg.evaluate(f"__app.go('day',{{date:'{T}'}})"); await pg.wait_for_timeout(200)
        t=await body_text(pg); ok('復元後の日の詳細に「中」', '顔のこわばり・緊張\n中' in t)
        # ---- 9) 画面：はみ出し・小さすぎるボタン ----
        await pg.evaluate(f"__app.open('{T}')"); await pg.wait_for_timeout(300)
        m=await pg.evaluate("""()=>{const rows=[...document.querySelectorAll('.symrow')];const r=rows.find(x=>x.textContent.includes('顔のこわばり'));
          const bs=[...r.querySelectorAll('button')].map(b=>b.getBoundingClientRect());const rr=r.getBoundingClientRect();
          return {sw:document.documentElement.scrollWidth,vw:innerWidth,minH:Math.min(...bs.map(b=>b.height)),right:Math.max(...bs.map(b=>b.right)),rowR:rr.right,n:bs.length}}""")
        ok('記録画面：横のはみ出しなし・ボタン高さ40px以上', m['sw']<=m['vw'] and m['minH']>=40 and m['right']<=m['vw'], m)
        await pg.locator('.symrow:has-text("顔のこわばり")').scroll_into_view_if_needed(); await pg.screenshot(path=os.path.join(OUT,'p4_記録画面_顔のこわばり中.png'))
        await ctx.close()
        # 320px 幅でも確認
        d4=tempfile.mkdtemp(); ctx,pg,errs3=await persistent(p,d4,w=320,h=700); await pg.goto(URL); await pg.wait_for_timeout(600)
        await pg.click('[data-a="setRole"][data-v="main"]'); await pg.evaluate(f"__app.open('{T}')"); await pg.wait_for_timeout(300)
        m=await pg.evaluate("""()=>{const r=[...document.querySelectorAll('.symrow')].find(x=>x.textContent.includes('顔のこわばり'));const bs=[...r.querySelectorAll('button')].map(b=>b.getBoundingClientRect());return {sw:document.documentElement.scrollWidth,vw:innerWidth,right:Math.max(...bs.map(b=>b.right))}}""")
        ok('320px幅：はみ出しなし', m['sw']<=m['vw'] and m['right']<=m['vw'], m)
        await pg.locator('.symrow:has-text("顔のこわばり")').scroll_into_view_if_needed(); await pg.screenshot(path=os.path.join(OUT,'p5_記録画面_320px.png'))
        # 320px幅：主な画面すべて（デモの記録48日分で、文字や表が多い状態）。画面の外だけでなく、カードの枠からのはみ出しも見る
        await pg.evaluate("__demo.set('rich')"); await pg.wait_for_timeout(300)   # 書きかけの画面も閉じる
        over=[]
        for name,js in [('今日',"__app.tab('home')"),('記録',"__app.tab('log')"),('振り返り',"__app.tab('insights')"),('重なり・顔',"__demo.A.look({sym:'face'})"),
                        ('重なり・肌（全部開く）',"(__demo.A.look({sym:'skin'}),document.querySelectorAll('details').forEach(d=>d.open=true))"),('試す',"__app.tab('try')"),('設定',"__app.go('settings')"),
                        ('日の詳細',"__app.go('day',{date:__app.today()})"),('記録画面・体調',"(__app.tab('log'),__app.open(__app.today(),{step:1}))"),
                        ('記録画面・食事',"(__app.tab('log'),__app.open(__app.today(),{step:2}))"),('記録画面・ほか',"(__app.tab('log'),__app.open(__app.today(),{step:3}))")]:
            await pg.evaluate(js); await pg.wait_for_timeout(250)
            r=await pg.evaluate(OVERFLOW_JS)
            if r: over.append((name,r[:3]))
            if name.startswith('記録画面'): await pg.evaluate("__demo.set('rich')"); await pg.wait_for_timeout(200)
        ok('320px幅：主な画面（11画面）で、画面やカードの枠からはみ出さない', not over, over)
        await ctx.close()
        allerr=errs+errs2+errs3; ok('画面のエラーなし', not allerr, allerr[:3])
        for x in (d,d3,d4,tmp): shutil.rmtree(x,ignore_errors=True)
    print('---', sum(1 for r in RES if r[1]), '/', len(RES), '件 合格')
if __name__=="__main__": asyncio.run(main())
