#!/usr/bin/env python3
"""Controle e rastreio da grade OSSU-br (Ciência da Computação).

    python3 serve.py        # http://127.0.0.1:8765
    python3 serve.py test   # self-checks

Grade fixa de 35 cursos em 7 etapas, com pré-requisitos (DAG). Fluxo:
home (etapas/cursos) -> curso (aulas) -> assistir (timer + notas + link).
Concluir um curso (todas as aulas assistidas OU botão manual) libera os
cursos que dependem dele. Soft-lock: curso bloqueado mostra 🔒 mas abre.

Fonte da verdade (sem dependencias externas):
  curriculum.json            -> grade: cursos (etapa, pré-req, provider, aulas)
  progress.json              -> {lessons: {...}, courses: {<cid>: {completed}}}
  courses/<curso>/<aula>.md  -> tag (frontmatter) + suas anotacoes

Tempo automatico: enquanto assiste, o navegador manda um heartbeat a cada
15s que estende a sessao aberta; fechou a aba, o tempo gravado e o real.
"""
import os, re, json, html, sys, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.abspath(__file__))
COURSES = os.path.join(ROOT, "courses")
CUR = os.path.join(ROOT, "curriculum.json")
PROG = os.path.join(ROOT, "progress.json")
HEARTBEAT_MS = 15000
ICON = {"todo": "○", "watching": "▶", "paused": "⏸", "watched": "✓"}


# ---- io -----------------------------------------------------------------

def load(path, default):
    if os.path.exists(path) and os.path.getsize(path):
        return json.load(open(path, encoding="utf-8"))
    return default


def load_prog():
    p = load(PROG, {"lessons": {}, "courses": {}})
    if "lessons" not in p:  # migração defensiva do formato plano antigo
        p = {"lessons": p, "courses": {}}
    p.setdefault("courses", {})
    return p


def save(path, data):
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def fetch_playlist(url):
    """(video_id, título) de TODA a playlist do YouTube, via yt-dlp."""
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist", "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return [(en["id"], en.get("title") or en["id"])
            for en in (info.get("entries") or []) if en.get("id")]


# ---- time model ---------------------------------------------------------

def dur(s):
    if s.get("start") and s.get("end"):
        a = datetime.datetime.fromisoformat(s["start"])
        b = datetime.datetime.fromisoformat(s["end"])
        return max(0, (b - a).total_seconds())  # relogio pra tras nao vira negativo
    return 0


def recompute(e):
    e["seconds"] = int(sum(dur(s) for s in e.get("sessions", [])))
    return e


def times(e):
    ss = e.get("sessions", [])
    started = ss[0]["start"] if ss else ""
    finished = ss[-1]["end"] if e.get("status") == "watched" and ss else ""
    return started, finished


def fmt(secs):
    secs = int(secs)
    h, m = secs // 3600, secs % 3600 // 60
    return f"{h}h {m:02d}m" if h else f"{m}m" if m else f"{secs}s"


# ---- catalog / progresso de curso ---------------------------------------

def course_by_id(cur, cid):
    return next((c for c in cur["courses"] if c["id"] == cid), None)


def get_lesson(cur, cid, lid):
    c = course_by_id(cur, cid)
    if c:
        for l in c["lessons"]:
            if l["id"] == lid:
                return c, l
    return None, None


def valid_keys(cur):
    return {f'{c["id"]}/{l["id"]}' for c in cur["courses"] for l in c["lessons"]}


def new_entry():
    return {"status": "todo", "sessions": [], "seconds": 0}


def entry(prog, key):
    return prog["lessons"].setdefault(key, new_entry())


def watched_count(cur, prog, cid):
    c = course_by_id(cur, cid)
    ls = c["lessons"] if c else []
    return sum(1 for l in ls if prog["lessons"].get(f'{cid}/{l["id"]}', {}).get("status") == "watched")


def is_complete(cur, prog, cid):
    if prog["courses"].get(cid, {}).get("completed"):
        return True
    c = course_by_id(cur, cid)
    ls = c["lessons"] if c else []
    return bool(ls) and watched_count(cur, prog, cid) == len(ls)


def missing_prereqs(cur, prog, course):
    return [p for p in course.get("prereqs", []) if not is_complete(cur, prog, p)]


def course_title(cur, cid):
    c = course_by_id(cur, cid)
    return c["title"] if c else cid


# ---- notes --------------------------------------------------------------

def notes_path(cid, lid):
    d = os.path.join(COURSES, cid)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{lid}.md")


def read_body(cid, lid):
    p = notes_path(cid, lid)
    if not os.path.exists(p):
        return ""
    t = open(p, encoding="utf-8").read()
    m = re.match(r"^---\n.*?\n---\n?(.*)$", t, re.S)  # tira o frontmatter, sobram as notas
    return (m.group(1) if m else t).strip()


def write_md(cid, lid, cur, prog, body):
    """Grava o .md = tag completa da aula (frontmatter) + notas."""
    course, lesson = get_lesson(cur, cid, lid)
    e = prog["lessons"].get(f"{cid}/{lid}", new_entry())
    started, finished = times(e)
    fm = [
        ("course", course["title"]),
        ("lesson", lesson["title"]),
        ("source_url", lesson.get("url", "")),
        ("started_at", started),
        ("finished_at", finished),
        ("seconds", e.get("seconds", 0)),
        ("status", e.get("status", "todo")),
    ]
    # ponytail: valores sem aspas duplas internas; titulo do YouTube nao costuma ter. Se tiver, escapar.
    head = "\n".join(f"{k}: {v}" if k == "seconds" else f'{k}: "{v}"' for k, v in fm)
    content = body.strip()
    open(notes_path(cid, lid), "w", encoding="utf-8").write(
        f"---\n{head}\n---\n" + (f"\n{content}\n" if content else "\n")
    )


# ---- html ---------------------------------------------------------------

STYLE = """<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{font:16px/1.5 system-ui,sans-serif;max-width:900px;margin:1.4rem auto;padding:0 1rem;background:#14171c;color:#e6e6e6}
a{color:#58a6ff;text-decoration:none} a:hover{text-decoration:underline}
.crumb{color:#7d8590;font-size:.85rem;margin-bottom:.6rem}
h1{font-size:1.4rem;margin:.2rem 0} h2{font-size:1rem;color:#9aa;margin:1.4rem 0 .3rem;border-bottom:1px solid #21262d;padding-bottom:.2rem}
.card,.lrow{border:1px solid #2a2f36;border-radius:8px;margin:.4rem 0;padding:.6rem .8rem;display:flex;align-items:center;gap:.7rem}
.card:hover,.lrow:hover{border-color:#3d444d}
.card.locked{opacity:.6}
.grow{flex:1} .muted{color:#7d8590;font-size:.85rem}
.bar{height:5px;background:#2a2f36;border-radius:9px;overflow:hidden;margin-top:.35rem;max-width:320px}
.bar>span{display:block;height:100%;background:#1a7f37}
.ic{width:1.2rem;text-align:center;font-weight:700}
.ic.watched{color:#3fb950} .ic.watching{color:#f0b429} .ic.paused{color:#d29922} .ic.todo{color:#565f6a}
.prov,.cat{font-size:.65rem;padding:.05rem .45rem;border-radius:99px;margin-left:.3rem;vertical-align:middle}
.prov.yt{background:#3a1519;color:#ff9aa2} .prov.co{background:#0d2440;color:#7fb2ff}
.cat.obr{background:#12261a;color:#7fe0a0} .cat.elet{background:#2a1e33;color:#d0a3ff}
.tag{font-size:.8rem} .tag.ok{color:#3fb950} .tag.lock{color:#d29922}
.banner{border-radius:8px;padding:.5rem .7rem;margin:.5rem 0;font-size:.9rem}
.banner.ok{background:#0f2f1a;color:#7fe0a0} .banner.lock{background:#2f2410;color:#e6c07b}
button,.btn{font:inherit;padding:.4rem .8rem;border:0;border-radius:6px;background:#2f81f7;color:#fff;cursor:pointer;display:inline-block}
button.stop,.btn.stop{background:#1a7f37} button.ghost{background:#30363d} button.warn{background:#9e6a00}
input,select,textarea{font:inherit;padding:.45rem;background:#0d1117;color:#e6e6e6;border:1px solid #2a2f36;border-radius:6px;width:100%}
form.add{display:grid;gap:.5rem;border:1px solid #2a2f36;border-radius:8px;padding:.8rem;margin:1rem 0}
.timer{font-variant-numeric:tabular-nums;font-weight:700;font-size:1.5rem;color:#f0b429}
#notes{min-height:22rem;font:14px/1.6 ui-monospace,monospace;margin:.6rem 0}
.saved{color:#3fb950;font-size:.82rem} .toolbar{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}
</style>"""

JS = """<script>
function post(u,d){return fetch(u,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams(d)});}
function act(u,id,go){post(u,{id:id}).then(function(){location.href=go||location.href;});}
function submitForm(f,u){post(u,Object.fromEntries(new FormData(f))).then(function(){location.reload();});return false;}
</script>"""


def page(title, body, script=""):
    return (f'<!doctype html><html lang="pt-br"><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title>{STYLE}{body}{JS}{script}</html>')


def e(s):
    return html.escape(str(s))


def next_lesson(course, prog):
    for l in course["lessons"]:
        if prog["lessons"].get(f'{course["id"]}/{l["id"]}', {}).get("status") != "watched":
            return l["id"]
    return course["lessons"][0]["id"] if course["lessons"] else None


def prov_badge(c):
    return ('<span class="prov co">Coursera</span>' if c.get("provider") == "coursera"
            else '<span class="prov yt">YouTube</span>')


def cat_badge(c):
    return ('<span class="cat elet">Eletiva</span>' if c.get("category") == "eletiva"
            else '<span class="cat obr">Obrigatória</span>')


# ---- views --------------------------------------------------------------

def course_card(cur, prog, c):
    cid = c["id"]
    total = len(c["lessons"])
    done = watched_count(cur, prog, cid)
    missing = missing_prereqs(cur, prog, c)
    complete = is_complete(cur, prog, cid)
    right = ""
    if complete:
        state = '<span class="tag ok">✓ concluído</span>'
    elif missing:
        names = ", ".join(course_title(cur, m) for m in missing)
        state = f'<span class="tag lock">🔒 requer: {e(names)}</span>'
    elif total:
        pct = int(done / total * 100)
        state = (f'<div class="muted">{done}/{total} assistidas</div>'
                 f'<div class="bar"><span style="width:{pct}%"></span></div>')
        nxt = next_lesson(c, prog)
        right = f'<a class="btn" href="/watch/{e(cid)}/{e(nxt)}">continuar</a>' if nxt else ""
    else:
        state = '<span class="muted">curso externo — sem aulas importadas</span>'
    cls = "card locked" if (missing and not complete) else "card"
    return (f'<div class="{cls}"><div class="grow">'
            f'<a href="/course/{e(cid)}"><b>{e(c["title"])}</b></a>{prov_badge(c)}{cat_badge(c)}'
            f'<div>{state}</div></div>{right}</div>')


def render_home(cur, prog):
    mand = [c for c in cur["courses"] if c.get("category") != "eletiva"]
    done = sum(1 for c in mand if is_complete(cur, prog, c["id"]))
    body = ['<h1>🎓 OSSU-br — Ciência da Computação</h1>',
            f'<div class="muted">{done}/{len(mand)} cursos obrigatórios concluídos</div>']
    # obrigatórias e eletivas juntas na mesma etapa (obrigatórias primeiro)
    for st in sorted({c.get("stage", 0) for c in cur["courses"]}):
        body.append(f'<h2>{st}ª Etapa</h2>')
        stage_courses = [x for x in cur["courses"] if x.get("stage") == st]
        for c in sorted(stage_courses, key=lambda x: x.get("category") == "eletiva"):
            body.append(course_card(cur, prog, c))
    return page("OSSU-br — Ciência da Computação", "".join(body))


def render_course(cur, prog, cid):
    c = course_by_id(cur, cid)
    if not c:
        return None
    missing = missing_prereqs(cur, prog, c)
    complete = is_complete(cur, prog, cid)
    manual = bool(prog["courses"].get(cid, {}).get("completed"))
    body = [f'<div class="crumb"><a href="/">← grade</a></div>',
            f'<h1>{e(c["title"])}{prov_badge(c)}{cat_badge(c)}</h1>']

    if c.get("source_url"):
        body.append(f'<div class="muted"><a href="{e(c["source_url"])}" '
                    'target="_blank" rel="noopener">🔗 fonte</a></div>')

    if missing and not complete:
        names = ", ".join(course_title(cur, m) for m in missing)
        body.append(f'<div class="banner lock">🔒 Pré-requisitos pendentes: {e(names)} '
                    '— você pode assistir mesmo assim.</div>')

    if manual:
        body.append('<div class="banner ok">✓ concluído manualmente '
                    f'<button class="ghost" onclick="act(\'/complete-course\',\'{e(cid)}\')">desfazer</button></div>')
    elif complete:
        body.append('<div class="banner ok">✓ concluído (todas as aulas assistidas)</div>')
    else:
        body.append(f'<button class="stop" onclick="act(\'/complete-course\',\'{e(cid)}\')">'
                    '✓ marcar curso como concluído</button>')

    if c.get("provider") == "coursera" and not c["lessons"]:
        body.append('<div class="muted" style="margin:.6rem 0">Curso externo (Coursera). '
                    'Marque como concluído quando terminar, ou cadastre as aulas/semanas abaixo.</div>')

    for l in c["lessons"]:
        st = prog["lessons"].get(f'{cid}/{l["id"]}', {})
        status = st.get("status", "todo")
        t = f'<span class="muted">{fmt(st.get("seconds",0))}</span>' if st.get("seconds") else ""
        body.append(
            f'<a class="lrow" href="/watch/{e(cid)}/{e(l["id"])}">'
            f'<span class="ic {status}">{ICON[status]}</span>'
            f'<span class="grow">{e(l["id"])} · {e(l["title"])}</span>{t}</a>'
        )
    if not c["lessons"]:  # só cursos externos (Coursera) precisam cadastrar aula na mão
        body.append(
            '<h2>cadastrar aula</h2>'
            '<form class="add" onsubmit="return submitForm(this,\'/new-lesson\')">'
            f'<input type="hidden" name="course" value="{e(cid)}">'
            '<input name="title" placeholder="título da aula" required>'
            '<input name="url" placeholder="url do vídeo (YouTube)">'
            '<button>adicionar aula</button></form>'
        )
    return page(c["title"], "".join(body))


def render_watch(cur, prog, cid, lid):
    c, l = get_lesson(cur, cid, lid)
    if not c:
        return None
    key = f"{cid}/{lid}"
    st = prog["lessons"].get(key, new_entry())
    status = st.get("status", "todo")
    course_url = f"/course/{e(cid)}"
    link_btn = (f'<a class="btn ghost" href="{e(l["url"])}" target="_blank" rel="noopener">🔗 abrir vídeo</a>'
                if l.get("url") else "")

    if status == "watching":
        base = int(sum(dur(s) for s in st["sessions"][:-1]))
        start = e(st["sessions"][-1]["start"])
        timer = f'<span class="timer" id="timer" data-base="{base}" data-start="{start}"></span>'
        controls = (f'<button class="warn" onclick="act(\'/pause\',\'{key}\')">⏸ Pausar</button>'
                    f'<button class="stop" onclick="terminar()">✓ Terminar aula</button>')
    elif status == "paused":
        timer = f'<span class="timer">⏸ {fmt(st.get("seconds",0))}</span>'
        controls = (f'<button onclick="act(\'/start\',\'{key}\')">▶ Retomar</button>'
                    f'<button class="stop" onclick="terminar()">✓ Terminar aula</button>')
    elif status == "watched":
        timer = f'<span class="timer">✓ {fmt(st.get("seconds",0))}</span>'
        controls = f'<button class="ghost" onclick="act(\'/start\',\'{key}\')">▶ assistir de novo</button>'
    else:  # todo (nao deveria cair aqui: GET /watch auto-inicia)
        timer = '<span class="timer">—</span>'
        controls = f'<button onclick="act(\'/start\',\'{key}\')">▶ Começar</button>'

    lock = ""
    if missing_prereqs(cur, prog, c) and not is_complete(cur, prog, cid):
        lock = '<div class="banner lock">🔒 curso com pré-requisitos pendentes</div>'

    body = (
        f'<div class="crumb"><a href="{course_url}">← {e(c["title"])}</a></div>'
        f'<h1>{e(l["id"])} · {e(l["title"])}</h1>{lock}'
        f'<div class="toolbar">{timer}{link_btn}{controls}</div>'
        f'<textarea id="notes" placeholder="Suas anotações...">{e(read_body(cid, lid))}</textarea>'
        f'<div><span class="saved" id="saved"></span></div>'
    )
    script = f"""<script>
var KEY="{key}", COURSE="{course_url}", HB={HEARTBEAT_MS};
var ta=document.getElementById('notes'), tmr;
function save(){{return post('/save-notes',{{id:KEY,body:ta.value}}).then(function(){{
  document.getElementById('saved').textContent='salvo ✓ '+new Date().toLocaleTimeString();}});}}
ta.addEventListener('input',function(){{clearTimeout(tmr);tmr=setTimeout(save,1500);}});
ta.addEventListener('blur',save);
function terminar(){{save().then(function(){{post('/done',{{id:KEY}}).then(function(){{location.href=COURSE;}});}});}}
var el=document.getElementById('timer');
if(el){{
  function p(n){{return String(n).padStart(2,'0');}}
  function tick(){{var d=(+el.dataset.base)+Math.floor((Date.now()-new Date(el.dataset.start))/1000);
    el.textContent='⏱ '+Math.floor(d/3600)+'h '+p(Math.floor(d%3600/60))+'m '+p(d%60)+'s';}}
  setInterval(tick,1000);tick();
  setInterval(function(){{post('/heartbeat',{{id:KEY}});}},HB);
}}
</script>"""
    return page(l["title"], body, script)


# ---- actions ------------------------------------------------------------

def do_action(action, f):
    cur, prog = load(CUR, {"courses": []}), load_prog()

    if action in ("/start", "/pause", "/done", "/heartbeat"):
        key = f.get("id", "")
        if key not in valid_keys(cur):
            raise ValueError("aula desconhecida")
        cid, lid = key.split("/")
        ent = entry(prog, key)
        if action == "/start":
            if ent["status"] != "watching":
                ent["sessions"].append({"start": now(), "end": now()})
                ent["status"] = "watching"
        elif action == "/heartbeat":
            if ent["status"] == "watching" and ent["sessions"]:
                ent["sessions"][-1]["end"] = now()
        elif action == "/pause":
            if ent["status"] == "watching" and ent["sessions"]:
                ent["sessions"][-1]["end"] = now()
                ent["status"] = "paused"
        elif action == "/done":
            if ent["status"] == "watching" and ent["sessions"]:
                ent["sessions"][-1]["end"] = now()
            ent["status"] = "watched"
        recompute(ent)
        ent["updated_at"] = now()
        save(PROG, prog)
        if action == "/done":  # materializa o .md com a tag final
            write_md(cid, lid, cur, prog, read_body(cid, lid))

    elif action == "/save-notes":
        key = f.get("id", "")
        if key not in valid_keys(cur):
            raise ValueError("aula desconhecida")
        cid, lid = key.split("/")
        write_md(cid, lid, cur, prog, f.get("body", ""))

    elif action == "/complete-course":
        cid = f.get("id", "")
        if not course_by_id(cur, cid):
            raise ValueError("curso desconhecido")
        cc = prog["courses"]
        if cc.get(cid, {}).get("completed"):
            cc.pop(cid, None)  # desfazer conclusão manual
        else:
            cc[cid] = {"completed": True, "completed_at": now()}
        save(PROG, prog)

    elif action == "/new-lesson":
        course = course_by_id(cur, f.get("course", ""))
        title = f.get("title", "").strip()
        if not course or not title:
            raise ValueError("curso e título obrigatórios")
        nums = [int(m.group()) for l in course["lessons"] if (m := re.fullmatch(r"\d+", l["id"]))]
        lid = f"{(max(nums) + 1) if nums else 1:03d}"
        course["lessons"].append({"id": lid, "title": title, "url": f.get("url", "").strip()})
        save(CUR, cur)
    else:
        raise ValueError("acao desconhecida")


# ---- http ---------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body=b""):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        cur, prog = load(CUR, {"courses": []}), load_prog()
        parts = [p for p in urlparse(self.path).path.split("/") if p]
        html_out = None
        if not parts:
            html_out = render_home(cur, prog)
        elif parts[0] == "course" and len(parts) == 2:
            html_out = render_course(cur, prog, parts[1])
        elif parts[0] == "watch" and len(parts) == 3:
            cid, lid = parts[1], parts[2]
            if f"{cid}/{lid}" in valid_keys(cur):
                ent = entry(prog, f"{cid}/{lid}")
                if ent["status"] == "todo":  # abrir aula nova = comecar a assistir
                    ent["sessions"].append({"start": now(), "end": now()})
                    ent["status"] = "watching"
                    recompute(ent); ent["updated_at"] = now(); save(PROG, prog)
                html_out = render_watch(cur, prog, cid, lid)
        if html_out is None:
            return self._send(404, b"nao encontrado")
        self._send(200, html_out.encode())

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        f = {k: v[0] for k, v in parse_qs(self.rfile.read(n).decode(), keep_blank_values=True).items()}
        action = urlparse(self.path).path
        try:
            do_action(action, f)
        except ValueError as ex:
            return self._send(400, str(ex).encode())
        self._send(204)  # o front recarrega sozinho via fetch

    def log_message(self, *a):
        pass


# ---- self-check ---------------------------------------------------------

def test():
    assert fmt(4500) == "1h 15m" and fmt(1800) == "30m" and fmt(45) == "45s"
    ent = {"status": "todo", "sessions": []}
    ent["sessions"].append({"start": "2026-01-01T10:00:00", "end": "2026-01-01T10:20:00"})
    ent["status"] = "watching"; recompute(ent)
    assert ent["seconds"] == 1200
    ent["sessions"].append({"start": "2026-01-01T11:00:00", "end": "2026-01-01T11:10:00"})
    ent["status"] = "watched"; recompute(ent)
    assert ent["seconds"] == 1800
    assert times(ent) == ("2026-01-01T10:00:00", "2026-01-01T11:10:00")
    assert dur({"start": "2026-01-01T10:00:00", "end": "2026-01-01T09:00:00"}) == 0

    # conclusão + pré-requisitos (soft-lock)
    cur = {"courses": [
        {"id": "geo", "title": "Geo", "stage": 1, "prereqs": [],
         "lessons": [{"id": "001", "title": "a"}, {"id": "002", "title": "b"}]},
        {"id": "calc", "title": "Cálculo", "stage": 2, "prereqs": ["geo"], "lessons": []},
        {"id": "poo", "title": "POO", "stage": 2, "prereqs": [], "lessons": []},  # coursera, sem aulas
    ]}
    prog = {"lessons": {"geo/001": {"status": "watched"}}, "courses": {}}
    assert not is_complete(cur, prog, "geo")           # falta 002
    assert missing_prereqs(cur, prog, course_by_id(cur, "calc")) == ["geo"]
    prog["lessons"]["geo/002"] = {"status": "watched"}
    assert is_complete(cur, prog, "geo")               # todas assistidas -> auto
    assert missing_prereqs(cur, prog, course_by_id(cur, "calc")) == []  # destravou
    assert not is_complete(cur, prog, "poo")           # sem aulas, sem manual
    prog["courses"]["poo"] = {"completed": True}
    assert is_complete(cur, prog, "poo")               # manual
    print("ok")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test()
    else:
        try:
            srv = HTTPServer(("127.0.0.1", 8765), Handler)
        except OSError as ex:
            sys.exit(f"⚠ porta 8765 ocupada ({ex.strerror}). Já tem um servidor rodando?\n"
                     f"  Feche o antigo com:  fuser -k 8765/tcp")
        print("→ http://127.0.0.1:8765  (Ctrl+C para sair)")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\naté mais 👋")
