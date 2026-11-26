import json, os, runpy, shutil, sys, time
from pathlib import Path
here=Path.cwd()/'build/offline-ide-audit'; sys.path.insert(0,str(here))
ns=runpy.run_path(str(here/'run-rust-owned-window.py'),run_name='gitlab_ssh_documentation_only')
os.environ['GIT_TERMINAL_PROMPT']='0'; os.environ['GCM_INTERACTIVE']='Never'
os.environ['GIT_SSH_COMMAND']='ssh -oBatchMode=yes -oStrictHostKeyChecking=yes -oConnectTimeout=12'
root=Path.cwd(); head=ns['head_identity'](root); branch=head['head'].removeprefix('ref: '); target=head['revision']
run=here/('readme-push-'+target[:12]); url='git@gitlab.com:azurekiln-team/qflistudio-rust.git'; git=shutil.which('git.exe')
start=time.monotonic(); push=ns['run_owned']('gitlab existing SSH push',[git,'push',url,target+':'+branch],root,run/'gitlab-ssh-push.log',start+30,start+35)
result={'commit':target,'push':push,'exactHashVerified':False}
if push['exit']==0:
 start=time.monotonic(); verify=ns['run_owned']('gitlab SSH verify',[git,'ls-remote','--exit-code',url,branch],root,run/'gitlab-ssh-verify.log',start+20,start+25)
 raw=(run/'gitlab-ssh-verify.log').read_text(encoding='utf-8',errors='replace')
 result.update(verify=verify,exactHashVerified=verify['exit']==0 and any(line.split()==[target,branch] for line in raw.splitlines()))
(run/'gitlab-ssh-report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print('GITLAB_SSH_VERIFIED',result['exactHashVerified'],flush=True)
raise SystemExit(0 if result['exactHashVerified'] else 1)
