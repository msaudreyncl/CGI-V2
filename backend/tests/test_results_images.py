"""Run with venv/bin/python backend/tests/test_results_images.py (Chromium)."""
import base64
import io
from PIL import Image
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / 'frontend/assets/js/dashboard.js').read_text()
static_url = re.search(r'        function _staticUrl\(relPath\) \{.*?\n        }', source, re.S)[0]
set_img = re.search(r'            function _setImg\(imgId, linkId, path, captured = null\) \{.*?\n            }', source, re.S)[0]
images = []
for color in ('red', 'blue'):
    buffer = io.BytesIO()
    Image.new('RGB', (16, 9), color).save(buffer, format='JPEG')
    images.append(base64.b64encode(buffer.getvalue()).decode())

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
    page = browser.new_page()
    page.route('**/*', lambda route: route.fulfill(status=404, body='Missing'))
    page.goto('http://cgi.test/')
    page.set_content('<a id="a-link"><img id="a"></a><a id="b-link"><img id="b"></a>')
    page.add_script_tag(content=static_url + '\n' + set_img)
    # Both saved URLs fail on the deployed Apache layout; retain their own captures.
    for v, image in zip(('a', 'b'), images):
        page.evaluate('([v, image]) => _setImg(v, v+"-link", "static/uploads/"+v+".jpg", image)', [v, image])
    page.wait_for_function('["a","b"].every(v => document.getElementById(v).naturalWidth > 0)')
    for v, image in zip(('a', 'b'), images):
        assert page.locator('#'+v).get_attribute('src') == 'data:image/jpeg;base64,' + image
    # A saved image that loads successfully stays in place, even with a fallback.
    page.route('**/static/uploads/saved.jpg', lambda route: route.fulfill(
        body=base64.b64decode(images[1]), content_type='image/jpeg'))
    page.evaluate('(image) => _setImg("b", "b-link", "static/uploads/saved.jpg", image)', images[0])
    page.wait_for_function('document.getElementById("b").naturalWidth > 0')
    assert page.locator('#b').get_attribute('src') == '/static/uploads/saved.jpg'
    # Failed optional annotations and failed fallbacks terminate without placeholders.
    page.evaluate('_setImg("a", "a-link", "static/uploads/missing.jpg", "invalid")')
    page.wait_for_function('document.getElementById("a").hidden')
    # Missing originals can use captures immediately; unavailable annotations stay hidden.
    page.evaluate('(image) => _setImg("a", "a-link", null, image)', images[0])
    page.wait_for_function('document.getElementById("a").naturalWidth > 0')
    page.evaluate('_setImg("b", "b-link", null)')
    assert page.locator('#b').is_hidden()
    # Absolute URLs and configured backend origins must not be rewritten incorrectly.
    assert page.evaluate('_staticUrl("https://images.test/a.jpg")') == 'https://images.test/a.jpg'
    page.evaluate('window.CGI_API_BASE = "https://backend.test/"')
    assert page.evaluate('_staticUrl("/static/uploads/a.jpg")') == 'https://backend.test/static/uploads/a.jpg'
    browser.close()
print('PASS: both captures load after stored-URL failures; missing images and URL bases handled')
