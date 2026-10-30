"""UX v1.13 standalone visual and interaction regression tests (offline page.set_content)."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
pro=ROOT/'prototypes'
project_src=(pro/'powerforge-projects-prototype.html').read_text()
revision_src=(pro/'powerforge-project-revisions-prototype.html').read_text()
assert 'function projectOverview()' in project_src
assert 'function overview(){' not in revision_src
assert "location.replace('powerforge-projects-prototype.html#project/p1')" in revision_src
assert "if(next==='overview'){location.href='powerforge-projects-prototype.html#project/p1';return;}" in revision_src
assert '<th>Actions</th>' not in revision_src
assert 'data-open-revision="${r.id}">View' not in revision_src
with sync_playwright() as play:
 b=play.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
 page=b.new_page(viewport={'width':1440,'height':960},device_scale_factor=1)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.set_content(project_src,wait_until='load')
 page.evaluate("view='overview'; selectedId='p1'; render()")
 assert page.get_by_role('heading',name='BC Ferries FMU').is_visible()
 assert page.locator('.head .eyebrow').count()==0
 details=page.locator('.overview-block[aria-label="Project details"]')
 activity=page.locator('.overview-block[aria-label="Revision activity"]')
 assert details.count()==1 and activity.count()==1
 assert details.bounding_box()['y']<activity.bounding_box()['y']
 assert page.get_by_role('button',name='Edit details').is_visible()
 assert page.get_by_role('heading',name='Project lifecycle').is_visible()
 assert page.get_by_role('heading',name='Project summary').is_visible()
 assert page.get_by_role('heading',name='Revision history').is_visible()
 assert page.get_by_text('Continue with IFC 123').is_visible()
 assert page.locator('.history-row').count()==3
 # v1.13: no secondary Active Revision summary card or empty two-column rail.
 assert page.locator('.overview-block[aria-label="Revision activity"] .overview-aside').count()==0
 assert page.get_by_text('ACTIVE REVISION',exact=True).count()==0
 assert page.locator('.revision-activity-stack > .card').count()==2
 for cls in ['revision-work-card', 'revision-history-card']:
  bounds=page.locator('.revision-activity-stack').bounding_box()
  cb=page.locator('.'+cls).bounding_box()
  assert abs(cb['width']-bounds['width'])<2, (cls,bounds,cb)
 assert page.get_by_role('button',name='Open active revision').is_visible()
 page.wait_for_timeout(360)
 page.screenshot(path=str(ROOT/'previews/project-overview-unified-preview.png'),full_page=True)
 page.screenshot(path=str(ROOT/'previews/project-overview-preview.png'),full_page=True)
 # Test a history-row click dispatch without navigating across blocked local pages.
 page.evaluate("openRevisionDetail=(id)=>window.__openedRevision=id")
 page.locator('.history-row[data-open-revision="ifc124"]').click()
 assert page.evaluate('window.__openedRevision')=='ifc124'
 page.get_by_role('button',name='Edit details').click()
 assert page.get_by_role('heading',name='Edit Project').is_visible()
 page.locator('#edit-name').fill('BC Ferries FMU - Revised')
 page.locator('#save-project').click();page.wait_for_timeout(610)
 assert page.get_by_role('heading',name='BC Ferries FMU - Revised').is_visible()
 page.evaluate("view='list';render()")
 assert page.get_by_role('heading',name='Projects').is_visible()
 page.get_by_role('button',name='New Project').click()
 assert page.get_by_role('heading',name='Create Project').is_visible()
 page.goto('about:blank')
 page.set_content(revision_src,wait_until='load')
 assert page.get_by_role('heading',name='Revisions').is_visible()
 assert page.locator('.head .eyebrow').count()==0
 assert page.locator('thead th').all_text_contents()==['Revision','Description / lineage','Status','Updated']
 assert page.locator('thead').get_by_text('Actions').count()==0
 assert page.locator('tbody tr.selectable').count()==3
 page.wait_for_timeout(360)
 page.screenshot(path=str(ROOT/'previews/revisions-preview.png'),full_page=True)
 row=page.locator('tr[data-open-revision="ifc123"]')
 row.focus();page.keyboard.press('Enter')
 page.wait_for_timeout(330)
 assert page.get_by_role('heading',name='Revision Information').is_visible()
 assert page.locator('.head .eyebrow').count()==0
 for width in [900,390]:
  page.set_viewport_size({'width':width,'height':850})
  page.goto('about:blank')
  page.set_content(project_src,wait_until='load')
  page.evaluate("view='overview';selectedId='p1';render()")
  assert page.locator('.overview-block').count()==2
  assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'),f'horizontal overflow at width {width}'
  page.wait_for_timeout(360)
  if width==390:page.screenshot(path=str(ROOT/'previews/project-overview-unified-mobile-preview.png'),full_page=True)
 assert not errors,errors
 b.close()
print('PASS v1.13 unified overview, project editor, main heading labels, revision row keyboard, responsive layout')
