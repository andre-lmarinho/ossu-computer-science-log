# OSSU-br — Log de Aulas

Um painel local para **acompanhar, registrar e cronometrar** a grade de Ciência da
Computação do [OSSU-br / Universidade Livre](https://github.com/ossu/computer-science-br).

A grade completa (**35 cursos obrigatórios em 7 etapas + 4 eletivas**, com o DAG de
pré-requisitos) já vem pronta e o progresso começa zerado. Você escolhe a aula, abre o
**modo foco** (timer + notas), e ao terminar o app grava suas anotações num `.md` com a
tag completa da aula — notas + horários + link.

## Como rodar

Precisa só de **Python 3.8+** (nada além da biblioteca padrão):

```bash
python3 serve.py     # abre http://127.0.0.1:8765  (Ctrl+C para sair)
```

> Se aparecer "porta 8765 ocupada", já tem um servidor rodando — feche com `fuser -k 8765/tcp`.

O servidor normal não tem dependências. Só **reconstruir a grade** (`seed.py`) precisa
do [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) (`pip install --user yt-dlp`).

O repositório vem como um template limpo: `progress.json` não tem aulas assistidas e
`courses/` começa sem registros de aula. Os arquivos de anotação são criados conforme
você assiste e conclui aulas.

## O fluxo

```
Home (a grade)              Curso                       Assistindo (modo foco)
┌────────────────────┐      ┌────────────────────┐      ┌──────────────────────────┐
│ 1ª Etapa           │      │ Cálculo I  YouTube │      │ ⏱ 0h 12m 04s [🔗][⏸][✓]  │
│  Circuitos ▓▓░ ✓   │ ──▶  │ 🔒 requer: Geo…    │ ──▶  │ ─────────────────────────│
│  Cálculo I 🔒 requer│      │ ○ 001 · Aula 1     │      │  Suas anotações...        │
│  …                 │      │ ▶ 002 · Aula 2     │      │  ______________________   │
│ Eletivas           │      │ [✓ marcar concluído]│     │        [✓ Terminar aula]  │
└────────────────────┘      └────────────────────┘      └──────────────────────────┘
```

- **Home** (`/`) — a grade agrupada por `1ª…7ª Etapa` (as eletivas ficam junto da sua
  etapa), com `X/35 obrigatórios concluídos`. Cada curso mostra progresso, um badge do
  provider (YouTube/Coursera), um badge **Obrigatória/Eletiva** e **continuar** (pula
  pra próxima aula não assistida).
- **Curso** (`/course/<id>`) — banner de pré-requisitos, `🔗 fonte`, botão **marcar como
  concluído**, e a lista de aulas com ícone de status
  (○ a assistir · ▶ assistindo · ⏸ pausado · ✓ concluída).
- **Assistindo** (`/watch/<id>/<aula>`) — abrir uma aula nova já **começa a cronometrar**.
  Botão pra abrir o vídeo, notas com **autosave**, e **Terminar** que finaliza o tempo e
  grava o `.md`.

### Pré-requisitos (soft-lock)

Concluir um curso libera os que dependem dele — ex.: concluir *Geometria Analítica*
destrava *Cálculo I* e *Álgebra Linear I*. Um curso conta como **concluído** quando
**todas as aulas são assistidas** (automático) **ou** pelo botão **marcar como
concluído** (necessário pros cursos da Coursera, que não têm aulas importáveis).
O bloqueio é **visual**: um curso travado mostra 🔒 e o que falta, mas ainda pode ser
aberto e assistido.

### Tempo automático

Enquanto uma aula está sendo assistida, o navegador manda um *heartbeat* a cada 15s que
persiste a sessão. Se você fechar a aba ou esquecer de parar, o tempo gravado é o **real**
(com até ~15s de folga), não o relógio de parede. Pausar/retomar acumula em sessões.

## Estrutura dos dados

Sem banco de dados: tudo em arquivos de texto versionáveis.

| Arquivo | Papel |
|---|---|
| [`curriculum.json`](curriculum.json) | **Grade** — cursos com etapa, provider, categoria, pré-requisitos e aulas. |
| [`progress.json`](progress.json) | **Rastreio** — `{lessons: {...}, courses: {...}}`: status/sessões por aula + conclusões manuais. |
| `courses/<curso>/<aula>.md` | **Registro da aula** — criado automaticamente com tag (frontmatter) + suas anotações. |
| [`serve.py`](serve.py) | O app inteiro: servidor `http.server` da stdlib. |
| [`seed.py`](seed.py) | Monta a grade em `curriculum.json` e importa as playlists (roda uma vez). |

Um curso no `curriculum.json`:

```jsonc
{
  "id": "calculo-i", "title": "Cálculo I", "stage": 2,
  "provider": "youtube", "category": "obrigatoria",
  "prereqs": ["geometria-analitica"],
  "source_url": "https://www.youtube.com/watch?v=...",
  "playlist_url": "https://www.youtube.com/playlist?list=...",
  "lessons": [ { "id": "001", "title": "...", "url": "...", "duration_seconds": 1012 } ]
}
```

Cada `.md` é auto-contido — a tag completa da aula mais as notas:

```markdown
---
course: "Circuitos Digitais"
lesson: "[CIRCUITOS DIGITAIS] Aula 01 - Introdução aos Circuitos Digitais"
source_url: "https://www.youtube.com/watch?v=...&list=...&index=1"
started_at: "2026-01-01T10:00:00-03:00"
finished_at: "2026-01-01T10:20:00-03:00"
seconds: 1200
status: "watched"
---

# Aula 01 - Introdução aos Circuitos Digitais

## Conceitos principais
- ...
```

## Reconstruir a grade

O `seed.py` (re)monta `curriculum.json` a partir da definição da grade. Ele **preserva
as aulas de cursos que você já começou** (ids/ordem congelados) e **nunca apaga
progresso**; só reimporta as playlists dos cursos ainda não iniciados.

```bash
python3 seed.py
```

## Testes

Um self-check embutido (parsing de tempo, sessões, slug, pré-requisitos/conclusão):

```bash
python3 serve.py test
```
