"""Render the repository's small, offline assistant/API guides as static HTML."""
from pathlib import Path
import html
import re

ROOT=Path(__file__).resolve().parent.parent
LINKS={'../web/openapi.json':'/openapi.json','assistant-planning.md':'/assistant-guide.html','local-api.md':'/api-guide.html'}


def inline(value):
    value=html.escape(value)
    value=re.sub(r'`([^`]+)`',r'<code>\1</code>',value)
    value=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',value)
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',lambda match:'<a href="'+LINKS.get(match[2],match[2])+'">'+match[1]+'</a>',value)


def render(source):
    parts=[];lines=source.splitlines();i=0
    while i<len(lines):
        line=lines[i]
        if not line:i+=1;continue
        if line.startswith('```'):
            block=[];i+=1
            while i<len(lines) and not lines[i].startswith('```'):block.append(lines[i]);i+=1
            parts.append('<pre><code>'+html.escape('\n'.join(block))+'</code></pre>');i+=1;continue
        if line.startswith('#'):
            n=len(line)-len(line.lstrip('#'));parts.append(f'<h{n}>'+inline(line[n:].strip())+f'</h{n}>');i+=1;continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].startswith('|'):
                cells=[c.strip() for c in lines[i].strip('|').split('|')]
                if not all(re.fullmatch(r'[-: ]+',c) for c in cells):rows.append(cells)
                i+=1
            parts.append('<div class="table-scroll"><table>'+''.join('<tr>'+''.join(('<th>' if j==0 else '<td>')+inline(c)+('</th>' if j==0 else '</td>') for c in row)+'</tr>' for j,row in enumerate(rows))+'</table></div>');continue
        if line.startswith('- '):
            items=[]
            while i<len(lines) and lines[i].startswith('- '):items.append('<li>'+inline(lines[i][2:])+'</li>');i+=1
            parts.append('<ul>'+''.join(items)+'</ul>');continue
        if line.startswith('> '):parts.append('<blockquote>'+inline(line[2:])+'</blockquote>')
        else:parts.append('<p>'+inline(line)+'</p>')
        i+=1
    return ''.join(parts)


SHELL='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Open FI · Assistant tools</title><style>body{max-width:900px;margin:40px auto;padding:0 22px;font:15px/1.7 system-ui;color:#192d2a;background:#f4f6f2}h1,h2{line-height:1.25;margin-top:32px}pre{background:#e6eee5;padding:18px;border-radius:8px;overflow:auto}code{font:13px/1.6 ui-monospace,monospace}a{color:#1e5147}.table-scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:10px;border-bottom:1px solid #dce4dd;text-align:left}li{margin-bottom:8px}blockquote{border-left:3px solid #2e7765;padding-left:18px;margin-left:0}</style></head><body><a href="/">← Open planner</a> · <a href="/assistant-guide.html">ChatGPT &amp; Codex setup</a> · <a href="/api-guide.html">Local API</a> · <a href="/openapi.json">OpenAPI schema</a>'''

if __name__=='__main__':
    for source,target in [('local-api.md','api-guide.html'),('assistant-planning.md','assistant-guide.html')]:
        (ROOT/'web'/target).write_text(SHELL+render((ROOT/'docs'/source).read_text())+'</body></html>')
