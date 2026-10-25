"""History rendering and browser interactions with read-only API fixtures."""
import html
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def history_page(tmp_path):
    if not shutil.which('php'):
        pytest.skip('PHP required')
    transactions = [dict(id=1, inspection_id=1, status='completed', created_at='2026-10-25T03:30:00',
                         weight_kg=.3501, price_per_kg=190, total_price=66.519, currency='PHP')]
    inspections = {'1':dict(txn_number='CGI-20261025-NORMAL',farmer_id=42,sample_weight_g=350.12,total_beans_detected=250,
        grade='class_i',over_threshold_flag=False,defect_results=[dict(defect_type='black_bean',bean_count=5,defect_percentage=2)])}
    tests=[]
    for n,value in enumerate([-500,0,1000000,None],2):
        meta={'completed_at':f'2026-10-26T0{n}:00:00+00:00','sensor_reading':None if value is None else dict(
            value=value,unit='ADC counts',raw_counts=value,calibrated=False,measured_at='2026-10-25T12:00:00Z')}
        tests.append(dict(id=n,farmer_id=84 if n in (2,4) else (99 if n==3 else None),txn_number=f'CGI-20261026-TEST{n}',created_at='2026-10-25T03:30:00',
                          weight_g=None,weight_metadata=json.dumps(meta)))
    tests.append(dict(id=6,farmer_id=84,txn_number='DEV-20261026-ABC123',created_at='2026-10-26T06:00:00',weight_g=None,
        weight_metadata=json.dumps({'simulated':True,'simulation_result':{'sample_weight_g':-500,'grade':'class_ii',
        'total_beans_detected':20,'currency':'PHP','price_per_kg':190,'total_price':-95,'defect_results':[]}})))
    (tmp_path/'data.json').write_text(json.dumps(dict(transactions=transactions,inspections=inspections,tests=tests)))
    (tmp_path/'stub.php').write_text('''<?php
function api_require_auth() {}
function api_current_user() { return ['id'=>1,'role'=>'admin']; }
function api_response_list($r) { return $r['data']; }
function api_request($method,$path) {
 if ($method !== 'GET') throw new Exception('History attempted mutation');
 $d=json_decode(file_get_contents(__DIR__.'/data.json'),true);
 if ($path === '/api/users') return ['status'=>200,'data'=>[
  ['id'=>7,'name'=>'Normal Farmer & Family <North>'],
  ['id'=>42,'name'=>'Test Farmer With A Long Full Name'],
  ['id'=>8,'name'=>'User without farmer profile']
 ]];
 if ($path === '/api/users/7/farmer') return ['status'=>200,'data'=>['id'=>42,'user_id'=>7]];
 if ($path === '/api/users/42/farmer') return ['status'=>200,'data'=>['id'=>84,'user_id'=>42]];
 if ($path === '/api/users/8/farmer') return ['status'=>404,'data'=>null];
 if (str_starts_with($path,'/api/transactions?')) return ['status'=>200,'data'=>$d['transactions']];
 if (str_starts_with($path,'/api/transaction/completed-tests?')) return ['status'=>200,'data'=>$d['tests']];
 return ['status'=>200,'data'=>$d['inspections'][basename($path)]];
}
''')
    source=(ROOT/'frontend/history.php').read_text().replace("require_once __DIR__ . '/api.php';", "require_once __DIR__ . '/stub.php';")
    source=source.replace("include __DIR__ . '/components/navbar.php';",'')
    (tmp_path/'history.php').write_text(source)
    rendered=subprocess.run(['php',str(tmp_path/'history.php')],capture_output=True,text=True,check=True)
    assert not rendered.stderr,rendered.stderr
    return tmp_path, rendered.stdout


def test_history_preserves_nulls_extremes_units_and_saved_prices(history_page):
    _,page=history_page
    values=[json.loads(html.unescape(s)) for s in re.findall(r"data-transaction='([^']+)'",page)]
    assert len(values)==6 and len({v['id'] for v in values})==6
    assert values[0]['recordLabel']=='Simulated development run'
    assert values[-1]['suggestedPrice']==66.519 and values[-1]['pricingWeightKg']==.3501
    for value in values[1:-1]:
        assert value['weight'] is None and value['beans'] is None and value['defects'] is None
        assert value['grade']=='Not recorded' and value['suggestedPrice'] is None
    assert sorted(v['sensorReading']['value'] for v in values if v['sensorReading'])==[-500,0,1000000]
    assert '1,000,000 g' not in page
    by_id={v['id']:v for v in values}
    assert by_id['CGI-20261025-NORMAL']['farmerName']=='Normal Farmer & Family <North>'
    assert by_id['CGI-20261026-TEST4']['farmerName']=='Test Farmer With A Long Full Name'
    assert by_id['DEV-20261026-ABC123']['farmerName']=='Test Farmer With A Long Full Name'
    assert by_id['CGI-20261026-TEST3']['farmerName']=='Not Available'
    assert by_id['CGI-20261026-TEST5']['farmerName']=='Not Available'
    assert 'Normal Farmer &amp; Family &lt;North&gt;' in page
    headings=re.findall(r'<th[^>]*>(.*?)</th>',page)
    assert headings==['Transaction ID','Farmer Name','Date & Time','Weight','Defects','Grade','Suggested Price','Actions']


def test_history_browser_filters_details_print_csv(history_page):
    pw=pytest.importorskip('playwright.sync_api')
    tmp_path,source=history_page
    source=re.sub(r'<script src=.*?</script>','',source)
    (tmp_path/'history.html').write_text(source)
    with pw.sync_playwright() as playwright:
        browser=playwright.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        try:
            page=browser.new_page(viewport={'width':800,'height':480})
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.route('https://**/*',lambda route:route.abort())
            page.goto((tmp_path/'history.html').as_uri())
            page.add_style_tag(content=(ROOT/'frontend/assets/css/history.css').read_text())
            page.add_script_tag(content=(ROOT/'frontend/assets/js/history.js').read_text())
            page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
            result=page.evaluate('''async () => {
                const id=x=>document.getElementById(x);
                const rows=[...document.querySelectorAll('.transaction-row')];
                const visible=()=>rows.filter(r=>!r.hidden);
                const assert=(condition,message)=>{if(!condition)throw Error(message)};
                const set=(key,value,type='change')=>{id(key).value=value;id(key).dispatchEvent(new Event(type))};
                assert(visible().length===6,'initial rows');
                set('history-search','test4','input');
                assert(visible().length===1,'search');
                visible()[0].querySelector('.view-btn').click();
                assert(id('details-farmer-name').textContent==='Test Farmer With A Long Full Name','farmer in details');
                assert(id('details-weight').textContent==='Not recorded','no invented grams');
                assert(id('details-sensor-reading').textContent==='1000000 ADC counts (uncalibrated)','raw unit');
                assert(id('details-beans').textContent==='Not recorded','missing beans');
                assert(id('details-price').textContent==='Not recorded','missing pricing');
                assert(id('details-grade').textContent==='Not recorded','missing grade');
                let prints=0;window.print=()=>prints++;window.requestAnimationFrame=fn=>fn();
                id('details-print').click();
                assert(prints===1&&id('receipt-print-area').textContent.includes('1000000 ADC counts'),'receipt');
                const receiptRows=[...id('receipt-print-area').querySelectorAll('.receipt-row')];
                assert(receiptRows[0].textContent.includes('Transaction ID')&&receiptRows[1].textContent.includes('Farmer Name')&&receiptRows[1].textContent.includes('Test Farmer With A Long Full Name')&&receiptRows[2].textContent.includes('Date & Time'),'receipt name order');
                window.dispatchEvent(new Event('afterprint'));
                document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}));
                assert(id('details-overlay').hidden,'close details');
                let blob;URL.createObjectURL=b=>{blob=b;return 'blob:test'};URL.revokeObjectURL=()=>{};
                HTMLAnchorElement.prototype.click=function(){};
                id('export-btn').click();
                const csv=await blob.text();
                assert(csv.split('\\n').length===2&&csv.includes('1000000')&&csv.includes('ADC counts'),'filtered CSV');
                assert(csv.split('\\n')[0].startsWith('"Transaction ID","Farmer Name"')&&csv.includes('Test Farmer With A Long Full Name'),'farmer in CSV');
                set('history-search','test2','input');
                id('export-btn').click();
                const negativeCsv=await blob.text();
                assert(negativeCsv.includes('"-500"'), 'CSV preserves negative numeric values');
                set('history-search','test4','input');
                set('grade-filter','Class I');
                assert(!visible().length&&!id('empty-state').hidden&&id('export-btn').disabled,'empty filters');
                id('reset-filters').click();assert(visible().length===6,'reset');
                set('grade-filter','Not recorded');assert(visible().length===4,'missing grade filter');
                id('reset-filters').click();
                set('date-filter','7');
                const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Manila',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
                const p=t=>parts.find(x=>x.type===t).value;
                const now=Date.parse(`${p('year')}-${p('month')}-${p('day')}T00:00:00Z`);
                assert(visible().length===rows.filter(r=>{const days=(now-Date.parse(r.dataset.date+'T00:00:00Z'))/86400000;return days>=0&&days<7}).length,'Manila dates');
                id('reset-filters').click();
                rows[0].querySelector('.print-btn').click();
                assert(id('receipt-print-area').textContent.includes('Simulated development run'),'simulation label on receipt');
                set('history-search','test5','input');
                visible()[0].querySelector('.print-btn').click();
                assert(id('receipt-print-area').querySelectorAll('.receipt-row')[1].textContent.includes('Not Available'),'missing farmer receipt');
                visible()[0].querySelector('.view-btn').click();
                assert(id('details-farmer-name').textContent==='Not Available','missing farmer details');
                return 'filters, nulls, raw readings, details, printing and CSV passed';
            }''')
            assert result.endswith('passed')
            assert not errors,errors
            for width,height in [(800,480),(480,800)]:
                page.set_viewport_size({'width':width,'height':height})
                page.evaluate("document.getElementById('details-close-footer').click();document.getElementById('reset-filters').click()")
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                assert page.locator('.table-wrap').evaluate('(el)=>getComputedStyle(el).overflowX')=='auto'
                assert page.locator('.farmer-name-cell').first.evaluate('(el)=>getComputedStyle(el).overflowWrap')=='anywhere'
        finally:
            browser.close()


def test_finish_handler_uses_archive_only_for_test_runs():
    """Execute the actual Finish handler with API/UI boundaries stubbed."""
    pw=pytest.importorskip('playwright.sync_api')
    source=(ROOT/'frontend/assets/js/dashboard.js').read_text()
    start=source.index("        document.getElementById('btn-complete-txn').addEventListener")
    end=source.index('\n    }\n\n    function initializeDashboard',start)
    handler=source[start:end].replace('location.reload();','window.reloaded = true;')
    with pw.sync_playwright() as playwright:
        browser=playwright.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        try:
            page=browser.new_page()
            for scenario,endpoint in [('sensor','/api/transaction/7/complete-test'),
                ('missing','/api/transaction/7/complete-test'),
                ('simulation','/api/transaction/complete-simulation'),
                ('normal','/api/transactions/9'),('failed','/api/transaction/7/complete-test')]:
                page.set_content('<button id="btn-complete-txn">Finish</button><select id="farmer-select"><option value="1">Farmer</option></select>')
                page.evaluate('(value)=>{window.scenario=value;window.calls=[];window.reloaded=false;window.hidden=false;window.failure=null}',scenario)
                setup='''(() => {
                    const devMode=window.scenario==='simulation';
                    const currentAnalysis={sensor_test_mode:['sensor','failed'].includes(window.scenario),
                        analysis_skipped:window.scenario==='missing'};
                    const pendingId=7,txnId=9,txnNumber='DEV-20261026-ABC123';
                    const txnModal={hide(){window.hidden=true}};
                    function _hideError(){} function _showError(id,message){window.failure=message}
                    async function _resolveFarmerProfile(){return 1}
                    async function request(path,body){
                        window.calls.push({path,body});
                        return {ok:window.scenario!=='failed',json:async()=>({detail:'Database unavailable'})};
                    }
                    const API={post:request,put:request};
                '''
                page.add_script_tag(content=setup+handler+'})();')
                page.locator('#btn-complete-txn').click()
                page.wait_for_function('window.reloaded || window.failure')
                calls=page.evaluate('window.calls')
                assert len(calls)==1 and calls[0]['path']==endpoint
                if scenario=='failed':
                    assert not page.evaluate('window.hidden')
                    assert not page.locator('#btn-complete-txn').is_disabled()
                    assert 'Database unavailable' in page.evaluate('window.failure')
                else:
                    assert page.evaluate('window.hidden && window.reloaded')
                if scenario=='normal':
                    assert calls[0]['body']=={'status':'completed'}
                if scenario=='simulation':
                    assert calls[0]['body']['txn_number']=='DEV-20261026-ABC123'
        finally:
            browser.close()


@pytest.mark.parametrize('farmer_name', ['Receipt Farmer With A Long Full Name', None])
def test_new_receipt_preview_farmer_order_and_fallback(farmer_name):
    pw=pytest.importorskip('playwright.sync_api')
    source=(ROOT/'frontend/assets/js/dashboard.js').read_text()
    start=source.index('        function _buildReceiptPreview()')
    end=source.index("        document.getElementById('btn-print-receipt').addEventListener",start)
    function=source[start:end]
    with pw.sync_playwright() as playwright:
        browser=playwright.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        try:
            page=browser.new_page(timezone_id='Asia/Manila')
            page.set_content('<pre id="receipt-preview-box"></pre>')
            page.evaluate('(value)=>window.receiptFarmer=value',farmer_name)
            page.add_script_tag(content='''(() => {
                const currentAnalysis={txn_number:'CGI-20261026-ABC123',created_at:'2026-10-26T10:30:00',
                    grade:'class_i',sample_weight_g:350,price_per_kg:190,total_price:66.5};
                const txnNumber=currentAnalysis.txn_number, farmerName=window.receiptFarmer, devMode=false;
                const _gradeLabel=()=> 'Class I', _phpFormat=value=>String(value), _pad32=(label,value)=>(label+value).padEnd(36);
            '''+function+'\n_buildReceiptPreview();})();')
            lines=page.locator('#receipt-preview-box').text_content().splitlines()
            index=next(i for i,line in enumerate(lines) if line.startswith('Transaction ID:'))
            assert lines[index+1].strip()=='Farmer Name: '+(farmer_name or 'Not Available')
            assert lines[index+2].startswith('Date & Time: October 26, 2026')
            assert '10:30 AM' in lines[index+2]
        finally:
            browser.close()


@pytest.mark.parametrize('farmer_name', ['Receipt Farmer With A Long Full Name', None, '   '])
def test_thermal_receipt_presentation_preserves_printer_calls(monkeypatch, farmer_name):
    import sys
    import types
    from datetime import datetime
    from unittest.mock import Mock
    from services import thermal_print
    from models.inspection import Inspection
    from models.farmer import Farmer
    from models.user import User
    # Only the receipt renderer runs. No database connection or physical printer is used.
    txn=types.SimpleNamespace(inspection_id=3,created_at=datetime(2026,10,26,10,30),
                              weight_kg=.35,currency='PHP',price_per_kg=190,total_price=66.5)
    inspection=types.SimpleNamespace(id=3,txn_number='CGI-20261026-ABC123',farmer_id=42,
        officer_id=9,grade=types.SimpleNamespace(value='class_i'),over_threshold_flag=False)
    farmer=types.SimpleNamespace(user_id=7) if farmer_name is not None else None
    user=types.SimpleNamespace(name=farmer_name) if farmer_name is not None else None
    rows={(Inspection,3):inspection,(Farmer,42):farmer,(User,7):user,(User,9):types.SimpleNamespace(name='Officer')}
    db=Mock()
    db.get.side_effect=lambda model,id:rows.get((model,id))
    printer=Mock()
    module=types.ModuleType('escpos.printer')
    module.Network=Mock(return_value=printer)
    module.Usb=Mock(return_value=printer)
    monkeypatch.setitem(sys.modules,'escpos',types.ModuleType('escpos'))
    monkeypatch.setitem(sys.modules,'escpos.printer',module)
    monkeypatch.setattr(thermal_print.settings,'THERMAL_PRINTER_TYPE','network')
    thermal_print.print_receipt(txn,db)
    lines=''.join(call.args[0] for call in printer.text.call_args_list).splitlines()
    index=lines.index('Transaction ID: CGI-20261026-ABC123')
    assert lines[index+1]=='Farmer Name: '+(farmer_name.strip() if farmer_name and farmer_name.strip() else 'Not Available')
    assert lines[index+2]=='Date & Time: October 26, 2026 - 10:30 AM'
    assert 'Weight  : 0.350 kg' in lines and 'TOTAL   : PHP 66.50' in lines
    printer.cut.assert_called_once()
    printer.close.assert_called_once()
    printer.ln.assert_called_once_with(3)
    module.Network.assert_called_once_with(thermal_print.settings.THERMAL_PRINTER_HOST,thermal_print.settings.THERMAL_PRINTER_PORT)
    assert not db.commit.called and not db.add.called
