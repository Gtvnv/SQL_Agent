"""Cria o Banco_Exemplo (SQLite, domínio de loja) de forma idempotente e atômica.

Uso: python db/create_db.py [caminho_do_banco]

O banco é montado em um arquivo temporário, dentro de uma única transação, e só
substitui o arquivo final (os.replace) quando tudo deu certo. Em falha, o arquivo
temporário é removido, o arquivo final fica intacto e o processo sai com código 1.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

CAMINHO_PADRAO = Path(__file__).resolve().parent / "loja.sqlite"

DDL = """
CREATE TABLE categorias (
    id   INTEGER PRIMARY KEY,
    nome TEXT NOT NULL
);
CREATE TABLE produtos (
    id           INTEGER PRIMARY KEY,
    nome         TEXT NOT NULL,
    preco        REAL NOT NULL,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id)
);
CREATE TABLE clientes (
    id            INTEGER PRIMARY KEY,
    nome          TEXT NOT NULL,
    cidade        TEXT NOT NULL,
    data_cadastro TEXT NOT NULL
);
CREATE TABLE funcionarios (
    id    INTEGER PRIMARY KEY,
    nome  TEXT NOT NULL,
    cargo TEXT NOT NULL
);
CREATE TABLE pedidos (
    id             INTEGER PRIMARY KEY,
    cliente_id     INTEGER NOT NULL REFERENCES clientes(id),
    funcionario_id INTEGER NOT NULL REFERENCES funcionarios(id),
    data_pedido    TEXT NOT NULL,
    status         TEXT NOT NULL
);
CREATE TABLE itens_pedido (
    id             INTEGER PRIMARY KEY,
    pedido_id      INTEGER NOT NULL REFERENCES pedidos(id),
    produto_id     INTEGER NOT NULL REFERENCES produtos(id),
    quantidade     INTEGER NOT NULL,
    preco_unitario REAL NOT NULL
);
"""

CATEGORIAS = [
    "Eletrônicos", "Informática", "Móveis", "Livros", "Papelaria",
    "Esportes", "Brinquedos", "Cozinha", "Beleza", "Ferramentas",
]

# (nome, preço, categoria_id)
PRODUTOS = [
    ("Smartphone X", 1899.90, 1), ("Fone Bluetooth", 249.90, 1),
    ("Notebook Pro", 4599.00, 2), ("Mouse Sem Fio", 79.90, 2),
    ("Teclado Mecânico", 329.00, 2), ("Cadeira Ergonômica", 1290.00, 3),
    ("Mesa de Escritório", 780.50, 3), ("Romance Clássico", 54.90, 4),
    ("Livro de Python", 119.90, 4), ("Caderno Universitário", 22.50, 5),
    ("Caneta Esferográfica", 3.50, 5), ("Bola de Futebol", 89.90, 6),
    ("Tênis de Corrida", 359.90, 6), ("Quebra-Cabeça 1000 peças", 64.00, 7),
    ("Boneca Articulada", 99.90, 7), ("Jogo de Panelas", 459.00, 8),
    ("Liquidificador", 189.90, 8), ("Perfume Floral", 215.00, 9),
    ("Furadeira", 299.90, 10), ("Jogo de Chaves", 74.90, 10),
]

# (nome, cidade, data_cadastro)
CLIENTES = [
    ("Ana Souza", "São Paulo", "2022-01-15"), ("Bruno Lima", "Rio de Janeiro", "2022-02-03"),
    ("Carla Dias", "São Paulo", "2022-03-21"), ("Daniel Alves", "Curitiba", "2022-05-10"),
    ("Elisa Ramos", "Belo Horizonte", "2022-06-18"), ("Felipe Costa", "Curitiba", "2022-08-02"),
    ("Giovana Reis", "Porto Alegre", "2022-09-27"), ("Hugo Martins", "São Paulo", "2022-11-05"),
    ("Isabela Nunes", "Rio de Janeiro", "2023-01-12"), ("João Pereira", "Salvador", "2023-02-24"),
    ("Karina Melo", "Belo Horizonte", "2023-04-09"), ("Lucas Barros", "Curitiba", "2023-06-30"),
    ("Marina Teixeira", "São Paulo", "2023-08-14"), ("Nelson Cardoso", "Recife", "2023-10-01"),
    ("Olívia Freitas", "Porto Alegre", "2023-12-19"),
]

# (nome, cargo)
FUNCIONARIOS = [
    ("Paulo Mendes", "Vendedor"), ("Quitéria Santos", "Vendedor"),
    ("Rafael Moreira", "Gerente"), ("Sofia Andrade", "Vendedor"),
    ("Tiago Ribeiro", "Atendente"), ("Úrsula Campos", "Vendedor"),
    ("Valter Duarte", "Atendente"), ("Wanda Pires", "Supervisor"),
    ("Xavier Lopes", "Vendedor"), ("Yara Fonseca", "Atendente"),
]

STATUS = ["entregue", "entregue", "enviado", "pendente", "cancelado", "entregue"]


def gerar_pedidos() -> list[tuple]:
    """30 pedidos determinísticos: (cliente_id, funcionario_id, data, status)."""
    pedidos = []
    for i in range(30):
        mes = i % 12 + 1
        dia = (i * 3) % 28 + 1
        ano = 2023 + (i // 12)
        pedidos.append((
            i % len(CLIENTES) + 1,
            (i * 7) % len(FUNCIONARIOS) + 1,
            f"{ano:04d}-{mes:02d}-{dia:02d}",
            STATUS[i % len(STATUS)],
        ))
    return pedidos


def gerar_itens() -> list[tuple]:
    """Cerca de 60 itens determinísticos: (pedido_id, produto_id, qtd, preço)."""
    itens = []
    for pedido_id in range(1, 31):
        for k in range(1 + pedido_id % 3):
            produto_id = (pedido_id * 3 + k * 5) % len(PRODUTOS) + 1
            preco = PRODUTOS[produto_id - 1][1]
            itens.append((pedido_id, produto_id, 1 + (pedido_id + k) % 4, preco))
    return itens


def criar_esquema(conn: sqlite3.Connection) -> None:
    for comando in DDL.split(";"):
        if comando.strip():
            conn.execute(comando)


def popular(conn: sqlite3.Connection) -> None:
    conn.executemany("INSERT INTO categorias (nome) VALUES (?)", [(n,) for n in CATEGORIAS])
    conn.executemany(
        "INSERT INTO produtos (nome, preco, categoria_id) VALUES (?, ?, ?)", PRODUTOS)
    conn.executemany(
        "INSERT INTO clientes (nome, cidade, data_cadastro) VALUES (?, ?, ?)", CLIENTES)
    conn.executemany("INSERT INTO funcionarios (nome, cargo) VALUES (?, ?)", FUNCIONARIOS)
    conn.executemany(
        "INSERT INTO pedidos (cliente_id, funcionario_id, data_pedido, status) "
        "VALUES (?, ?, ?, ?)", gerar_pedidos())
    conn.executemany(
        "INSERT INTO itens_pedido (pedido_id, produto_id, quantidade, preco_unitario) "
        "VALUES (?, ?, ?, ?)", gerar_itens())


def verificar(conn: sqlite3.Connection) -> None:
    violacoes = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violacoes:
        raise sqlite3.IntegrityError(f"violações de chave estrangeira: {violacoes[:3]}")


def criar_banco(destino: Path) -> None:
    """Cria o banco em `destino`. Levanta RuntimeError("<passo>: <motivo>") em falha."""
    destino = Path(destino)
    passo = "preparar diretório"
    temporario = destino.with_name(destino.name + ".tmp")
    conn: sqlite3.Connection | None = None
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        passo = "remover arquivo temporário antigo"
        temporario.unlink(missing_ok=True)

        passo = "abrir arquivo temporário"
        conn = sqlite3.connect(temporario, isolation_level=None)
        conn.execute("PRAGMA foreign_keys = ON")

        conn.execute("BEGIN")
        passo = "criar tabelas"
        criar_esquema(conn)
        passo = "popular tabelas"
        popular(conn)
        passo = "verificar chaves estrangeiras"
        verificar(conn)
        passo = "confirmar transação"
        conn.execute("COMMIT")
        conn.close()
        conn = None

        passo = "substituir arquivo final"
        os.replace(temporario, destino)
    except Exception as exc:
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        try:
            temporario.unlink(missing_ok=True)
        except OSError:
            pass
        raise RuntimeError(f"{passo}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    destino = Path(args[0]) if args else CAMINHO_PADRAO
    try:
        criar_banco(destino)
    except RuntimeError as exc:
        print(f"Falha ao criar o banco de exemplo no passo '{exc}'", file=sys.stderr)
        return 1
    print(f"Banco de exemplo criado em {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
