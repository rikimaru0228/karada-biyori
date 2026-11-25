# 版の更新の確認：古いコミットを配信して開き、同じアドレスで新しいコミットに差し替えて更新されるかを見る（架空データのみ）
# usage: python t_update.py <古いコミット> <新しいコミット> [結果の保存先]
#  - 2つのコミットを一時フォルダへ取り出し、空いているポートで順に配信する（同じアドレス＝実際の更新と同じ条件）
#  - 中身の確認は t_live.py（first → update）。天気は実際の Open-Meteo に問い合わせる
#  - ブラウザのプロファイルは一時フォルダ（%TEMP%）に作る
import os, sys, subprocess, tempfile, socket, time, io, tarfile, re, urllib.request, datetime, shutil
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, '..'))
OLD, NEW = sys.argv[1], sys.argv[2]
OUT = os.path.abspath(sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, '結果', f'更新確認_{OLD}から{NEW}_' + datetime.datetime.now().strftime('%Y%m%d_%H%M%S')))
base, i = OUT, 1
while os.path.exists(OUT): i += 1; OUT = f'{base}_{i}'
os.makedirs(OUT)
work = tempfile.mkdtemp(prefix='karada_upd_')
def extract(commit, dst):
    tar = subprocess.run(['git', '-C', REPO, 'archive', commit], capture_output=True, check=True).stdout
    tarfile.open(fileobj=io.BytesIO(tar)).extractall(dst, filter='data')
    shutil.rmtree(os.path.join(dst, '検証'), ignore_errors=True)
    return re.search(r"PREFIX \+ '([^']+)'", open(os.path.join(dst, 'sw.js'), encoding='utf-8').read()).group(1)
ver = {}
for name, c in (('old', OLD), ('new', NEW)): ver[name] = extract(c, os.path.join(work, name))
s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
url = f'http://127.0.0.1:{port}/'; prof = os.path.join(work, 'profile')
env = dict(os.environ, PYTHONIOENCODING='utf-8')
log = []
def serve(name):
    p = subprocess.Popen([sys.executable, '-m', 'http.server', str(port), '--bind', '127.0.0.1'], cwd=os.path.join(work, name), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        try:
            sw = urllib.request.urlopen(url + 'sw.js', timeout=2).read().decode('utf-8')
            if ver[name] in sw: return p
        except Exception: pass
        time.sleep(0.25)
    p.terminate(); p.wait(10); raise SystemExit(f'{name} の配信を確認できません')
def stop(p):
    p.terminate(); p.wait(10)
code = 0
try:
    for name, phase in (('old', 'first'), ('new', 'update')):
        p = serve(name)
        try:
            r = subprocess.run([sys.executable, os.path.join(HERE, 't_live.py'), url, prof, phase, os.path.join(OUT, '画面'), 'karada-shell-' + ver[name]],
                               env=env, capture_output=True, text=True, encoding='utf-8', timeout=600)
        finally:
            stop(p)
        out = r.stdout + '\n--- stderr ---\n' + r.stderr + f'\n--- 終了コード {r.returncode} ---\n'
        open(os.path.join(OUT, f'{phase}_{ver[name]}_結果.txt'), 'w', encoding='utf-8').write(out)
        m = re.search(r'--- (\d+) / (\d+)', r.stdout)
        line = (f'{phase}（{ver[name]}）: {m.group(1)}/{m.group(2)}' if m else f'{phase}（{ver[name]}）: 途中で停止') + f'（終了コード {r.returncode}）'
        log.append(line); print(line, flush=True)
        if r.returncode or not m or m.group(1) != m.group(2): code = 1
finally:
    shutil.rmtree(work, ignore_errors=True)
open(os.path.join(OUT, 'まとめ.txt'), 'w', encoding='utf-8').write(f'実行日時 {datetime.datetime.now().isoformat(timespec="seconds")}／{OLD}（{ver["old"]}）→ {NEW}（{ver["new"]}）\n' + '\n'.join(log) + '\n')
print('結果:', OUT)
sys.exit(code)
