#!/usr/bin/env python3
"""Monta a grade OSSU-br em curriculum.json (35 obrigatórias + 4 eletivas, 7 etapas,
pré-requisitos) e migra progress.json para {lessons, courses}. Roda uma vez.

    python3 seed.py

Preserva aulas de cursos já iniciados (ids/ordem congelados) e nunca apaga progresso.
Importa as playlists do YouTube via serve.fetch_playlist (requer yt-dlp).
"""
import json
import urllib.parse as up
import serve

# Obrigatórias — (id, título, etapa, provider, source_url, [pré-requisitos])
GRADE = [
    # Etapa 1
    ("circuitos-digitais", "Circuitos Digitais", 1, "youtube",
     "https://www.youtube.com/playlist?list=PLXyWBo_coJnMYO9Na3t-oYsc2X4kPJBWf", []),
    ("matematica-discreta", "Matemática Discreta", 1, "youtube",
     "https://www.youtube.com/watch?v=KGoSTh1sgyM&list=PL6mfjjCaO1WrEJ0JKRyXO3QjaPkJaSvAS", []),
    ("linguagens-de-programacao", "Linguagens de Programação", 1, "youtube",
     "https://www.youtube.com/watch?v=xfDdxqbkiSQ&list=PLnzT8EWpmbka4KukGR184tifzqcuq_ZDv", []),
    ("intro-cc-python-i", "Introdução à Ciência da Computação com Python I", 1, "coursera",
     "https://www.coursera.org/learn/ciencia-computacao-python-conceitos", []),
    ("geometria-analitica", "Geometria Analítica", 1, "youtube",
     "https://www.youtube.com/watch?v=ijkDjQT7UPM&list=PL82Svt6JAgOH3M6TCELx8oegTVCriUg3L", []),
    # Etapa 2
    ("calculo-i", "Cálculo I", 2, "youtube",
     "https://www.youtube.com/watch?v=WgHUHPlJETs&list=PLAudUnJeNg4tr-aiNyYCXE46L3qEZ2Nzx",
     ["geometria-analitica"]),
    ("algebra-linear-i", "Álgebra Linear I", 2, "youtube",
     "https://www.youtube.com/playlist?list=PLIEzh1OveCVczEZAjhVIVd7Qs-X8ILgnI",
     ["geometria-analitica"]),
    ("estruturas-de-dados", "Estruturas de Dados", 2, "youtube",
     "https://www.youtube.com/watch?v=0hT3EKGhbpI&list=PLndfcZyvAqbofQl2kLLdeWWjCcPlOPnrW",
     ["matematica-discreta", "intro-cc-python-i"]),
    ("intro-cc-python-ii", "Introdução à Ciência da Computação com Python II", 2, "coursera",
     "https://www.coursera.org/learn/ciencia-computacao-python-conceitos-2",
     ["intro-cc-python-i"]),
    ("lab-poo-i", "Laboratório de Programação Orientada a Objetos I", 2, "coursera",
     "https://pt.coursera.org/learn/lab-poo-parte-1", ["intro-cc-python-i"]),
    # Etapa 3
    ("algoritmos-em-grafos", "Algoritmos em Grafos", 3, "youtube",
     "https://www.youtube.com/watch?v=fjOiu6CD5pc&list=PLrPn-zKAOzUzKdPqFNF52g-i9p1f-vmsk",
     ["estruturas-de-dados"]),
    ("arquitetura-de-computadores-i", "Arquitetura de Computadores I", 3, "youtube",
     "https://www.youtube.com/playlist?list=PLEUHFTHcrJmswfeq7QEHskgkT6HER3gK6",
     ["circuitos-digitais"]),
    ("probabilidade-e-estatistica", "Probabilidade e Estatística", 3, "youtube",
     "https://www.youtube.com/watch?v=snXf8YT7L3U&list=PLrOyM49ctTx8HWnxWRBtKrfcuf7ew_3nm",
     ["calculo-i"]),
    ("calculo-ii", "Cálculo II", 3, "youtube",
     "https://www.youtube.com/watch?v=lQdzRBRL9Tw&list=PLAudUnJeNg4sd0TEJ9EG6hr-3d3jqrddN",
     ["calculo-i"]),
    ("programacao-funcional-haskell", "Programação Funcional em Haskell", 3, "youtube",
     "https://www.youtube.com/watch?v=eTisiy5FB7k&list=PLYItvall0TqJ25sVTLcMhxsE0Hci58mpQ&index=1", []),
    # Etapa 4
    ("analise-de-algoritmos", "Análise de Algoritmos", 4, "youtube",
     "https://www.youtube.com/watch?v=_HBTCUNPxOg&list=PLncEdvQ20-mgGanwuFczm-4IwIdIcIiha",
     ["algoritmos-em-grafos"]),
    ("metodos-numericos-i", "Métodos Numéricos I", 4, "youtube",
     "https://www.youtube.com/watch?v=a6nNQ6qKgiY&list=PLI9WiBCz67cPTTRER4CrsN0wpRN-NmjGA",
     ["intro-cc-python-i", "calculo-i"]),
    ("banco-de-dados", "Banco de Dados", 4, "youtube",
     "https://www.youtube.com/watch?v=pmAxIs5U1KI&list=PLxI8Can9yAHeHQr2McJ01e-ANyh3K0Lfq", []),
    ("arquitetura-de-computadores-ii", "Arquitetura de Computadores II", 4, "youtube",
     "https://www.youtube.com/playlist?list=PLEUHFTHcrJmsqKX-GDD-hBvkF8h2_BfKJ",
     ["intro-cc-python-ii", "arquitetura-de-computadores-i"]),
    ("programacao-logica", "Programação Lógica", 4, "youtube",
     "https://youtube.com/playlist?list=PLZ-Bk6jzsb-OScKa7vhpcQXoU2uxYGaFx", []),
    # Etapa 5
    ("redes-de-computadores", "Redes de Computadores", 5, "youtube",
     "https://www.youtube.com/playlist?list=PLvHXLbw-JSPfKp65psX5C9tyNLHHC4uoR", []),
    ("intro-engenharia-de-software", "Introdução à Engenharia de Software", 5, "youtube",
     "https://www.youtube.com/watch?v=h_hEI1Kfm2U&list=PLhBaeEzs3d7lsn_Mq2n3R4_api16Wkp1Q",
     ["intro-cc-python-ii"]),
    ("sistemas-operacionais", "Sistemas Operacionais", 5, "youtube",
     "https://www.youtube.com/watch?v=EGn8fOf7zE0&list=PLSmh8AKk_aUn9HxFs5FnjQupdQnV56MXV",
     ["arquitetura-de-computadores-ii"]),
    ("programacao-matematica", "Programação Matemática", 5, "youtube",
     "https://www.youtube.com/watch?v=8rrgnFCL9LM&list=PL2peXovwG2kuqXC6sECjFSiG-MT1yXMQ-",
     ["algebra-linear-i"]),
    ("fundamentos-de-computacao-grafica", "Fundamentos de Computação Gráfica", 5, "youtube",
     "https://www.youtube.com/watch?v=AVSAesOiKYY&list=PLE51fUFkeIwLXwe4rvG4EMgw7zgjP-tDx",
     ["geometria-analitica"]),
    # Etapa 6
    ("linguagens-formais-e-automatos", "Linguagens Formais e Autômatos", 6, "youtube",
     "https://www.youtube.com/watch?v=4zMwOozUt9U&list=PLncEdvQ20-mhD_qMeLHtLnA3XDT1Fr_k4",
     ["matematica-discreta"]),
    ("inteligencia-artificial", "Inteligência Artificial", 6, "youtube",
     "https://www.youtube.com/watch?v=-T3zDFxngf4&list=PLeejGOroKw_txh7j7S3etF5eudI2WvMx0",
     ["estruturas-de-dados", "probabilidade-e-estatistica"]),
    ("sistemas-distribuidos", "Sistemas Distribuídos", 6, "youtube",
     "https://www.youtube.com/watch?v=TEEy5f46h_Q&list=PLP0bYj2MTFcuXa4-EbBKhvehr-rkxpeR8&index=1",
     ["redes-de-computadores"]),
    ("teoria-dos-grafos", "Teoria dos Grafos", 6, "youtube",
     "https://www.youtube.com/watch?v=kfHqZLYHfHU&list=PLndfcZyvAqbr2MLCOLEvBNX6FgD8UNWfX",
     ["matematica-discreta"]),
    ("calculo-iii", "Cálculo III", 6, "youtube",
     "https://www.youtube.com/watch?v=8mBTfk7s63s&list=PLAudUnJeNg4ugGUJo52dtgFZ_tCm1Ds5W",
     ["calculo-ii"]),
    # Etapa 7
    ("teoria-da-computacao", "Teoria da Computação", 7, "youtube",
     "https://www.youtube.com/watch?v=dWRxL30aoes&list=PLYLYA7XrlskNgCeSpJf9PQHHb8Z4WpRm4",
     ["linguagens-formais-e-automatos"]),
    ("deep-learning", "Deep Learning", 7, "youtube",
     "https://www.youtube.com/watch?v=0VD_2t6EdS4&list=PL9At2PVRU0ZqVArhU9QMyI3jSe113_m2-",
     ["inteligencia-artificial"]),
    ("compiladores", "Compiladores", 7, "youtube",
     "https://youtube.com/playlist?list=PLX6Nyaq0ebfhI396WlWN6WlBm-tp7vDtV",
     ["estruturas-de-dados", "teoria-dos-grafos"]),
    ("computacao-quantica", "Computação Quântica", 7, "youtube",
     "https://youtube.com/playlist?list=PLUFcRbu9t-v4peHdmDy4rtG3EnbZNS86R",
     ["calculo-iii", "arquitetura-de-computadores-ii"]),
    ("metodologia-da-pesquisa", "Metodologia da Pesquisa", 7, "youtube",
     "https://youtube.com/playlist?list=PLclUQno6PMpQO0-XrDwWsPzRzEvjwp1__", []),
]

# Eletivas — vão junto da sua etapa. (id, título, etapa, source_url, [pré-requisitos])
ELECTIVES = [
    ("algoritmos-aproximativos", "Algoritmos Aproximativos", 5,
     "https://www.youtube.com/watch?v=Owm_idXvw2I&list=PL6mfjjCaO1Wq3sLEGtMWCOAN6n9xIBOu8",
     ["analise-de-algoritmos"]),
    ("algoritmos-probabilisticos", "Algoritmos Probabilísticos", 5,
     "https://www.youtube.com/watch?v=-8BsuBl4vOE&list=PL6mfjjCaO1WpMf4T3AUVzzqkRIhmEemTB",
     ["analise-de-algoritmos"]),
    ("visao-computacional", "Visão Computacional", 6,
     "https://www.youtube.com/playlist?list=PLmDIGfkfgKy1SBjXA0kBk4DAhIaN1vQOS",
     ["fundamentos-de-computacao-grafica"]),
    ("processamento-de-imagens", "Processamento de Imagens", 6,
     "https://www.youtube.com/watch?v=Bd0PCypQ44s&list=PLo4jXE-LdDTRaFa39TdNN3FgPAKkcuHvj&index=1",
     ["calculo-ii", "algebra-linear-i", "analise-de-algoritmos", "fundamentos-de-computacao-grafica"]),
]


def playlist_url(u):
    lst = up.parse_qs(up.urlparse(u).query).get("list", [None])[0]
    return f"https://www.youtube.com/playlist?list={lst}" if lst else None


def main():
    old = serve.load(serve.CUR, {"courses": []})
    existing = {c["id"]: c.get("lessons", []) for c in old.get("courses", [])}
    prog = serve.load_prog()
    # "iniciado" = tem qualquer progresso de aula -> preserva as aulas (ordem/ids congelados)
    started = {cid for cid in existing if any(k.startswith(cid + "/") for k in prog["lessons"])}

    # (id, título, etapa, provider, src, prereqs, category)
    entries = [(cid, t, st, pv, s, pr, "obrigatoria") for cid, t, st, pv, s, pr in GRADE]
    entries += [(cid, t, st, "youtube", s, pr, "eletiva") for cid, t, st, s, pr in ELECTIVES]

    courses, fails = [], []
    for cid, title, stage, provider, src, prereqs, category in entries:
        pl = playlist_url(src) if provider == "youtube" else None
        if cid in started:                       # já assistiu algo -> não mexe nas aulas
            lessons, tag = existing.get(cid, []), "[preservado]"
        elif provider != "youtube":              # coursera -> sem aulas importáveis
            lessons, tag = [], "[externo]"
        else:                                    # importa (yt-dlp se houver, senão scraper)
            tag = ""
            try:
                lessons = [{"id": f"{i:03d}", "title": t,
                            "url": f"https://www.youtube.com/watch?v={vid}",
                            "duration_seconds": secs}
                           for i, (vid, t, secs) in enumerate(serve.fetch_playlist(pl), 1)]
                if not lessons:
                    fails.append((cid, "0 vídeos"))
            except Exception as ex:
                lessons = []
                fails.append((cid, str(ex)))
        courses.append({"id": cid, "title": title, "stage": stage, "provider": provider,
                        "category": category, "source_url": src, "playlist_url": pl,
                        "prereqs": prereqs, "lessons": lessons})
        print(f"  et.{stage} {'elet' if category == 'eletiva' else '    '} "
              f"{cid:34} {len(lessons):3} aulas  {tag}")

    serve.save(serve.CUR, {"courses": courses})
    serve.save(serve.PROG, prog)  # já normalizado por load_prog()

    print(f"\n{len(courses)} cursos gravados ({len(ELECTIVES)} eletivas).")
    if fails:
        print("falhas de importação (reimporte sob demanda depois):")
        for cid, why in fails:
            print(f"  - {cid}: {why}")


if __name__ == "__main__":
    main()
