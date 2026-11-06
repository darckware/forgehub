import json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parent;root.mkdir(exist_ok=True)
user=dict(id='test-admin',username='admin.test',is_admin=True,is_active=True,ui_language='pt-BR',full_name='Test admin')
proposal=dict(id='p1',agent_id='a1',message_number=42,status='proposed',reason='Instalar ferramenta solicitada',content='sudo apt install example\n'+'printf "Verificação concluída"\n'*12,shell='sh',risk='change',timeout_seconds=30,requires_elevation=True,content_hash='a'*64,expected_effect='Ferramenta disponível',rollback='Remover pacote',machines=[dict(id='m1',name='linux-target.test')],parameters=[])
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path='/root/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome',headless=True,args=['--no-sandbox'])
 for width in [390,1440]:
  page=browser.new_page(viewport=dict(width=width,height=1000),device_scale_factor=1)
  page.add_init_script('localStorage.setItem("forgehub-auth",'+json.dumps(json.dumps(dict(state=dict(token='synthetic-visual-session',user=user,permissions={},actions={}),version=0)))+');localStorage.setItem("i18nextLng","pt-BR");')
  def route(r):
   path=r.request.url.split('/api/v1/')[-1].split('?')[0]
   data=[]
   if path=='maintenance-proposals':data=[proposal]
   elif path=='servers/readiness':data=dict(entries=[],checked_at=None)
   elif path=='vpn/status':data=dict(server=dict(posture={}),peers=[],sources=[])
   elif path=='auth/me':data=user
   elif path=='notifications/unread-count':data=dict(count=0)
   elif path=='agents':data=[dict(id='a1',name='Aramis',is_active=True,status='active')]
   r.fulfill(status=200,content_type='application/json',body=json.dumps(data))
  page.on('pageerror', lambda e: print('PAGE ERROR:', str(e)))
  page.route('**/api/v1/**',route)
  page.goto('http://127.0.0.1:5188/remote-access')
  page.wait_for_timeout(5000)
  print('PAGE',page.url,page.locator('body').inner_text()[:800])
  page.get_by_role('button',name='Ver proposta').wait_for(timeout=10000)
  page.get_by_role('button',name='Ver proposta').click()
  page.get_by_text(proposal['content_hash'],exact=True).wait_for()
  assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
  dialog=page.get_by_role('dialog')
  assert dialog.is_visible()
  page.screenshot(path=str(root/f'proposal-{width}.png'),full_page=True)
  page.get_by_role('button',name='Recusar',exact=True).click()
  page.get_by_label('Motivo da recusa').fill('Alvo incorreto')
  page.screenshot(path=str(root/f'rejection-{width}.png'),full_page=True)
  print(f'{width}px: dialog, complete hash, rejection field, no page overflow verified')
  page.close()
 browser.close()
