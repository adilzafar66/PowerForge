from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
UX9=ROOT/'prototypes/powerforge-design-system-prototype.html'
PREVIEW=ROOT/'previews';PREVIEW.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1580,'height':980},device_scale_factor=1); page.set_default_timeout(4500)
    errors=[];page.on('pageerror', lambda e: errors.append(str(e)))
    page.set_content(UX9.read_text(encoding='utf-8'),wait_until='load')
    page.get_by_role('tab',name='Selects & Checkboxes').click()
    combo=page.locator('#pf-controls-choice').locator('xpath=..').get_by_role('combobox')
    assert combo.count()==1, f'{combo.count()} comboboxes'
    assert combo.inner_text()=='All equipment types'
    assert combo.get_attribute('aria-expanded')=='false'
    page.screenshot(path=str(PREVIEW/'ux9-controls-preview.png'),full_page=True)
    combo.click()
    assert combo.get_attribute('aria-expanded')=='true'
    assert page.get_by_role('option',name='Synchronous Generator').is_visible()
    page.wait_for_timeout(230)
    page.screenshot(path=str(PREVIEW/'ux9-controls-dropdown-open-preview.png'),full_page=False)
    page.get_by_role('option',name='2-Winding Transformer').click()
    assert page.locator('#pf-controls-choice').input_value()=='transformer'
    assert page.locator('#pf-controls-current').inner_text()=='Selected: 2-Winding Transformer'
    assert combo.get_attribute('aria-expanded')=='false'
    combo.focus();page.keyboard.press('ArrowDown')
    assert combo.get_attribute('aria-expanded')=='true'
    page.keyboard.press('End');page.keyboard.press('Enter')
    assert page.locator('#pf-controls-choice').input_value()=='motor'
    combo.focus();page.keyboard.press(' ');page.keyboard.press('Escape')
    assert combo.get_attribute('aria-expanded')=='false'
    assert combo.evaluate('(el)=>document.activeElement===el')
    assert page.locator('#pf-controls-disabled').is_disabled()
    disabled=page.locator('#pf-controls-disabled').locator('xpath=..').get_by_role('combobox')
    assert disabled.is_disabled()
    assert page.locator('#pf-demo-checked').is_checked()
    assert not page.locator('#pf-demo-unchecked').is_checked()
    assert page.locator('#pf-demo-mixed').evaluate('(el)=>el.indeterminate')
    assert page.locator('#pf-demo-disabled').is_disabled()
    page.locator('#pf-demo-unchecked').check()
    assert page.locator('#pf-demo-unchecked').is_checked()
    page.locator('#pf-demo-checked').focus();page.keyboard.press('Space')
    assert not page.locator('#pf-demo-checked').is_checked()
    assert not errors,errors
    # Main UX-9 async demo must still use its checkboxes and dynamic state.
    page.get_by_role('tab',name='API & Jobs').click()
    assert page.locator('#auto-poll').is_checked()
    page.get_by_role('button',name='Start simulated job').click()
    page.wait_for_timeout(600)
    assert int(page.locator('.progress').get_attribute('aria-valuenow'))>0
    # Topology revision selector is also replaced and retains its original change handlers.
    top=browser.new_page(viewport={'width':1440,'height':900})
    top_errors=[];top.on('pageerror',lambda e:top_errors.append(str(e)))
    top.set_content((ROOT/'prototypes/powerforge-topology-prototype.html').read_text(encoding='utf-8'),wait_until='load')
    mode=top.locator('#mode')
    assert mode.count()==1
    tcombo=mode.locator('xpath=..').get_by_role('combobox')
    tcombo.click();top.get_by_role('option',name='Superseded (read-only)').click()
    assert mode.input_value()=='readonly'
    assert not top_errors,top_errors
    # At narrow viewport, menu should stay in bounds.
    narrow=browser.new_page(viewport={'width':390,'height':844})
    narrow.set_content(UX9.read_text(encoding='utf-8'),wait_until='load')
    narrow.get_by_role('tab',name='Selects & Checkboxes').click()
    nc=narrow.locator('#pf-controls-choice').locator('xpath=..').get_by_role('combobox')
    nc.click()
    box=narrow.locator('.pf-select-menu:visible').bounding_box()
    assert box['x']>=0 and box['x']+box['width']<=393,box
    assert not errors,errors
    browser.close()
print('PASS UX-9.1: themed dropdown menus across prototypes, pointer/keyboard, checkbox states, old async/job state, viewport')
