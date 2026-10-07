#!/usr/bin/env python3
"""Validate static HTML structure and local/source links without third-party tools."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, unquote
root=Path(__file__).resolve().parents[1]
class Page(HTMLParser):
 def __init__(self): super().__init__(); self.ids=[]; self.links=[]; self.stack=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if 'id' in a: self.ids.append(a['id'])
  if tag=='a': self.links.append(a.get('href',''))
  if tag not in {'meta','link','br','hr','img','input','source','wbr','area','base','embed','param','track','col'}: self.stack.append(tag)
 def handle_startendtag(self,tag,attrs):
  self.handle_starttag(tag,attrs)
  if self.stack and self.stack[-1]==tag: self.handle_endtag(tag)

 def handle_endtag(self,tag):
  assert self.stack and self.stack[-1]==tag, (tag,self.stack[-5:])
  self.stack.pop()
count=0
for file in (root/'public').rglob('*.html'):
 p=Page();p.feed(file.read_text()); assert not p.stack, (file,p.stack)
 assert len(p.ids)==len(set(p.ids)), file
 for link in p.links:
  u=urlparse(link)
  if link.startswith('#'): assert u.fragment in p.ids,(file,link)
  elif u.path.startswith('/') and not u.netloc:
   target=root/'public'/unquote(u.path).lstrip('/')
   if target.is_dir():target=target/'index.html'
   assert target.exists(),(file,link)
  elif link.startswith('https://github.com/Martines90/dagp/blob/main/'):
   assert (root/link.split('/blob/main/',1)[1]).exists(),link
  count+=1
print(f'Validated nesting, duplicate IDs, local routes, anchors and repository source links: {count} links across all HTML pages.')
import json
import re
import xml.etree.ElementTree as ET
manifest=json.loads((root/'public/dagp.json').read_text())
assert manifest['license']=='MIT'
for entry in manifest['documents']:
    route=urlparse(entry['url']).path.lstrip('/')
    path=root/'public'/route
    assert path.exists(),entry
    bundled=root/'integrations/docs-mcp/docs'/('protocol.md' if entry['id']=='protocol' else entry['file'])
    assert path.read_bytes()==bundled.read_bytes(),entry['id']
for match in re.finditer(r'\]\((https://dagp.net/[^)]+)\)',(root/'public/llms.txt').read_text()):
    path=root/'public'/urlparse(match.group(1)).path.lstrip('/')
    assert path.exists(),match.group(1)
for node in ET.parse(root/'public/sitemap.xml').getroot():
    url=node[0].text
    target=root/'public'/urlparse(url).path.lstrip('/')/'index.html'
    assert target.exists(),url
package=json.loads((root/'integrations/docs-mcp/package.json').read_text())
registry=json.loads((root/'integrations/docs-mcp/server.json').read_text())
assert package['mcpName']==registry['name']
assert package['version']==registry['version']
npm=json.loads((root/'integrations/docs-mcp/server.npm.json').read_text())
assert package['name']==npm['packages'][0]['identifier']
assert package['version']==npm['packages'][0]['version']
assert registry['packages'][0]['registryType']=='mcpb'
assert re.fullmatch('[0-9a-f]{64}',registry['packages'][0]['fileSha256'])
assert not (root/'public/.well-known/agent-card.json').exists(), 'Do not advertise a nonexistent A2A service'
print('Validated discovery routes, sitemap, bundled source consistency and package identities.')
