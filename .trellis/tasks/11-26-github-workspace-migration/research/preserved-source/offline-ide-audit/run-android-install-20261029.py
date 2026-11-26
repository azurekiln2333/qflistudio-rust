import time
START=time.monotonic()
import os,json,hashlib,importlib.util,sys
from pathlib import Path
ROOT=Path.cwd();RUN=ROOT/'build/offline-ide-audit/android-release-20261028T161947Z';APK=ROOT/'build/app/outputs/flutter-apk/app-release.apk'
assert APK.stat().st_size==98915757 and hashlib.sha256(APK.read_bytes()).hexdigest()=='3e404c0b4be439747533f398cdfcd1704c68183a5e00ba43ade881c138d1c398'
p=ROOT/'build/offline-ide-audit/send-production-hap.py';s=importlib.util.spec_from_file_location('owned_install',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.MODULE_STARTED=START
ADB='D:/ProgramFiles/platform-tools/adb.exe';TARGET='192.168.68.236:39643';results=[]
def run(name,args,seconds):
 r=m.run_owned(name,[ADB,'-s',TARGET]+args,ROOT,RUN/(name+'.log'),min(START+170,time.monotonic()+seconds),START+180);results.append(r)
 while m.RETAINED_CUSTODIANS:
  print('HOLD',json.dumps(m.public_custodians()),flush=True);m.drain_custodians(time.monotonic()+5);time.sleep(1)
 assert r['exit']==0 and r['resourceReleased'],name+' failed'
 return (RUN/(name+'.log')).read_text(encoding='utf-8',errors='replace')
report={'target':TARGET,'package':'com.azurekiln.qfli.rustcore','apkSha256':'3e404c0b4be439747533f398cdfcd1704c68183a5e00ba43ade881c138d1c398','results':results,'exit':1}
try:
 assert run('serial',['shell','getprop','ro.serialno'],8).strip()=='d361e7a0','device identity changed'
 assert run('abi',['shell','getprop','ro.product.cpu.abi'],8).strip()=='arm64-v8a','device ABI changed'
 output=run('install',['install','-r',str(APK)],120)
 assert any(line.strip()=='Success' for line in output.splitlines()),'ADB textual success absent: '+output
 report['installTextSuccess']=True
 path=run('installed-path',['shell','pm','path','com.azurekiln.qfli.rustcore'],10)
 assert 'package:' in path and 'base.apk' in path
 package=run('installed-package',['shell','dumpsys','package','com.azurekiln.qfli.rustcore'],10)
 assert 'versionCode=1000000' in package and 'versionName=1.0.0' in package
 report['installedPath']=path.strip();report['versionVerified']=True;report['exit']=0
except BaseException as e:
 report['error']=repr(e)
finally:
 report['elapsedSeconds']=time.monotonic()-START;report['allOwnedJobsEmpty']=all(r.get('emptyJob') for r in results);report['checkedHandlesClosed']=all(r.get('handleClose',{}).get('closed') for r in results)
 (RUN/'install-result.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('INSTALL_RESULT',json.dumps(report),flush=True)
sys.exit(report['exit'])
