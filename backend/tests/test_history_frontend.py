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
    inspections = {'1':dict(txn_number='CGI-20261025-NORMAL',sample_weight_g=350.12,total_beans_detected=250,
        grade='class_i',over_threshold_flag=False,defect_results=[dict(defect_type='black_bean',bean_count=5,defect_percentage=2)])}
    tests=[]
    for n,value in enumerate([-500,0,1000000,None],2):
        meta={'completed_at':f'2026-10-26T0{n}:00:00+00:00','sensor_reading':None if value is None else dict(
            value=value,unit='ADC counts',raw_counts=value,calibrated=False,measured_at='2026-10-25T12:00:00Z')}
        tests.append(dict(id=n,txn_number=f'CGI-20261026-TEST{n}',created_at='2026-10-25T03:30:00',
                          weight_g=None,weight_metadata=json.dumps(meta)))
    tests.append(dict(id=6,txn_number='DEV-20261026-ABC123',created_at='2026-10-26T06:00:00',weight_g=None,
        weight_metadata=json.dumps({'simulated':True,'simulation_result':{'sample_weight_g':-500,'grade':'class_ii',
        'total_beans_detected':20,'currency':'PHP','price_per_kg':190,'total_price':-95,'defect_results':[]}})))
    (tmp_path/'data.json').write_text(json.dumps(dict(transactions=transactions,inspections=inspections,tests=tests)))
    (tmp_path/'stub.php').write_text('''<?php
function api_require_auth() {}
function api_current_user() { return ['role'=>'admin']; }
function api_response_list($r) { return $r['data']; }
function api_request($method,$path) {
 if ($method !== 'GET') throw new Exception('History attempted mutation');
 $d=json_decode(file_get_contents(__DIR__.'/data.json'),true);
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


def test_history_browser_filters_details_print_csv(history_page):
    pw=pytest.importorskip('playwright.sync_api')
    tmp_path,source=history_page
    source=re.sub(r'<script src=.*?</script>','',source)
    (tmp_path/'history.html').write_text(source)
    with pw.sync_playwright() as playwright:
        browser=playwright.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
        try:
            page=browser.new_page()
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.route('https://**/*',lambda route:route.abort())
            page.goto((tmp_path/'history.html').as_uri())
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
                assert(id('details-weight').textContent==='Not recorded','no invented grams');
                assert(id('details-sensor-reading').textContent==='1000000 ADC counts (uncalibrated)','raw unit');
                assert(id('details-beans').textContent==='Not recorded','missing beans');
                assert(id('details-price').textContent==='Not recorded','missing pricing');
                assert(id('details-grade').textContent==='Not recorded','missing grade');
                let prints=0;window.print=()=>prints++;window.requestAnimationFrame=fn=>fn();
                id('details-print').click();
                assert(prints===1&&id('receipt-print-area').textContent.includes('1000000 ADC counts'),'receipt');
                window.dispatchEvent(new Event('afterprint'));
                document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}));
                assert(id('details-overlay').hidden,'close details');
                let blob;URL.createObjectURL=b=>{blob=b;return 'blob:test'};URL.revokeObjectURL=()=>{};
                HTMLAnchorElement.prototype.click=function(){};
                id('export-btn').click();
                const csv=await blob.text();
                assert(csv.split('\\n').length===2&&csv.includes('1000000')&&csv.includes('ADC counts'),'filtered CSV');
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
                return 'filters, nulls, raw readings, details, printing and CSV passed';
            }''')
            assert result.endswith('passed')
            assert not errors,errors
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
