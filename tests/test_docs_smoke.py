"""Testes de fumaça da documentação do repositório.

Requirements: 8.3, 11.1, 11.2, 11.3, 11.7, 11.8
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
README = RAIZ / "README.md"
DOCS = RAIZ / "docs"

# Seção do README -> trecho (sem acento, minúsculo) esperado no título.
SECOES_README = {
    "descrição do problema": "descricao do problema",
    "objetivos": "objetivos",
    "arquitetura": "arquitetura",
    "tecnologias": "tecnologias",
    "pré-requisitos": "pre-requisitos",
    "instalação": "instalacao",
    "execução": "execucao",
    "exemplos de uso": "exemplos de uso",
    "limitações": "limitacoes",
}

# Tema -> (arquivo em /docs, trecho esperado no conteúdo)
TEMAS_DOCS = {
    "arquitetura": "arquitetura.md",
    "fluxo": "fluxo-do-agente.md",
    "engenharia de prompt": "engenharia-de-prompt.md",
    "esquema do banco": "esquema-do-banco.md",
    "decisões de segurança": "decisoes-de-seguranca.md",
}

REGEX_IMAGEM = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _norm(texto: str) -> str:
    sem = unicodedata.normalize("NFD", texto)
    return "".join(c for c in sem if unicodedata.category(c) != "Mn").lower()


def _secoes(markdown: str) -> dict[str, str]:
    """Mapeia título normalizado (## ...) para o corpo da seção, ignorando código."""
    secoes: dict[str, list[str]] = {}
    atual: str | None = None
    em_codigo = False
    for linha in markdown.splitlines():
        if linha.lstrip().startswith("```"):
            em_codigo = not em_codigo
        if not em_codigo:
            m = re.match(r"^##\s+(.+?)\s*$", linha)
            if m:
                atual = _norm(m.group(1))
                secoes[atual] = []
                continue
        if atual is not None:
            secoes[atual].append(linha)
    return {k: "\n".join(v).strip() for k, v in secoes.items()}


def _ler(caminho: Path) -> str:
    assert caminho.is_file(), f"arquivo ausente: {caminho}"
    return caminho.read_text(encoding="utf-8")


def test_readme_tem_as_nove_secoes_nao_vazias() -> None:
    secoes = _secoes(_ler(README))
    for nome, trecho in SECOES_README.items():
        titulos = [t for t in secoes if trecho in t]
        assert titulos, f"seção ausente no README: {nome}"
        assert any(secoes[t] for t in titulos), f"seção vazia no README: {nome}"


@pytest.mark.parametrize("tema,arquivo", TEMAS_DOCS.items())
def test_docs_cobrem_cada_tema(tema: str, arquivo: str) -> None:
    conteudo = _ler(DOCS / arquivo)
    assert len(conteudo.strip()) > 0, f"documento vazio para o tema: {tema}"


def test_doc_arquitetura_tem_diagrama() -> None:
    conteudo = _ler(DOCS / "arquitetura.md")
    blocos = re.findall(r"```(\w*)\n(.*?)```", conteudo, flags=re.DOTALL)
    tem_diagrama = any(
        lang == "mermaid" or ("->" in corpo or "-->" in corpo or "+--" in corpo)
        for lang, corpo in blocos
    )
    assert tem_diagrama, "docs/arquitetura.md não contém diagrama"


def test_license_tem_ano_e_titular() -> None:
    conteudo = _ler(RAIZ / "LICENSE")
    m = re.search(r"Copyright\s*(?:\(c\)|©)?\s*(\d{4})\s+(\S.*)", conteudo)
    assert m, "LICENSE sem linha de copyright com ano e titular"
    assert m.group(2).strip(), "LICENSE sem titular"


def _variaveis_lidas_por_config() -> set[str]:
    codigo = (RAIZ / "sql_agent" / "config.py").read_text(encoding="utf-8")
    lidas = set(re.findall(r'_valor\(\s*"([A-Z][A-Z0-9_]*)"', codigo))
    lidas |= set(re.findall(r'^\s*"([A-Z][A-Z0-9_]*)":\s*\(', codigo, flags=re.M))
    return lidas


def test_env_example_lista_todas_as_variaveis_do_config() -> None:
    lidas = _variaveis_lidas_por_config()
    assert {"LLM_API_KEY", "LLM_MODEL"} <= lidas
    exemplo = _ler(RAIZ / ".env.example")
    declaradas = set(re.findall(r"^\s*([A-Z][A-Z0-9_]*)\s*=", exemplo, flags=re.M))
    faltando = lidas - declaradas
    assert not faltando, f".env.example sem variáveis: {sorted(faltando)}"


def test_gitignore_ignora_env() -> None:
    linhas = [
        l.strip() for l in _ler(RAIZ / ".gitignore").splitlines() if l.strip()
    ]
    assert ".env" in linhas or "/.env" in linhas


def test_readme_tem_ao_menos_cinco_exemplos() -> None:
    secoes = _secoes(_ler(README))
    # Os exemplos são subseções (###); precisamos do texto bruto da seção.
    texto = _ler(README)
    inicio = texto.index("## Exemplos de uso")
    resto = texto[inicio + 1 :]
    fim = re.search(r"^## ", resto, flags=re.M)
    corpo = resto[: fim.start()] if fim else resto
    assert secoes  # sanidade do parser
    exemplos = re.findall(r"^### .*$", corpo, flags=re.M)
    com_sql = len(re.findall(r"```sql", corpo))
    com_pergunta = len(re.findall(r"\*\*Pergunta:\*\*", corpo))
    assert len(exemplos) >= 5
    assert com_sql >= 5
    assert com_pergunta >= 5


def test_imagens_referenciadas_existem() -> None:
    """Falha até as capturas de tela (passo manual) serem adicionadas a /images."""
    ausentes: list[str] = []
    documentos = [README, *sorted(DOCS.glob("*.md"))]
    for doc in documentos:
        for ref in REGEX_IMAGEM.findall(doc.read_text(encoding="utf-8")):
            if re.match(r"^[a-z]+://", ref):
                continue
            alvo = (doc.parent / ref.split("#")[0]).resolve()
            if not alvo.is_file():
                ausentes.append(f"{doc.name}: {ref}")
    assert not ausentes, f"imagens referenciadas inexistentes: {ausentes}"
