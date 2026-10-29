from pathlib import Path
from playwright.sync_api import sync_playwright
p=Path('/mnt/data/powerforge_ux_v1_4/prototypes/powerforge-project-revisions-prototype.html')
pre=Path('/mnt/data/powerforge_ux_v1_4/previews');pre.mkdir(parents=True,exist_ok=True)
with sync_playwright() as play:
    browser=play.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':900},device_scale_factor=1)
    errors=[];page.on('pageerror',lambda e: errors.append(str(e)))
    page.set_content(p.read_text(encoding='utf-8'),wait_until='load');page.wait_for_timeout(100)
    assert page.locator('h1').first.inner_text().startswith('BC Ferries')
    page.locator('#revision-label').click();page.wait_for_timeout(340)
    assert page.locator('[data-action="edit-revision"]').count()==1
    # Contextual placement: metadata editor belongs to Revision Information, not the page header.
    assert page.locator('.head [data-action="edit-revision"]').count()==0
    card_header=page.locator('.card-top').filter(has=page.get_by_role('heading', name='Revision Information'))
    assert card_header.locator('[data-action="edit-revision"]').count()==1
    assert card_header.locator('[data-action="edit-revision"]').get_attribute('aria-label')=='Edit revision information'
    page.screenshot(path=str(pre/'revision-overview-preview.png'),full_page=True)
    page.locator('[data-action="edit-revision"]').click()
    assert page.locator('#edit-revision-form').count()==1
    assert page.locator('#save-revision').is_disabled()
    page.wait_for_timeout(400)
    page.screenshot(path=str(pre/'edit-revision-preview.png'),full_page=False)
    page.locator('#edit-identifier').fill('IFC 123 R1')
    page.locator('#edit-description').fill('Updated equipment ratings and system model assumptions')
    page.locator('#edit-frequency').fill('60')
    page.locator('#edit-phase').select_option('3')
    assert page.locator('#save-revision').is_enabled()
    page.wait_for_timeout(150)
    page.screenshot(path=str(pre/'edit-revision-filled-preview.png'),full_page=False)
    # Validate duplicate identifiers
    page.locator('#edit-identifier').fill('IFC 124')
    page.locator('#save-revision').click()
    assert 'already exists' in page.locator('#edit-error').inner_text()
    # Validate frequency
    page.locator('#edit-identifier').fill('IFC 123 R1')
    page.locator('#edit-frequency').fill('-1')
    page.locator('#save-revision').click()
    assert 'greater than zero' in page.locator('#edit-error').inner_text()
    page.locator('#edit-frequency').fill('60')
    # Unsaved changes guard
    page.locator('[data-action="close-drawer"]').last.click()
    assert page.locator('#discard-heading').count()==1
    page.locator('[data-action="keep-editing"]').click()
    assert page.locator('#edit-revision-form').count()==1
    page.locator('#save-revision').click()
    assert page.locator('#edit-revision-form').count()==0
    assert 'IFC 123 R1' in page.locator('.head h1').inner_text()
    assert 'IFC 123 R1' in page.locator('#side-revision-label').inner_text()
    assert '60 Hz' in page.locator('.detail-grid').first.inner_text()
    assert '3 phase' in page.locator('.detail-grid').first.inner_text()
    page.wait_for_timeout(400)
    page.screenshot(path=str(pre/'revision-overview-updated-preview.png'),full_page=True)
    # Cancel discard guard: no edit applied
    page.locator('[data-action="edit-revision"]').click()
    page.locator('#edit-description').fill('Unsaved test value')
    page.locator('[data-action="close-drawer"]').last.click()
    page.locator('[data-action="discard-revision-edit"]').click()
    assert 'Unsaved test value' not in page.locator('.head').inner_text()
    # Superseded read-only navigation
    page.locator('#nav-revisions').click();page.wait_for_timeout(320)
    page.locator('[data-open-revision="ifc122"]').first.click();page.wait_for_timeout(320)
    assert page.locator('[data-action="edit-revision"]').count()==0
    # Create and activate remain available
    page.locator('#nav-revisions').click();page.wait_for_timeout(320)
    page.locator('[data-action="create-revision"]').click()
    assert page.locator('#create-revision-form').count()==1
    page.locator('#new-identifier').fill('IFC 125')
    page.locator('#create-revision-form').evaluate('form => form.requestSubmit()')
    assert 'IFC 125' in page.locator('.head h1').inner_text()
    assert not errors, errors
    print('PASS: edit metadata, duplicate/invalid validation, guard, save/refetch UI, superseded read-only, create unaffected')
    print('Screen previews:',[x.name for x in pre.glob('*revision*preview.png')])
    browser.close()
