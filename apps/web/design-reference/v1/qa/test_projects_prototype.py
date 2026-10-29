from pathlib import Path
from playwright.sync_api import sync_playwright
BASE=Path(__file__).resolve().parent.parent
u=(BASE/'prototypes/powerforge-projects-prototype.html').as_uri()
out=BASE/'previews';out.mkdir(exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
 page=b.new_page(viewport={'width':1440,'height':900},device_scale_factor=1)
 errs=[]; page.on('pageerror',lambda e:errs.append(str(e)))
 page.set_content((BASE/'prototypes/powerforge-projects-prototype.html').read_text(),wait_until='load')
 page.screenshot(path=str(out/'projects-list-preview.png'),full_page=True)
 assert page.get_by_role('heading',name='Projects').is_visible()
 assert page.locator('tbody tr').count()==6
 page.get_by_label('Search projects').fill('ferries')
 assert page.locator('tbody tr').count()==2
 page.get_by_label('Search projects').fill('')
 page.get_by_role('button',name='Cancelled').click()
 assert page.locator('tbody tr').count()==1
 page.get_by_role('button',name='All',exact=False).click()
 page.get_by_role('button',name='New Project').click()
 page.screenshot(path=str(out/'create-project-preview.png'),full_page=True)
 assert page.get_by_role('heading',name='Create Project').is_visible()
 page.locator('#create-submit').click()
 assert page.locator('#error-new-name').inner_text()=='Project name is required.'
 page.locator('#new-number').fill('PF-2026-007')
 page.locator('#new-name').fill('Ridgeline Substation')
 page.locator('#new-client').fill('Acme Energy LLC')
 page.locator('#first-revision-check').check()
 assert page.locator('#first-revision-fields').is_visible()
 page.locator('#new-rev-id').fill('IFC 001')
 page.locator('#create-submit').click()
 page.wait_for_timeout(730)
 assert page.get_by_role('heading',name='Ridgeline Substation').is_visible()
 page.screenshot(path=str(out/'project-overview-new-preview.png'),full_page=True)
 page.get_by_role('button',name='Edit',exact=True).click()
 page.wait_for_timeout(350)
 page.screenshot(path=str(out/'edit-project-preview.png'),full_page=False)
 assert page.get_by_role('heading',name='Edit Project').is_visible()
 assert page.locator('#save-project').is_disabled()
 page.locator('#edit-name').fill('Ridgeline Substation Expansion')
 assert page.locator('#save-project').is_enabled()
 page.locator('#save-project').click()
 page.wait_for_timeout(580)
 assert page.get_by_role('heading',name='Ridgeline Substation Expansion').is_visible()
 page.get_by_role('button',name='Pause').click()
 page.get_by_role('button',name='Pause project').click()
 assert page.get_by_text('Paused',exact=True).count()>=1
 page.get_by_role('button',name='Resume').click()
 page.get_by_role('button',name='Resume project').click()
 assert page.get_by_text('Active',exact=True).count()>=1
 page.get_by_role('button',name='All Projects').click()
 assert page.locator('tbody tr').count()==7
 assert not errs, errs
 print('PASS: list filtering, creation validations, first revision, project edit & save, pause/resume, list refresh; console errors=',errs)
 b.close()
