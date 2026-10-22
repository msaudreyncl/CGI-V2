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
      window.hardwareStatus={camera:'error',scale:'ready',printer:'warning',details:{camera:'Cannot reach Pi service'}};
      window.previewCount=0; window.failPreview=false; window.failCapture=false; window.analysisPayload=null;
      window.CGI_API={
       get:async path => ({ok:!window.failWeight,json:async()=>path.endsWith('/status')?window.hardwareStatus:window.mockWeight}),
       post:async (path,body) => {
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
    assert not page.locator('#btn-to-capture').is_disabled()
    page.evaluate('window.failWeight=true');page.wait_for_timeout(600)
    assert page.locator('#btn-to-capture').is_disabled()
    page.evaluate('window.failWeight=false;window.mockWeight.weight_g=339');page.wait_for_timeout(600)
    assert page.locator('#btn-to-capture').is_disabled()
    page.evaluate('window.mockWeight.weight_g=350');page.wait_for_timeout(600)
    click('btn-tare-scale');page.wait_for_timeout(600)
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
    print('PASS: Chromium 800x480: live preview, disconnect/recovery, failed capture/retry, A/B confirmation and exact YOLO payload, retake, navigation cancellation, development mode; no JS errors')
    browser.close()
