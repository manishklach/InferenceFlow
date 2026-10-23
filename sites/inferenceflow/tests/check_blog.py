from pathlib import Path
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import re,json,unicodedata
root=Path(__file__).resolve().parents[1]/'dist'
article=root/'blog/what-if-ai-inference-didnt-have-to-be-instant/index.html'
s=BeautifulSoup(article.read_text(encoding='utf-8'),'html.parser')
source=(root.parent/'content/first-engineering-post.md').read_text(encoding='utf-8')
heads=[x[3:] for x in source.splitlines() if x.startswith('## ')]
assert len(s.select('.prose h2'))==len(heads)==8
# Every source paragraph is present, allowing Markdown emphasis and links.
import markdown
expected=BeautifulSoup(markdown.markdown('\n'.join(source.splitlines()[4:])),'html.parser')
for el in expected.find_all(['p','li','h2','h3']):
 assert el.get_text(' ',strip=True) in s.select_one('.prose').get_text(' ',strip=True),el.get_text()
for file in [root/'index.html',root/'blog/index.html',article]:
 soup=BeautifulSoup(file.read_text(encoding='utf-8'),'html.parser')
 assert len(soup.find_all('h1'))==1
 for el in soup.select('[href],[src]'):
  href=el.get('href',el.get('src',''))
  if href.startswith(('https:','http:','mailto:','#')):continue
  target=(root/href.lstrip('/')) if href.startswith('/') else file.parent/href
  target=Path(str(target).split('#')[0])
  assert target.exists(),(file,href)
assert json.loads(s.select_one('script[type="application/ld+json"]').string)['datePublished']=='2026-10-23'
(root.parent/'.qa').mkdir(exist_ok=True)
with sync_playwright() as p:
 browser=p.chromium.launch()
 page=browser.new_page(viewport={'width':1440,'height':1000})
 errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
 for path in ['/blog/','/blog/what-if-ai-inference-didnt-have-to-be-instant/']:
  assert page.goto('http://127.0.0.1:8095'+path).status==200
  page.screenshot(path=str(Path(__file__).parent.parent/'.qa'/('article-desktop.png' if 'instant' in path else 'blog-desktop.png')),full_page=True)
  page.locator('img').evaluate_all('(imgs)=>imgs.forEach(i=>i.loading="eager")')
  page.wait_for_timeout(500)
  assert page.locator('img').evaluate_all('(imgs)=>imgs.every(i=>i.complete && i.naturalWidth>0)')
 page.set_viewport_size({'width':390,'height':844})
 page.reload();page.screenshot(path=str(Path(__file__).parent.parent/'.qa/article-mobile.png'),full_page=True)
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 page.locator('.menu-toggle').click();assert page.locator('#navigation').is_visible()
 page.locator('#navigation a',has_text='Blog').click();assert page.url.endswith('/blog/')
 page.goto('http://127.0.0.1:8095/');page.locator('#run-replay').click()
 page.wait_for_timeout(10000)
 assert page.locator('#run-replay').is_enabled()
 page.locator('[data-preset="batch"]').click();page.locator('#run-replay').click();page.wait_for_timeout(10000)
 assert page.locator('#run-replay').is_enabled()
 page.locator('#capture-next').click();assert page.locator('#capture-index').inner_text()=='02 / 07'
 page.locator('#capture-expand').click();assert page.locator('#image-dialog').is_visible()
 page.locator('#close-dialog').click();assert not page.locator('#image-dialog').is_visible()
 page.locator('#curl-tab').click();assert 'curl http' in page.locator('#code-content').inner_text()
 page.locator('#python-tab').click();assert 'InferenceFlowClient' in page.locator('#code-content').inner_text()
 page.locator('#copy-code').click();assert 'Copied' in page.locator('#copy-code').inner_text() or 'Select code' in page.locator('#copy-code').inner_text()
 print('Browser regression: desktop/mobile blog, images, navigation, single/batch replay; no JS errors:',errors)
 assert not errors
 browser.close()
print('PASS: full article fidelity, 8 sections, heading hierarchy, local links, metadata, browser regressions')

