import json,os,subprocess,time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from gearshift.gui import Window
from gearshift.measurement import read_csv
SDK='/tmp/gearshift-sdk/tools/python_env/idf5.5_py3.13_env/bin/python'
app=QApplication([])
for mode,source in [('live','models/mlp-v2/reference-windows.jsonl'),('benchmark','docs/evidence/issue-7/benchmark-windows.jsonl')]:
 out=Path('results/issue-7')/('gui-'+mode);out.mkdir(exist_ok=False)
 reset=subprocess.run([SDK,'-m','esptool','--chip','esp32','--port','/dev/ttyUSB0','read_mac'],capture_output=True,text=True,timeout=15)
 (out/'reset.log').write_text(reset.stdout+reset.stderr);assert reset.returncode==0
 time.sleep(1)
 w=Window();w.resize(1100,1050);w.device.setCurrentIndex(2);w.mode.setCurrentIndex(0 if mode=='live' else 1);w.input.setText(source)
 for period,box in w.profiles:box.setChecked(period==10)
 w.show();app.processEvents();w.start()
 deadline=time.monotonic()+180
 while not w.finished and time.monotonic()<deadline:
  app.processEvents();time.sleep(.005)
 assert w.finished,'GUI worker did not finish'
 rows=w.session.rows
 (out/'events.jsonl').write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in rows))
 assert rows[-1]['event']=='run_complete',rows[-1]
 assert all(r['simulated'] is False and r['mode']==mode for r in rows)
 expected=11 if mode=='live' else 3100
 results=[r for r in rows if r['event']=='result']
 assert len(results)==expected and all(r['status']=='ok' for r in results)
 assert 'ESP32' in w.status.text() and 'ESP32' in w.origin.text()
 w.export_to(str(out/'events.csv'))
 while w.export_thread.is_alive() and time.monotonic()<deadline:
  app.processEvents();time.sleep(.005)
 app.processEvents();w.poll()
 assert read_csv(out/'events.csv')==rows
 assert 'ESP32' in w.export_status.text()
 w.grab().save('docs/evidence/issue-7/gui-hardware-'+mode+'.png')
 w.close();app.processEvents()
 print(json.dumps(dict(mode=mode,hardware=True,results=expected,all_ok=True,csv_roundtrip=True)),flush=True)
