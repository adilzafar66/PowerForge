from playwright.sync_api import sync_playwright
from pathlib import Path
from PIL import Image
p=Path(__file__).resolve().parents[1]
html=(p/'prototypes/powerforge-documents-prototype.html').read_text()
errors=[]
with sync_playwright() as pw:
    b=pw.chromium.launch(headless=True, executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    pg=b.new_page(viewport={'width':1580,'height':970},device_scale_factor=1)
    pg.on('pageerror',lambda err: errors.append(str(err)))
    pg.set_content(html,wait_until='domcontentloaded')
    assert pg.get_by_role('heading',name='Documents',exact=True).count()==1
    assert pg.locator('#doc-rows tr').count()==4
    assert pg.locator('#inspector').is_hidden()
    pg.screenshot(path=str(p/'previews/documents-register-preview.png'),full_page=True)

    pg.locator('[data-row="d2"]').click()
    assert pg.locator('#inspector').is_visible()
    assert pg.locator('#accept-ai').is_visible()
    pg.screenshot(path=str(p/'previews/documents-detail-preview.png'),full_page=True)
    # Changing a draft and then selecting another record must demand explicit discard.
    pg.locator('#metadata-form textarea[name="notes"]').fill('Draft notes not saved')
    pg.locator('[data-row="d1"]').click()
    assert pg.get_by_role('dialog',name='PowerForge dialog').is_visible()
    assert 'unsaved' in pg.locator('#modal-overlay').inner_text().lower()
    pg.locator('[data-modal="close"]').first.click()
    assert pg.locator('#metadata-form textarea[name="notes"]').input_value()=='Draft notes not saved'
    pg.locator('#close-inspector').click()
    pg.locator('[data-modal="discard"]').click()
    assert pg.locator('#inspector').is_hidden()

    pg.locator('[data-view="review"]').click()
    assert pg.locator('#doc-rows tr').count()==1
    pg.locator('#search').fill('no-match-filename')
    assert pg.locator('#doc-rows tr').count()==0
    assert pg.locator('#empty-title').inner_text()=='No matching documents'
    pg.locator('#search').fill('')
    pg.locator('#filter-toggle').click()
    assert pg.locator('#filter-panel').is_visible()
    # Real mouse interaction with the portalled custom select; not a native-select shortcut.
    trigger=pg.locator('#filter-panel .pf-select-trigger').nth(1)
    trigger.click()
    options=pg.get_by_role('option',name='Inherited')
    options.hover()
    pg.wait_for_timeout(220)
    assert options.evaluate('el => getComputedStyle(el).backgroundColor')=='rgb(245, 248, 250)'
    options.click()
    assert pg.locator('#filter-panel').is_visible()
    assert pg.locator('#doc-rows tr').count()==1
    trigger.click()
    selected=pg.get_by_role('option',name='Inherited')
    assert selected.get_attribute('aria-selected')=='true'
    assert selected.evaluate('el => getComputedStyle(el).backgroundColor')=='rgb(230, 238, 244)'
    selected.hover()
    pg.wait_for_timeout(220)
    assert selected.evaluate('el => getComputedStyle(el).backgroundColor')=='rgb(214, 227, 237)'
    trigger.press('Escape')
    pg.locator('#clear-filters').click()
    pg.locator('#filter-toggle').click()
    pg.locator('[data-view="all"]').click()

    pg.locator('[data-row="d3"]').click()
    pg.locator('#demo-progress').click()
    assert pg.locator('[data-row="d3"]').inner_text().find('15/18 pages')>=0
    pg.locator('#close-inspector').click()
    pg.locator('#add-docs').click()
    pg.locator('[data-do="reuse"]').click()
    assert pg.locator('#modal-overlay').is_visible()
    pg.locator('[data-modal="save-reuse"]').click()
    assert pg.locator('#doc-rows tr').count()==5
    pg.locator('#rev-toggle').click()
    pg.locator('[data-revision="IFC 122"]').click()
    assert pg.locator('#add-docs').is_disabled()
    pg.locator('[data-row="d1"]').click()
    assert pg.locator('#metadata-form input[name="number"]').is_disabled()

    mobile=b.new_page(viewport={'width':390,'height':844},device_scale_factor=1)
    mobile.on('pageerror',lambda err: errors.append('mobile:'+str(err)))
    mobile.set_content(html,wait_until='domcontentloaded')
    # The wide engineering register scrolls within its table container, not across the page.
    assert mobile.locator('.table-wrap').evaluate('el=>el.scrollWidth>el.clientWidth')
    assert mobile.locator('.main').evaluate('el=>getComputedStyle(el).overflowX')=='hidden'
    mobile.screenshot(path=str(p/'previews/documents-register-mobile-preview-raw.png'),full_page=True)
    screenshot=Image.open(p/'previews/documents-register-mobile-preview-raw.png')
    screenshot.crop((0,0,390,screenshot.height)).save(p/'previews/documents-register-mobile-preview.png')
    (p/'previews/documents-register-mobile-preview-raw.png').unlink()
    assert not errors, errors
    print('PASS v1.15 Documents main page: register, details, draft guard, search, quick views, themed portalled selects/hover, reuse, simulated job state, read-only, mobile overflow. No JS errors.')
    b.close()
