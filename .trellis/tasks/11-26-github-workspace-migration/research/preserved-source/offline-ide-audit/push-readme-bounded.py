"""Push the reviewed documentation with bounded, noninteractive owned Git jobs."""
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
runner = runpy.run_path(str(HERE / 'run-rust-owned-window.py'), run_name='git_documentation_only')
run_owned = runner['run_owned']
os.environ['GIT_TERMINAL_PROMPT'] = '0'
os.environ['GCM_INTERACTIVE'] = 'Never'
os.environ['GCM_GUI_PROMPT'] = '0'
git = shutil.which('git.exe') or shutil.which('git')
if not git:
    raise SystemExit('Git executable unavailable')
head = runner['head_identity'](ROOT)
branch = head['head'].removeprefix('ref: ')
if not branch.startswith('refs/heads/'):
    raise SystemExit('Expected named branch')
target = head['revision']
run = HERE / ('readme-push-' + target[:12])
run.mkdir(exist_ok=False)
report = {'commit': target, 'branch': branch, 'results': []}
urls = [
 ('github', 'https://github.com/azurekiln2333/qflistudio-rust.git'),
 ('gitee', 'https://gitee.com/azurekiln/qflistudio-rust.git'),
 ('gitlab', 'https://gitlab.com/azurekiln-team/qflistudio-rust.git'),
 ('gitcode', 'https://gitcode.com/azurekiln/qflistudio-rust.git'),
 ('cnb', 'https://cnb.cool/azurekiln/qflistudio-rust'),
]
base = [git, '-c', 'credential.interactive=false', '-c', 'http.lowSpeedLimit=1', '-c', 'http.lowSpeedTime=20']
for name, url in urls:
    started = time.monotonic()
    push = run_owned(name+' push', base+['push', url, target+':'+branch], ROOT,
                     run/(name+'-push.log'), started+40, started+45)
    started = time.monotonic()
    verify = run_owned(name+' verify', base+['ls-remote', '--exit-code', url, branch], ROOT,
                       run/(name+'-verify.log'), started+20, started+25)
    raw = (run/(name+'-verify.log')).read_text(encoding='utf-8',errors='replace')
    verified = verify['exit']==0 and any(line.split()==[target,branch] for line in raw.splitlines())
    row = {'remote':name, 'url':url, 'push':push, 'verify':verify, 'exactHashVerified':verified}
    report['results'].append(row)
    (run/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('REMOTE_RESULT',name,'pushExit='+str(push['exit']),'exactHashVerified='+str(verified),flush=True)
report['allVerified'] = all(row['exactHashVerified'] for row in report['results'])
(run/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('REPORT',str(run/'report.json'), 'ALL_VERIFIED',report['allVerified'],flush=True)
raise SystemExit(0 if report['allVerified'] else 1)
