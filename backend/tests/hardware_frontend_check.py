"""Isolated Chromium behavior check using the existing PHP template and JS.

Run: venv/bin/python backend/tests/hardware_frontend_check.py
Requires optional `pip install playwright==1.51.0` and /usr/bin/chromium.
PHP-generated values, Bootstrap modal and APIs are substituted; this checks DOM
behavior, not the deployed page layout or physical touchscreen.
"""
import re, json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[2]
html=re.sub(r'<\?.*?\?>','', (root/'frontend/dashboard.php').read_text(), flags=re.S)
html=re.sub(r'<script\b[^>]*>.*?</script>','',html,flags=re.S)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':800,'height':480})
    page.route('**/*',lambda route: route.fulfill(body=html,content_type='text/html') if route.request.url=='http://cgi.test/' else route.abort())
    page.goto('http://cgi.test/')
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.evaluate('''() => {
      for(let i=1;i<=6;i++){let el=document.createElement('span');el.id='step-badge-'+i;document.body.appendChild(el);}
      window.bootstrap={Modal: class {constructor(el){this.el=el} show(){this.el.style.display='block'} hide(){this.el.dispatchEvent(new Event('hidden.bs.modal'))}}};
      window.mockWeight={weight_g:350,stable:true,in_range:true};
      window.failWeight=false; window.captures=[]; window.saved=[];
      window.CGI_API={
       get:async path => ({ok:!window.failWeight,json:async()=>path.endsWith('/status')?{camera:'ready',scale:'ready',printer:'warning'}:window.mockWeight}),
       post:async (path,body) => {if(path.endsWith('/capture')) window.captures.push(body.view); return {ok:true,json:async()=>path.endsWith('/init')?{pending_id:42,txn_number:'CGI-TEST'}:path.endsWith('/capture')?{image_b64:'aGVsbG8='}:{tared:true}}},
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
    click('btn-capture-a');page.wait_for_timeout(3600);click('btn-accept-a')
    click('btn-capture-b');page.wait_for_timeout(3600)
    assert page.locator('#btn-to-analyze').is_disabled()
    click('btn-accept-b');assert not page.locator('#btn-to-analyze').is_disabled()
    click('btn-retake-a');assert page.locator('#btn-to-analyze').is_disabled()
    assert page.evaluate('window.captures')==['A','B']
    assert not errors,errors
    print('PASS: Chromium 800x480: prepare, weight validation/disconnect recovery, tare, weight save, A/B accept and retake gates; no JS errors')
    browser.close()
