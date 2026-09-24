"""
Chapéu Seletor Serverless — AWS Lambda (Python).

Recebe uma requisição HTTP POST em /v1/selecionar com o nome de um aluno e
retorna, em JSON, a casa de Hogwarts para a qual ele foi selecionado.

Handler: lambda_function.lambda_handler
"""

from __future__ import annotations

import base64
import json
import random

# Casas de Hogwarts disponíveis para seleção.
CASAS = ["Grifinória", "Sonserina", "Corvinal", "Lufa-Lufa"]

# Caminho (rota) em que a API responde. A Function URL não roteia por path,
# então a verificação é feita aqui dentro do handler.
ROTA = "/v1/selecionar"

# Método HTTP aceito nessa rota.
METODO = "POST"


def selecionar_casa(nome: str) -> str:
    """Seleciona uma casa aleatoriamente entre as quatro de Hogwarts.

    Cada requisição faz um novo sorteio, então o mesmo aluno pode cair
    em casas diferentes a cada chamada — como se o Chapéu Seletor
    decidisse na hora.
    """
    return random.choice(CASAS)


def _metodo_http(event: dict) -> str | None:
    """Extrai o método HTTP dos dois formatos de evento (Function URL / API GW)."""
    ctx = event.get("requestContext", {})
    metodo = ctx.get("http", {}).get("method")  # payload v2.0 (Function URL)
    return metodo or event.get("httpMethod")     # payload v1.0 (API GW REST)


def _caminho(event: dict) -> str:
    """Extrai o caminho da requisição, sem barra final, dos dois formatos."""
    ctx = event.get("requestContext", {})
    caminho = event.get("rawPath") or ctx.get("http", {}).get("path") or "/"
    caminho = caminho.rstrip("/")
    return caminho or "/"


def _extrair_nome(event: dict) -> str | None:
    """Extrai o nome do aluno do corpo JSON: { "nome": "Amanda" }."""
    corpo = event.get("body")
    if not corpo:
        return None
    if event.get("isBase64Encoded"):
        corpo = base64.b64decode(corpo).decode("utf-8")
    try:
        dados = json.loads(corpo)
    except (ValueError, TypeError):
        return None
    if isinstance(dados, dict) and dados.get("nome"):
        return str(dados["nome"])
    return None


def _resposta_json(dados: dict, status: int = 200, headers: dict | None = None) -> dict:
    """Monta a resposta no formato esperado pela Lambda (proxy integration).

    Os cabeçalhos de CORS são adicionados automaticamente pela Function URL
    (configuração `cors` no Terraform), então não os emitimos aqui para evitar
    cabeçalhos duplicados.
    """
    cabecalhos = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        cabecalhos.update(headers)
    return {
        "statusCode": status,
        "headers": cabecalhos,
        "body": json.dumps(dados, ensure_ascii=False),
    }


def lambda_handler(event, context):
    """Ponto de entrada da função Lambda."""
    metodo = _metodo_http(event)
    caminho = _caminho(event)

    # Roteamento: só existe uma rota nesta API.
    if caminho != ROTA:
        return _resposta_json(
            {"erro": f"Rota não encontrada. Use {METODO} {ROTA}"},
            status=404,
        )

    # Método: a rota aceita apenas POST.
    if metodo != METODO:
        return _resposta_json(
            {"erro": f"Método não permitido. Use {METODO} {ROTA}"},
            status=405,
            headers={"Allow": METODO},
        )

    nome = _extrair_nome(event)
    if not nome or not nome.strip():
        return _resposta_json(
            {"erro": "Informe o campo 'nome' no corpo JSON."},
            status=400,
        )

    casa = selecionar_casa(nome)
    return _resposta_json({"nome": nome.strip(), "casa": casa})
