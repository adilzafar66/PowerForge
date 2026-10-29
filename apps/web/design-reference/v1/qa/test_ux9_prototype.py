from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
PROTO=ROOT/'prototypes/powerforge-design-system-prototype.html'
OUT=ROOT/'previews'
OUT.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1600,'height':1000},device_scale_factor=1, reduced_motion='no-preference')
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content(PROTO.read_text(encoding="utf-8"), wait_until="load")
    assert page.get_by_role('heading',name='Interface foundations').is_visible()
    assert page.get_by_role('tabpanel',name='Foundations').is_visible()
    page.screenshot(path=str(OUT/'ux9-foundations-preview.png'),full_page=True)
    page.get_by_role('tab',name='Components').click()
    assert page.get_by_role('tabpanel',name='Components').is_visible()
    page.get_by_role('button',name='Primary action').click()
    assert page.get_by_text('Changes saved').count()>0
    page.get_by_role('button',name='Remove',exact=True).click()
    assert page.get_by_role('alertdialog').is_visible()
    page.get_by_role('button',name='Cancel').click()
    assert page.get_by_role('alertdialog').count()==0
    page.screenshot(path=str(OUT/'ux9-components-preview.png'),full_page=True)
    page.get_by_role('tab',name='API & Jobs').click()
    page.get_by_role('button',name='Load data').click()
    assert page.get_by_role('status',name='Loading equipment').count()==1
    page.wait_for_timeout(1250)
    assert page.get_by_text('BCH PRES').count()>=1
    page.get_by_role('button',name='Background refresh').click()
    assert page.get_by_text('Refreshing in background',exact=False).count()>0
    assert page.get_by_text('BCH PRES').count()>=1
    page.wait_for_timeout(1000)
    page.get_by_role('button',name='Simulate failure').click()
    page.wait_for_timeout(1250)
    assert page.get_by_text('Could not load equipment.',exact=False).count()>0
    page.get_by_role('button',name='Retry',exact=True).click()
    page.wait_for_timeout(1250)
    assert page.get_by_text('BCH PRES').count()>=1
    page.get_by_role('button',name='Simulate engineering save').click()
    page.wait_for_timeout(2300)
    assert page.get_by_text('CB-201').count()>0
    page.get_by_role('button',name='Start simulated job').click()
    page.wait_for_timeout(490)
    assert page.locator('.progress').get_attribute('aria-valuenow') != '0'
    page.get_by_role('button',name='Simulate partial failure').click()
    assert page.get_by_text('Partially completed',exact=True).count()>0
    page.get_by_role('button',name='Retry failed work').click()
    page.wait_for_timeout(4800)
    assert page.locator('#job-phase').inner_text()=='Complete'
    page.screenshot(path=str(OUT/'ux9-async-preview.png'),full_page=True)
    page.get_by_role('tab',name='Feedback & Forms').click()
    page.locator('#edit-tag').fill('')
    page.locator('#edit-voltage').fill('-5')
    page.get_by_role('button',name='Save changes').click()
    assert page.get_by_text('Equipment tag is required.').is_visible()
    page.locator('#edit-tag').fill('TX-101A')
    page.locator('#edit-voltage').fill('13.8')
    page.get_by_role('button',name='Discard changes').click()
    assert page.get_by_role('alertdialog').is_visible()
    page.get_by_role('button',name='Cancel').click()
    assert page.locator('#edit-tag').input_value()=='TX-101A'
    page.get_by_role('button',name='Save changes').click()
    page.wait_for_timeout(1150)
    assert page.locator('#draft-state').inner_text()=='Clean'
    page.screenshot(path=str(OUT/'ux9-feedback-preview.png'),full_page=True)
    page.get_by_role('tab',name='Motion & Accessibility').click()
    page.get_by_role('button',name='Move sample panel').click()
    assert 'moved' in page.locator('#motion-box').get_attribute('class')
    page.locator('#reduce-motion').check()
    assert 'manual-reduce-motion' in page.locator('body').get_attribute('class')
    page.get_by_role('tab',name='Feedback & Forms').focus()
    page.keyboard.press('ArrowRight')
    assert page.get_by_role('tab',name='Motion & Accessibility').get_attribute('aria-selected')=='true'
    assert not errors,errors
    phone=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=1)
    phone.set_content(PROTO.read_text(encoding="utf-8"), wait_until="load")
    assert phone.get_by_role('heading',name='Interface foundations').is_visible()
    phone.screenshot(path=str(OUT/'ux9-mobile-preview.png'),full_page=True)
    browser.close()
print('PASS UX-9: foundations, components, data lifecycle, refresh, recovery, job, validation, dialogs, motion, tabs, mobile')
