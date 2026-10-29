"""Acceptance test: unselected hover is exactly #F5F8FA, selected blue remains on rest and darkens on hover."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
html=ROOT/'prototypes/powerforge-design-system-prototype.html'
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1580,'height':980},device_scale_factor=1)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.set_content(html.read_text(),wait_until='load')
 page.get_by_role('tab',name='Selects & Checkboxes').click()
 combo=page.locator('#pf-controls-choice').locator('xpath=..').get_by_role('combobox')
 combo.click()
 selected=page.get_by_role('option',name='All equipment types')
 item=page.get_by_role('option',name='2-Winding Transformer')
 chosen=page.locator('#pf-controls-choice')
 # Open menu without moving pointer over selected option
 page.wait_for_timeout(190)
 assert selected.get_attribute('aria-selected')=='true'
 assert selected.evaluate('(el)=>getComputedStyle(el).backgroundColor')=='rgb(230, 238, 244)', 'Selected resting blue'
 assert item.evaluate('(el)=>getComputedStyle(el).backgroundColor')=='rgba(0, 0, 0, 0)' or item.evaluate('(el)=>getComputedStyle(el).backgroundColor')=='rgb(255, 255, 255)', 'Unselected resting background'
 item.hover();page.wait_for_timeout(210)
 assert item.evaluate('(el)=>getComputedStyle(el).backgroundColor')=='rgb(245, 248, 250)', 'Unselected hover should be #F5F8FA'
 assert selected.evaluate('(el)=>getComputedStyle(el).backgroundColor')=='rgb(230, 238, 244)', 'Selected remains blue when pointer elsewhere'
 assert chosen.input_value()=='all', 'Hover does not commit selection'
 page.screenshot(path=str(ROOT/'previews/ux9-controls-dropdown-unselected-hover-preview.png'),full_page=False)
 selected.hover();page.wait_for_timeout(210)
 assert selected.evaluate('(el)=>getComputedStyle(el).backgroundColor')=='rgb(214, 227, 237)', 'Selected hover should darken to #D6E3ED'
 assert item.evaluate('(el)=>getComputedStyle(el).backgroundColor')=='rgba(0, 0, 0, 0)' or item.evaluate('(el)=>getComputedStyle(el).backgroundColor')=='rgb(255, 255, 255)'
 assert chosen.input_value()=='all'
 page.screenshot(path=str(ROOT/'previews/ux9-controls-dropdown-hover-preview.png'),full_page=False)
 item.click()
 assert chosen.input_value()=='transformer'
 combo.click()
 newly_selected=page.get_by_role('option',name='2-Winding Transformer')
 page.wait_for_timeout(180)
 assert newly_selected.evaluate('(el)=>getComputedStyle(el).backgroundColor')=='rgb(230, 238, 244)'
 combo.focus();page.keyboard.press('Home')
 first=page.get_by_role('option',name='All equipment types')
 assert first.get_attribute('data-active')=='true'
 page.wait_for_timeout(200)
 assert first.evaluate('(el)=>getComputedStyle(el).backgroundColor')=='rgb(245, 248, 250)', 'Keyboard highlight matches neutral hover'
 assert newly_selected.evaluate('(el)=>getComputedStyle(el).backgroundColor')=='rgb(230, 238, 244)', 'Selection persists under keyboard navigation'
 page.keyboard.press('Escape')
 page.emulate_media(reduced_motion='reduce')
 combo.click()
 first.hover()
 assert all(float(v.strip()[:-1]) < .001 for v in first.evaluate('(el)=>getComputedStyle(el).transitionDuration').split(',')), 'Reduced-motion transition should be near zero'
 page.keyboard.press('Escape')
 assert not errors,errors
 css=(ROOT/'assets/powerforge-controls.css').read_text();js=(ROOT/'assets/powerforge-controls.js').read_text()
 for f in (ROOT/'prototypes').glob('*.html'):
  s=f.read_text();assert css in s and js in s,f
 browser.close()
print('PASS v1.11 dropdown selected/unselected hover, keyboard navigation, reduced motion and six-prototype CSS consistency')
