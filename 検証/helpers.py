import json, datetime, os, shutil, tempfile
# 実行環境の設定（日付・置き場所を固定しない。どの日に、どの端末で再実行しても同じ確認になるように）
HERE=os.path.dirname(os.path.abspath(__file__))
URL=os.environ.get('KARADA_URL','http://127.0.0.1:8765/')   # run_all.py が空いているポートで配信して設定する
def _find_chrome():
    if os.environ.get('KARADA_CHROME'): return os.environ['KARADA_CHROME']
    for c in [r'C:/Program Files/Google/Chrome/Application/chrome.exe', r'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
              '/usr/bin/google-chrome', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']:
        if os.path.exists(c): return c
    return shutil.which('google-chrome') or shutil.which('chrome')   # 見つからなければ None（Playwright 同梱のブラウザを使う）
CHROME=_find_chrome()
TMP=os.environ.get('KARADA_TMP') or tempfile.mkdtemp(prefix='karada_test_')
def tmp(name): return os.path.join(TMP,name)
# 別の日に実行した場合の確認用：KARADA_FAKE_NOW='2027-03-01T10:00:00+09:00' のように指定すると、
# ブラウザの時計をその日時にして全体を実行する（指定しなければ実際の今日）
FAKE_NOW=os.environ.get('KARADA_FAKE_NOW')
def jst_today():
    """アプリと同じ「日本時間の今日」（YYYY-MM-DD）"""
    now=datetime.datetime.fromisoformat(FAKE_NOW) if FAKE_NOW else datetime.datetime.now(datetime.timezone.utc)
    return (now.astimezone(datetime.timezone.utc)+datetime.timedelta(hours=9)).date().isoformat()
async def set_clock(pg, when=None):
    """ブラウザの時計を合わせる。when を省くと KARADA_FAKE_NOW（未指定なら何もしない）"""
    t=when or FAKE_NOW
    if not t: return
    t=datetime.datetime.fromisoformat(t) if isinstance(t,str) else t
    try: await pg.clock.install(time=t)
    except Exception: await pg.clock.set_system_time(t)   # すでに入っている場合は時刻だけ変える
def days_ago(n, base=None):
    return (datetime.date.fromisoformat(base or jst_today())-datetime.timedelta(days=n)).isoformat()
def fake_wx(today, past_days):
    """Open-Meteo 公開仕様の形の応答（試験用）"""
    d0=datetime.date.fromisoformat(today)-datetime.timedelta(days=past_days)
    days=[(d0+datetime.timedelta(days=i)).isoformat() for i in range(past_days+1)]
    hrs=[f"{d}T{h:02d}:00" for d in days for h in range(24)]
    return {"latitude":34.66,"longitude":133.93,"timezone":"Asia/Tokyo","daily_units":{"time":"iso8601","weather_code":"wmo code","temperature_2m_max":"°C","temperature_2m_min":"°C","precipitation_sum":"mm"},
      "daily":{"time":days,"weather_code":[[0,3,61,1][i%4] for i in range(len(days))],"temperature_2m_max":[15.2+i%3 for i in range(len(days))],"temperature_2m_min":[6.1 for _ in days],"precipitation_sum":[0.0 if i%4!=2 else 4.5 for i in range(len(days))]},
      "hourly_units":{"time":"iso8601","relative_humidity_2m":"%","surface_pressure":"hPa"},
      "hourly":{"time":hrs,"relative_humidity_2m":[50+(k//24)%5*5 for k in range(len(hrs))],"surface_pressure":[1010-(k//24)%3*3 for k in range(len(hrs))]}}
async def new_page(p, width=390, height=844, wx='ok', storage=None, clock=None, ua=None):
    b=await p.chromium.launch(executable_path=CHROME,args=['--no-sandbox'])
    kw=dict(viewport={'width':width,'height':height},device_scale_factor=2 if width<500 else 1,reduced_motion='reduce',accept_downloads=True)
    if ua: kw['user_agent']=ua
    ctx=await b.new_context(**kw)
    calls=[]
    async def route(r):
        calls.append(r.request.url)
        if wx=='ok':
            import urllib.parse as up
            q=dict(up.parse_qsl(up.urlparse(r.request.url).query)); pd=int(q.get('past_days','0'))
            today=await r.request.frame.evaluate("__app.today()") if False else None
            await r.fulfill(status=200, content_type='application/json', body=json.dumps(fake_wx(ctx._today, pd)))
        else:
            await r.abort()
    ctx._today=None
    await ctx.route('https://api.open-meteo.com/**', route)
    pg=await ctx.new_page(); errs=[]
    pg.on('pageerror',lambda e:errs.append(str(e)))
    pg.on('console',lambda m: errs.append('console:'+m.text) if m.type=='error' and 'open-meteo' not in m.text and 'ERR_FAILED' not in m.text else None)
    if clock: await pg.clock.install(time=clock)
    return b,ctx,pg,errs,calls
