from pathlib import Path
from playwright.sync_api import sync_playwright

BASE=Path(__file__).resolve().parents[1]
URL=(BASE/'prototypes'/'powerforge-topology-prototype.html').as_uri()
PRE=BASE/'previews';PRE.mkdir(exist_ok=True)

def choose(page, selector, value):
    # The visible select is now a custom combobox; preserve the native select as state source.
    page.locator(selector).evaluate(
        "(el, value) => { el.value = value; el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }",
        value,
    )

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1600,'height':1020},device_scale_factor=1)
    errors=[];page.on('pageerror',lambda e: errors.append(str(e)))
    page.set_content((BASE/'prototypes'/'powerforge-topology-prototype.html').read_text(), wait_until='load')
    assert page.get_by_role('heading',name='Topology').is_visible()
    assert page.get_by_role('heading',name='Nodes').is_visible()
    assert page.get_by_role('heading',name='Connections').is_visible()
    page.screenshot(path=str(PRE/'topology-overview-preview.png'),full_page=True)
    page.locator('[data-inspect="node:n2"]').click()
    assert page.get_by_label('Topology quick details').is_visible()
    assert page.get_by_text('Application-managed terminals cannot',exact=False).count()==0
    assert page.get_by_role('button',name='Remove',exact=True).count()==0
    page.screenshot(path=str(PRE/'topology-terminal-details-preview.png'),full_page=True)
    page.locator('[data-inspect="connection:c1"]').click()
    assert page.get_by_label('Topology quick details').is_visible()
    page.get_by_role('button',name='Edit connection').click()
    assert page.get_by_role('dialog',name='Edit Connection').is_visible()
    page.screenshot(path=str(PRE/'topology-edit-connection-preview.png'),full_page=True)
    choose(page, '#from', 'n2')
    choose(page, '#to', 'n2')
    page.get_by_role('button',name='Save changes').click()
    assert page.get_by_text('Select two different active endpoint nodes.').is_visible()
    choose(page, '#to', 'n3')
    page.locator('#voltage').fill('600')
    choose(page, '#unit', 'V')
    page.get_by_role('button',name='Save changes').click()
    assert page.get_by_label('Topology quick details').is_visible()
    assert page.locator('.inspector').get_by_text('600 V').is_visible()
    page.get_by_role('button',name='Add Electrical Node').click()
    page.get_by_label('Display label (optional)').fill('Auxiliary junction')
    page.get_by_role('button',name='Create',exact=True).click()
    assert page.get_by_text('Auxiliary junction',exact=False).count()>0
    page.locator('[data-inspect="node:n4"]').click()
    page.get_by_role('button',name='Remove',exact=True).click()
    assert page.get_by_role('alertdialog').is_visible()
    assert 'will NOT restore' in page.get_by_role('alertdialog').inner_text()
    page.get_by_role('alertdialog').get_by_role('button',name='Remove').click()
    assert page.get_by_text('Removed objects').count()>0
    choose(page, '#life', 'ALL')
    page.locator('[data-inspect="connection:c2"]').click()
    assert page.get_by_label('Topology quick details').is_visible()
    assert page.get_by_role('button',name='Restore').is_disabled()
    assert page.get_by_text('Restore both endpoint nodes before restoring this connection.').count()>0
    page.locator('[data-inspect="node:n4"]').click()
    page.get_by_role('button',name='Restore').click()
    page.locator('[data-inspect="connection:c2"]').click()
    page.get_by_role('button',name='Restore').click()
    choose(page, '#mode', 'readonly')
    assert page.get_by_text('This revision is superseded.',exact=False).is_visible()
    assert page.get_by_role('button',name='Add Electrical Node').count()==0
    assert not errors,errors
    browser.close()
print('PASS: Topology overview/inspection/editing/add/remove/restore/read-only')
