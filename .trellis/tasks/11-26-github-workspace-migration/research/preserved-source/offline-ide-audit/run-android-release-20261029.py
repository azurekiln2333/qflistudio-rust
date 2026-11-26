import time
ORIGIN=time.monotonic()
import os,sys,json,hashlib,importlib.util,subprocess
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path.cwd()
RUN=ROOT/'build/offline-ide-audit'/('android-release-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
RUN.mkdir(parents=True,exist_ok=True)
helper=ROOT/'build/offline-ide-audit/send-production-hap.py'
assert hashlib.sha256(helper.read_bytes()).hexdigest()=='d09259728dcf804a3ebff51bf677fd5b93f4ad655a661e7232cc76d072e4535c'
spec=importlib.util.spec_from_file_location('owned_android',helper)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.MODULE_STARTED=ORIGIN
os.environ['JAVA_HOME']='D:/ProgramFiles/Android/Android Studio/jbr'
os.environ['ANDROID_HOME']='D:/ProgramData/Android/Sdk'
os.environ['ANDROID_SDK_ROOT']=os.environ['ANDROID_HOME']
os.environ['GRADLE_OPTS']='-Dorg.gradle.jvmargs="-Xmx1024m -XX:MaxMetaspaceSize=384m -XX:ReservedCodeCacheSize=128m" -Dorg.gradle.workers.max=1 -Dorg.gradle.parallel=false -Dorg.gradle.project.kotlin.compiler.execution.strategy=in-process'
os.environ['PATH']=os.environ['JAVA_HOME']+'/bin;D:/ProgramData/Android/Sdk/platform-tools;'+os.environ['PATH']
os.environ['FLUTTER_SUPPRESS_ANALYTICS']='true'
local=ROOT/'android/local.properties'; before=local.read_bytes();(RUN/'local.properties.before').write_bytes(before)
paths=list((ROOT/'lib').rglob('*.dart'))+[ROOT/'pubspec.yaml',ROOT/'pubspec.lock',ROOT/'android/app/build.gradle.kts',ROOT/'android/gradle.properties']
snapshot={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
cmd=['D:/ProgramFiles/flutter_ohos/bin/cache/dart-sdk/bin/dart.exe','D:/ProgramFiles/flutter_ohos/bin/cache/flutter_tools.snapshot','build','apk','--release','--target-platform','android-arm64','--build-number','1000000','--dart-define=QFLI_DIAG_TABBAR=false','--dart-define=QFLI_PERF=false','--no-android-gradle-daemon','-t','lib/main.dart']
report={'parentPid':os.getpid(),'run':str(RUN),'command':cmd,'status':'running','startedUtc':datetime.now(timezone.utc).isoformat()}
(RUN/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('ANDROID_RUN',str(RUN),flush=True)
result=m.run_owned('android-release-build',cmd,ROOT,RUN/'build.log',ORIGIN+520,ORIGIN+550)
report['build']=result
while m.RETAINED_CUSTODIANS:
 print('HOLD',json.dumps(m.public_custodians()),flush=True)
 m.drain_custodians(time.monotonic()+5)
 time.sleep(1)
report['localPropertiesRestored']=False
if result['resourceReleased']:
 current=local.read_bytes()
 # Flutter owns only generated local.properties. Preserve any unexpected key drift.
 def props(b):
  return dict(line.split('=',1) for line in b.decode('utf-8').splitlines() if '=' in line and not line.startswith('#'))
 a,b=props(before),props(current)
 allowed={'flutter.buildMode','flutter.versionName','flutter.versionCode','flutter.sdk','sdk.dir'}
 assert all(a.get(k)==b.get(k) for k in set(a)|set(b) if k not in allowed),'Unexpected local.properties drift'
 local.write_bytes(before);report['localPropertiesRestored']=local.read_bytes()==before
report['sourceInputDiffs']=[p for p,h in snapshot.items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
apk=ROOT/'build/app/outputs/flutter-apk/app-release.apk'
if result['exit']==0 and apk.is_file():
 report['artifact']={'path':str(apk),'bytes':apk.stat().st_size,'mtimeNs':apk.stat().st_mtime_ns,'sha256':hashlib.sha256(apk.read_bytes()).hexdigest()}
report['elapsedSeconds']=time.monotonic()-ORIGIN
report['exit']=0 if result['exit']==0 and result['resourceReleased'] and not report['sourceInputDiffs'] and report['localPropertiesRestored'] else 1
report['status']='passed' if report['exit']==0 else 'failed'
(RUN/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('ANDROID_RESULT',json.dumps(report),flush=True)
sys.exit(report['exit'])

