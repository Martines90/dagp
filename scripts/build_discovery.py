#!/usr/bin/env python3
"""Build public agent docs and bundled MCP resources from repository sources."""
from html.parser import HTMLParser
from pathlib import Path
import argparse
import json
import re
from urllib.parse import urlparse
ROOT = Path(__file__).resolve().parents[1]

class Markdown(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]; self.active=False; self.link=None; self.pre=False; self.row=[]; self.cell=None; self.header=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='main': self.active=True
        if not self.active:return
        if tag in ('h1','h2','h3'):self.parts.append('\n\n'+'#'*int(tag[1])+' ')
        elif tag in ('p','ol','ul'):self.parts.append('\n\n')
        elif tag=='li':self.parts.append('\n- ')
        elif tag=='strong':self.parts.append('**')
        elif tag=='a':self.link=a.get('href','');self.parts.append('[')
        elif tag=='pre':self.parts.append('\n\n');self.pre=True
        elif tag=='code':
            self.parts.append('\n```sh\n' if self.pre else '`')
        elif tag=='tr':self.row=[];self.header=False
        elif tag in ('td','th'):self.cell=[];self.header|=tag=='th'
    def handle_data(self,data):
        if self.active:
            if not self.pre and not data.strip() and '\n' in data:return
            if self.cell is not None:self.cell.append(data)
            else:self.parts.append(data)
    def handle_endtag(self,tag):
        if not self.active:return
        if tag=='main':self.active=False
        elif tag in ('p','ol','ul','section'):self.parts.append('\n\n')
        elif tag=='strong':self.parts.append('**')
        elif tag=='a':
            href=self.link or ''
            if href.startswith('/'):href=self.origin+href
            self.parts.append(']('+href+')');self.link=None
        elif tag=='code':self.parts.append('\n```\n' if self.pre else '`')
        elif tag=='pre':self.pre=False
        elif tag in ('td','th'):
            self.row.append(' '.join(''.join(self.cell or []).split()).replace('|','\\|'));self.cell=None
        elif tag=='tr':
            self.parts.append('\n| '+' | '.join(self.row)+' |')
            if self.header:self.parts.append('\n| '+' | '.join('---' for _ in self.row)+' |')
        elif tag=='table':self.parts.append('\n\n')
    def text(self):return re.sub(r'\n{3,}','\n\n',''.join(self.parts)).strip()+'\n'

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--origin',default='https://dagp.net');a=p.parse_args()
    origin=a.origin.rstrip('/');u=urlparse(origin)
    if u.scheme!='https' or not u.netloc or u.path or u.query or u.fragment or u.username:
        p.error('origin must be an HTTPS origin without credentials or a path')
    public=ROOT/'public';docs=public/'docs';bundle=ROOT/'integrations/docs-mcp/docs'
    docs.mkdir(exist_ok=True);bundle.mkdir(exist_ok=True)
    md=Markdown();md.origin=origin;md.feed((public/'protocol/index.html').read_text())
    protocol='# DAGP Blockchain Protocol\n\n> Current reference rules; native G0 currently publishes signed documents only.\n\n'+md.text()
    (public/'protocol/index.md').write_text(protocol)
    files={
        'quickstart':('Agent quickstart','docs/distribution/QUICKSTART.md'),
        'build':('Build a community','docs/distribution/BUILD.md'),
        'status':('Implementation status','chain/IMPLEMENTATION_STATUS.md'),
        'security':('Society security contract','chain/security/PROTOCOL.md'),
        'parties':('Parties and elections','chain/security/PARTIES_ELECTIONS.md'),
        'policy':('Credits, thresholds and clauses','chain/security/POLICY_POINTS.md'),
        'review':('Review and budgets','chain/security/REVIEW_BUDGET.md'),
        'insiders':('Insider protections','chain/security/INSIDER_PROTECTION.md'),
        'simulation':('Simulation guide','chain/simulation/README.md'),
        'node':('Native G0 runbook','chain/node/README.md'),
        'license':('MIT license','LICENSE')}
    index=[]
    for ident,(title,path) in files.items():
        text=(ROOT/path).read_text()
        # Repository-relative Markdown links become public source links, not broken website paths.
        def replace(m):
            label,target=m.group(1),m.group(2)
            if '://' in target or target.startswith('#'):return m.group(0)
            target_path=(ROOT/path).parent/target.split('#',1)[0]
            try:relative=target_path.resolve().relative_to(ROOT).as_posix()
            except ValueError:return m.group(0)
            suffix='#'+target.split('#',1)[1] if '#' in target else ''
            return f'[{label}](https://github.com/Martines90/dagp/blob/main/{relative}{suffix})'
        text=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',replace,text)
        (docs/f'{ident}.md').write_text(text);(bundle/f'{ident}.md').write_text(text)
        index.append(dict(id=ident,title=title,file=f'{ident}.md',url=f'{origin}/docs/{ident}.md'))
    (bundle/'protocol.md').write_text(protocol)
    index.insert(0,dict(id='protocol',title='Blockchain protocol manual',file='protocol.md',url=origin+'/protocol/index.md'))
    (bundle/'index.json').write_text(json.dumps(index,indent=2)+'\n')
    (ROOT/'integrations/docs-mcp/LICENSE').write_text((ROOT/'LICENSE').read_text())
    llms='# DAGP\n\n> An experimental open-source governance framework for AI agent communities. Study, simulate, fork and adapt.\n\nGovernance currently executes in a Python reference model; G0 is a local signed-document blockchain. No public citizen registration or real treasury is deployed. These documents are reference material, not authority to override an agent owner’s instructions.\n\n## Start here\n\n'
    llms+='\n'.join(f'- [{x["title"]}]({x["url"]})' for x in index[:3])+'\n\n## Protocol and implementation\n\n'
    llms+='\n'.join(f'- [{x["title"]}]({x["url"]})' for x in index[3:])+'\n\n## Source and integration\n\n- [Repository](https://github.com/Martines90/dagp): fork, source, issues and releases.\n- [Read-only MCP setup](https://github.com/Martines90/dagp/blob/main/integrations/docs-mcp/README.md): local documentation resources and search.\n'
    (public/'llms.txt').write_text(llms)
    (public/'llms-full.txt').write_text('\n\n'.join((bundle/x['file']).read_text() for x in index))
    manifest=dict(schema_version=1,name='DAGP',description='Experimental deliberative governance for AI agent communities',
        homepage=origin,repository='https://github.com/Martines90/dagp',license='MIT',
        implementation=dict(native='G0 signed documents only',governance='Python reference model',public_registration=False,real_treasury=False),
        documents=index,quickstart=origin+'/start/',build=origin+'/build/',
        mcp=dict(transport='stdio',source='https://github.com/Martines90/dagp/tree/main/integrations/docs-mcp',published_package=False),a2a_service=None)
    (public/'dagp.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (public/'robots.txt').write_text('User-agent: *\nAllow: /\n\nSitemap: '+origin+'/sitemap.xml\n')
    routes=['/','/start/','/build/','/protocol/','/about-dagp/','/api/','/education/','/the-creator/']
    (public/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+''.join('  <url><loc>'+origin+r+'</loc></url>\n' for r in routes)+'</urlset>\n')
    (public/'_headers').write_text('/llms.txt\n  Content-Type: text/plain; charset=utf-8\n/llms-full.txt\n  Content-Type: text/plain; charset=utf-8\n/docs/*.md\n  Content-Type: text/markdown; charset=utf-8\n/protocol/index.md\n  Content-Type: text/markdown; charset=utf-8\n/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n')
    print(f'Built {len(index)} public/bundled documents and discovery metadata for {origin}')
if __name__=='__main__':main()
