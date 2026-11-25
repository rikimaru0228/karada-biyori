# からだ日和：自動検証をまとめて実行する（日付・ポート・置き場所を固定しない）
# usage: python run_all.py [公開用フォルダ（既定：この検証フォルダの1つ上）] [結果の保存先（既定：検証/結果/。git には入れない）]
#  - 公開用フォルダを一時フォルダへ写し、更新の試験用の v2ok/v2ng もそこに作る（公開用フォルダには何も足さない）
#  - 空いているポートで配信し、t_core / t_more / t_face を順に実行して結果を保存する
import os, sys, shutil, subprocess, tempfile, socket, datetime, re, time
HERE=os.path.dirname(os.path.abspath(__file__))
SRC=os.path.abspath(sys.argv[1] if len(sys.argv)>1 else os.path.join(HERE,'..'))
OUTDIR=os.path.abspath(sys.argv[2] if len(sys.argv)>2 else os.path.join(HERE,'結果','自動実行_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')))
_base,_i=OUTDIR,1
while os.path.exists(OUTDIR): _i+=1; OUTDIR=f'{_base}_{_i}'   # 既存の結果は上書きしない（同じ名前があれば別名）
os.makedirs(OUTDIR)
work=tempfile.mkdtemp(prefix='karada_srv_'); srv=os.path.join(work,'site')
shutil.copytree(SRC,srv,ignore=shutil.ignore_patterns('.git','検証','.gitignore'))
html=open(os.path.join(srv,'index.html'),encoding='utf-8').read()
assert 'const SCHEMA = 1;' in html and 'const MIGRATIONS={ };' in html, '版の書き方が想定と違います（v2ok/v2ng を作れません）'
v2ok=html.replace('const SCHEMA = 1;','const SCHEMA = 2;').replace('const MIGRATIONS={ };',"const MIGRATIONS={ 1:(st)=>({...st,prefs:{...(st.prefs||{}),migratedToV2:true}}) };")
v2ng=html.replace('const SCHEMA = 1;','const SCHEMA = 2;')
for name,body in [('v2ok',v2ok),('v2ng',v2ng)]:
    os.makedirs(os.path.join(srv,name)); open(os.path.join(srv,name,'index.html'),'w',encoding='utf-8',newline='').write(body)
s=socket.socket(); s.bind(('127.0.0.1',0)); port=s.getsockname()[1]; s.close()   # 空いているポート（他のアプリのポートには触れない）
server=subprocess.Popen([sys.executable,'-m','http.server',str(port),'--bind','127.0.0.1'],cwd=srv,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
env=dict(os.environ,KARADA_URL=f'http://127.0.0.1:{port}/',KARADA_TMP=os.path.join(work,'tmp'),PYTHONIOENCODING='utf-8')
os.makedirs(env['KARADA_TMP'])
summary=[]
try:
    time.sleep(1)
    for t,args in [('t_core',[]),('t_more',[]),('t_face',[os.path.join(OUTDIR,'画面')])]:
        r=subprocess.run([sys.executable,os.path.join(HERE,t+'.py'),*args],env=env,capture_output=True,text=True,encoding='utf-8',timeout=900)
        out=r.stdout+'\n--- stderr ---\n'+r.stderr+f'\n--- 終了コード {r.returncode} ---\n'   # 実行ログ全体を残す
        open(os.path.join(OUTDIR,f'{t}_結果.txt'),'w',encoding='utf-8').write(out)
        m=re.search(r'--- (\d+) / (\d+)',r.stdout); line=(f"{t}: {m.group(1)}/{m.group(2)}" if m else f"{t}: 途中で停止")+f"（終了コード {r.returncode}）"
        summary.append(line); print(line, flush=True)
finally:
    server.terminate(); server.wait(10); shutil.rmtree(work,ignore_errors=True)
head=f"実行日時 {datetime.datetime.now().isoformat(timespec='seconds')}／日本時間の今日 {(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=9)).date()}／対象 {SRC}\n"
open(os.path.join(OUTDIR,'まとめ.txt'),'w',encoding='utf-8').write(head+'\n'.join(summary)+'\n')
print('結果:',OUTDIR)
sys.exit(0 if all(re.search(r': (\d+)/\1（終了コード 0）$',x) for x in summary) else 1)
