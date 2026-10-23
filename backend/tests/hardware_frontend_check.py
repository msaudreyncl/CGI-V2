"""Isolated Chromium behavior check using the existing PHP template and JS.

Run: venv/bin/python backend/tests/hardware_frontend_check.py
Requires optional `pip install playwright==1.51.0` and /usr/bin/chromium.
PHP-generated values, Bootstrap modal and APIs are substituted; this checks DOM
behavior, not the deployed page layout or physical touchscreen.
"""
import re, json, io, base64
from PIL import Image
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[2]
def jpeg(color):
    image = io.BytesIO()
    Image.new('RGB', (16, 9), color).save(image, format='JPEG')
    return base64.b64encode(image.getvalue()).decode()

html=re.sub(r'<\?.*?\?>','', (root/'frontend/dashboard.php').read_text(), flags=re.S)
html=re.sub(r'<script\b[^>]*>.*?</script>','',html,flags=re.S)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':800,'height':480})
    page.route('**/*',lambda route: route.fulfill(body=html,content_type='text/html') if route.request.url=='http://cgi.test/' else route.abort())
    page.goto('http://cgi.test/')
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.evaluate('(frames) => { window.framesForTest = frames; }', [jpeg('red'), jpeg('blue'), jpeg('green')])
    page.evaluate('''() => {
      for(let i=1;i<=6;i++){let el=document.createElement('span');el.id='step-badge-'+i;document.body.appendChild(el);}
      window.bootstrap={Modal: class {constructor(el){this.el=el} show(){this.el.style.display='block'} hide(){this.el.dispatchEvent(new Event('hidden.bs.modal'))}}};
      window.mockWeight={weight_g:350,stable:true,in_range:true};
      window.failWeight=false; window.captures=[]; window.saved=[];
      window.profileMode='existing'; window.profileCreates=0; window.initPayloads=[];
      window.hardwareStatus={camera:'error',scale:'ready',printer:'warning',details:{camera:'Cannot reach Pi service'}};
      window.previewCount=0; window.failPreview=false; window.failCapture=false; window.analysisPayload=null;
      window.CGI_API={
       get:async path => {
         if(path === '/api/users/1/farmer') {
           const found = window.profileMode === 'existing';
           const denied = window.profileMode === 'denied';
           return {ok:found,status:found?200:denied?403:404,json:async()=>found?{id:7,user_id:1}:{detail:denied?'Access denied':'Farmer profile not found'}};
         }
         return {ok:!window.failWeight,json:async()=>path.endsWith('/status')?window.hardwareStatus:window.mockWeight};
       },
       post:async (path,body) => {
         if(path === '/api/users/1/farmer') {
           window.profileCreates++;
           const conflict=window.profileMode === 'conflict';
           window.profileMode='existing';
           return {ok:!conflict,status:conflict?409:201,json:async()=>conflict?{detail:'Already exists'}:{id:7,user_id:1}};
         }
         if(path.endsWith('/init')) window.initPayloads.push(body);
         if(path === '/api/hardware/weight' && body.action.startsWith('calibration_')) {
           window.calibrationActions = (window.calibrationActions || []).concat([body]);
           return {ok:true,json:async()=>({token:'test-calibration',calibrated:body.action==='calibration_finish'})};
         }
         if(path === '/api/hardware/weight' && body.action === 'tare')
           window.mockWeight={weight_g:0,stable:false,in_range:false};
         if(path.endsWith('/capture')) {
           if(body.preview) window.previewCount++;
           else window.captures.push(body.view);
           const fail = body.preview ? window.failPreview : window.failCapture;
           return {ok:!fail,json:async()=> fail ? {detail:'Camera disconnected'} : {
             image_b64: window.framesForTest[body.preview ? 2 : body.view === 'A' ? 0 : 1],
             preview:!!body.preview,simulated:false
           }};
         }
         if(path.endsWith('/capture-dual')) {
           window.analysisPayload=body;
           return {ok:false,json:async()=>({detail:'Analysis intentionally stopped after payload check'})};
         }
         return {ok:true,json:async()=>path.endsWith('/init')?{pending_id:42,txn_number:'CGI-TEST'}:{tared:true}};
       },
       put:async (path,body)=>{window.saved.push(body.weight_g);return {ok:true,json:async()=>({})}}
      };
      document.getElementById('farmer-select').innerHTML='<option value="1">Test Farmer</option>';
    }''')
    page.add_script_tag(content=(root/'frontend/assets/js/dashboard.js').read_text())
    assert not errors,errors
    # DOM-level click avoids Bootstrap CSS dependency in this isolated harness.
    def click(id):page.locator('#'+id).evaluate('(el)=>el.click()')
    click('btn-start-txn')
    page.wait_for_timeout(100)
    page.locator('.prep-check').evaluate_all('(els)=>els.forEach(el=>{el.checked=true;el.dispatchEvent(new Event("change"))})')
    assert page.locator('#btn-to-weight').is_disabled()
    assert 'Cannot reach Pi service' in page.locator('#hw-label-camera').inner_text()
    page.evaluate("window.hardwareStatus={camera:'ready',scale:'ready',printer:'warning',details:{}}")
    click('btn-recheck-hw');page.wait_for_timeout(100)
    assert not page.locator('#btn-to-weight').is_disabled()
    click('btn-to-weight');page.wait_for_timeout(150)
    assert page.evaluate('window.initPayloads') == [{'farmer_id':7}]
    assert page.evaluate('window.profileCreates') == 0
    assert not page.locator('#btn-to-capture').is_disabled()
    assert page.locator('#live-weight-value').inner_text() == '350.00 g'
    dialogs=[]
    def calibration_dialog(dialog):
        dialogs.append(dialog.message)
        if dialog.type == 'prompt': dialog.accept('350')
        else: dialog.accept()
    page.on('dialog', calibration_dialog)
    click('btn-calibrate-scale');page.wait_for_timeout(250)
    actions=page.evaluate('window.calibrationActions')
    assert [a['action'] for a in actions] == ['calibration_zero','calibration_load','calibration_finish']
    assert actions[1]['known_g'] == 350 and actions[1]['token'] == 'test-calibration'
    assert len(dialogs) == 5
    assert not page.locator('#btn-calibrate-scale').is_disabled()
    page.remove_listener('dialog', calibration_dialog)
    # Cancelling at the mass prompt releases the session and resumes polling.
    def cancel_dialog(dialog):
        if dialog.type == 'prompt': dialog.dismiss()
        else: dialog.accept()
    page.on('dialog', cancel_dialog)
    click('btn-calibrate-scale');page.wait_for_timeout(250)
    assert [a['action'] for a in page.evaluate('window.calibrationActions')][-2:] == ['calibration_zero','calibration_cancel']
    page.remove_listener('dialog', cancel_dialog)
    page.evaluate('window.mockWeight={weight_g:0,stable:true,in_range:false}');page.wait_for_timeout(600)
    assert page.locator('#live-weight-value').inner_text() == '0.00 g'
    page.evaluate('window.mockWeight={weight_g:125.37,stable:true,in_range:false}');page.wait_for_timeout(600)
    assert page.locator('#live-weight-value').inner_text() == '125.37 g'
    page.evaluate("window.mockWeight={weight_g:-123.456789,stable:false,in_range:false,weight_test_mode:true,simulated:false,measured_at:'2026-10-23T01:00:00+00:00'}");page.wait_for_timeout(600)
    assert page.locator('#live-weight-value').inner_text() == '-123.46 g'
    assert not page.locator('#btn-to-capture').is_disabled()
    assert 'calibration bypassed' in page.locator('#weight-status-badge').inner_text()
    page.evaluate("window.failWeight=true");page.wait_for_timeout(600)
    assert page.locator('#btn-to-capture').is_disabled()
    assert page.locator('#live-weight-value').inner_text() == '— g'
    assert 'Error' in page.locator('#hw-label-scale').inner_text()
    page.evaluate("window.failWeight=false;window.mockWeight={weight_g:350,stable:true,in_range:true}");page.wait_for_timeout(600)
    click('btn-tare-scale');page.wait_for_timeout(150)
    assert page.locator('#live-weight-value').inner_text() == '0.00 g'
    assert page.locator('#btn-to-capture').is_disabled()
    page.evaluate('window.mockWeight={weight_g:350.27,stable:false,in_range:true}');page.wait_for_timeout(600)
    assert page.locator('#btn-to-capture').is_disabled()
    assert 'Stabilizing' in page.locator('#weight-status-badge').inner_text()
    page.evaluate('window.mockWeight={weight_g:-125.37,stable:true,in_range:false}');page.wait_for_timeout(600)
    assert page.locator('#live-weight-value').inner_text() == '-125.37 g'
    assert page.locator('#btn-to-capture').is_disabled()
    page.evaluate("window.mockWeight={weight_g:null,stable:false,in_range:false,measurement_state:'unstable',error:'Scale moving or noisy'}")
    page.wait_for_timeout(600)
    assert page.locator('#live-weight-value').inner_text() == '— g'
    assert 'moving or noisy' in page.locator('#weight-status-badge').inner_text()
    assert page.locator('#btn-to-capture').is_disabled()
    page.evaluate('window.mockWeight={weight_g:350,stable:true,in_range:true}');page.wait_for_timeout(600)
    page.evaluate('window.failWeight=true');page.wait_for_timeout(600)
    assert page.locator('#btn-to-capture').is_disabled()
    page.evaluate('window.failWeight=false;window.mockWeight.weight_g=339');page.wait_for_timeout(600)
    assert page.locator('#btn-to-capture').is_disabled()
    page.evaluate('window.mockWeight.weight_g=350');page.wait_for_timeout(600)
    click('btn-tare-scale');page.wait_for_timeout(600)
    assert page.locator('#btn-to-capture').is_disabled()
    page.evaluate('window.mockWeight={weight_g:350,stable:true,in_range:true}');page.wait_for_timeout(600)
    assert not page.locator('#btn-to-capture').is_disabled()
    click('btn-to-capture');page.wait_for_timeout(100)
    assert page.evaluate('window.saved')==[350]
    page.wait_for_function("document.getElementById('camera-live-preview').getAttribute('src') !== null")
    assert 'Ready' in page.locator('#camera-live-status').inner_text()
    page.evaluate('window.failPreview=true');page.wait_for_timeout(650)
    assert 'unavailable' in page.locator('#camera-live-status').inner_text()
    assert page.locator('#camera-live-preview').get_attribute('src') is None
    page.evaluate('window.failPreview=false');page.wait_for_timeout(650)
    assert 'Ready' in page.locator('#camera-live-status').inner_text()
    page.evaluate('window.failCapture=true')
    click('btn-capture-a');page.wait_for_timeout(3700)
    assert not page.locator('#btn-capture-a').is_disabled()
    assert 'd-none' in page.locator('#btn-accept-a').get_attribute('class')
    page.evaluate('window.failCapture=false')
    click('btn-capture-a');page.wait_for_timeout(3700);click('btn-accept-a')
    assert 'd-none' not in page.locator('#reorient-instruction').get_attribute('class')
    click('btn-capture-b');page.wait_for_timeout(3700)
    assert page.locator('#btn-to-analyze').is_disabled()
    click('btn-accept-b');assert not page.locator('#btn-to-analyze').is_disabled()
    click('btn-to-analyze');page.wait_for_timeout(650)
    preview_count=page.evaluate('window.previewCount')
    page.wait_for_timeout(650)
    assert page.evaluate('window.previewCount') == preview_count
    click('btn-start-analysis');page.wait_for_timeout(100)
    payload=page.evaluate('window.analysisPayload')
    assert payload == {'pending_id':42, 'image_a_b64':jpeg('red'), 'image_b_b64':jpeg('blue')}
    page.evaluate("""() => {
      const original = window.CGI_API.post;
      window.CGI_API.post = async (path, body) => path.endsWith('/capture-dual') ?
        {ok:true,json:async()=>({analysis_skipped:true,message:'Analysis skipped — trained YOLOv8 model unavailable.',
          txn_id:null,pending_id:42,txn_number:'CGI-TEST',sample_weight_g:350,grade:null,
          created_at:'2026-10-23T00:00:00',image_path:'static/uploads/a.jpg',image_path_b:'static/uploads/b.jpg',defect_results:[]})} : original(path,body);
    }""")
    click('btn-start-analysis');page.wait_for_timeout(100)
    assert 'd-none' not in page.locator('#stage-5').get_attribute('class')
    assert 'Analysis skipped' in page.locator('#res-grade-badge').inner_text()
    assert page.locator('#res-total-price').inner_text() == 'Unavailable'
    click('btn-to-receipt')
    assert 'SKIPPED — MODEL UNAVAILABLE' in page.locator('#receipt-preview-box').inner_text()
    assert 'Unavailable — test only' in page.locator('#receipt-preview-box').inner_text()
    click('btn-back-to-capture');page.wait_for_timeout(650)
    assert page.evaluate('window.previewCount') > preview_count
    click('btn-retake-a');assert page.locator('#btn-to-analyze').is_disabled()
    assert page.locator('#btn-capture-b').is_disabled()
    # Leaving during countdown must discard the attempt and stop the preview.
    calls=page.evaluate('window.captures.length')
    click('btn-capture-a');page.wait_for_timeout(100);click('btn-back-to-weight')
    page.wait_for_timeout(3700)
    assert page.evaluate('window.captures.length') == calls
    assert 'd-none' in page.locator('#btn-accept-a').get_attribute('class')
    preview_count=page.evaluate('window.previewCount')
    page.wait_for_timeout(650)
    assert page.evaluate('window.previewCount') == preview_count
    # Account IDs and profile IDs differ. Resolve existing, missing and
    # concurrently-created profiles; a permissions error must not start a transaction.
    for mode in ('missing', 'conflict', 'denied'):
        page.locator('#txn-modal').evaluate("el=>el.dispatchEvent(new Event('hidden.bs.modal'))")
        page.evaluate('(mode)=>window.profileMode=mode', mode)
        click('btn-start-txn');page.wait_for_timeout(100)
        page.locator('.prep-check').evaluate_all('(els)=>els.forEach(el=>{el.checked=true;el.dispatchEvent(new Event("change"))})')
        before_init=page.evaluate('window.initPayloads.length')
        before_create=page.evaluate('window.profileCreates')
        click('btn-to-weight');page.wait_for_timeout(150)
        if mode == 'denied':
            assert page.evaluate('window.initPayloads.length') == before_init
            assert page.evaluate('window.profileCreates') == before_create
            assert 'Access denied' in page.locator('#stage1-error').text_content()
            assert 'd-none' not in page.locator('#stage-1').get_attribute('class')
        else:
            assert page.evaluate('window.initPayloads.length') == before_init+1
            assert page.evaluate('window.initPayloads.at(-1)') == {'farmer_id':7}
            assert page.evaluate('window.profileCreates') == before_create+1
    preview_count=page.evaluate('window.previewCount')
    # UI-only development mode must render preview/captures without camera API calls.
    page.locator('#txn-modal').evaluate("el=>el.dispatchEvent(new Event('hidden.bs.modal'))")
    click('btn-devmode-toggle');click('btn-start-txn')
    page.locator('.prep-check').evaluate_all('(els)=>els.forEach(el=>{el.checked=true;el.dispatchEvent(new Event("change"))})')
    click('btn-to-weight');page.wait_for_timeout(1200);click('btn-to-capture');page.wait_for_timeout(100)
    assert 'Simulated' in page.locator('#camera-live-status').inner_text()
    calls=page.evaluate('window.captures.length')
    click('btn-capture-a');page.wait_for_timeout(3700);click('btn-accept-a')
    assert page.evaluate('window.captures.length') == calls
    assert page.evaluate('window.previewCount') == preview_count
    page.locator('#txn-modal').evaluate("el=>el.dispatchEvent(new Event('hidden.bs.modal'))")
    assert not errors,errors
    print('PASS: Step 2 calibration sequence/cancellation, signed 2-decimal weight, tray/tare, instability gates; farmer account/profile mapping, profile creation/conflict/error handling; Chromium 800x480: live preview, disconnect/recovery, failed capture/retry, A/B confirmation and exact YOLO payload, retake, navigation cancellation, development mode; no JS errors')
    browser.close()
