"""
Chapéu Seletor Serverless — Checkpoint 2 (Event-Driven, AWS Lambda + SNS).

Três funções que compartilham este mesmo código:

  * PRODUTORA   (handler: publisher_handler)
      POST /v1/selecionar (HTTP) → publica a mensagem no tópico SNS. Responde 202.

  * CONSUMIDORA (handler: lambda_handler)
      Acionada pelo SNS. Sorteia a casa, grava no DynamoDB e registra no log.

  * LISTADORA   (handler: lister_handler)
      GET /v1/alunos (HTTP) → lê o DynamoDB e devolve todos os alunos e suas casas.

Formato da mensagem/corpo JSON: { "nome": "Amanda" }
"""

from __future__ import annotations

import base64
import json
import logging
import os
import random
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Casas de Hogwarts disponíveis para seleção.
CASAS = ["Grifinória", "Sonserina", "Corvinal", "Lufa-Lufa"]

# Rotas/métodos aceitos pelas funções HTTP.
ROTA_SELECIONAR = "/v1/selecionar"
ROTA_ALUNOS = "/v1/alunos"

# Clientes AWS reutilizados entre invocações (criados sob demanda).
_sns = None
_dynamodb = None


def selecionar_casa(nome: str) -> str:
    """Seleciona uma casa aleatoriamente entre as quatro de Hogwarts."""
    return random.choice(CASAS)


def _nome_de_json(texto: str) -> str | None:
    """Extrai o campo 'nome' de um texto JSON: { "nome": "Amanda" }."""
    try:
        dados = json.loads(texto)
    except (ValueError, TypeError):
        return None
    if isinstance(dados, dict) and dados.get("nome"):
        return str(dados["nome"])
    return None


# ---------------------------------------------------------------------------
# Clientes AWS (import tardio para não exigir boto3 nos testes).
# ---------------------------------------------------------------------------
def _sns_client():
    global _sns
    if _sns is None:
        import boto3

        _sns = boto3.client("sns")
    return _sns


def _dynamodb_client():
    global _dynamodb
    if _dynamodb is None:
        import boto3

        _dynamodb = boto3.client("dynamodb")
    return _dynamodb


# ---------------------------------------------------------------------------
# CONSUMIDORA — acionada pelo SNS.
# ---------------------------------------------------------------------------
def _gravar_resultado(nome: str, casa: str) -> None:
    """Grava (ou sobrescreve) o resultado do aluno no DynamoDB."""
    tabela = os.environ.get("TABLE_NAME")
    if not tabela:
        return
    _dynamodb_client().put_item(
        TableName=tabela,
        Item={
            "nome": {"S": nome},
            "casa": {"S": casa},
            "atualizado_em": {"S": datetime.now(timezone.utc).isoformat()},
        },
    )


def _processar_registro(registro: dict) -> dict | None:
    """Processa um registro de evento do SNS e devolve o resultado (ou None)."""
    mensagem = registro.get("Sns", {}).get("Message", "")
    nome = _nome_de_json(mensagem)

    if not nome or not nome.strip():
        logger.warning("Mensagem ignorada (sem campo 'nome'): %s", mensagem)
        return None

    nome = nome.strip()
    casa = selecionar_casa(nome)
    resultado = {"nome": nome, "casa": casa}
    _gravar_resultado(nome, casa)
    logger.info("Aluno selecionado: %s", json.dumps(resultado, ensure_ascii=False))
    return resultado


def lambda_handler(event, context):
    """Handler da CONSUMIDORA (eventos do SNS)."""
    registros = event.get("Records", [])
    resultados = [r for r in (_processar_registro(reg) for reg in registros) if r]
    logger.info("Processadas %d mensagem(ns) do tópico.", len(resultados))
    return {"processados": len(resultados), "resultados": resultados}


# ---------------------------------------------------------------------------
# Helpers HTTP (produtora e listadora).
# ---------------------------------------------------------------------------
def _metodo_http(event: dict) -> str | None:
    ctx = event.get("requestContext", {})
    return ctx.get("http", {}).get("method") or event.get("httpMethod")


def _caminho(event: dict) -> str:
    ctx = event.get("requestContext", {})
    caminho = event.get("rawPath") or ctx.get("http", {}).get("path") or "/"
    return caminho.rstrip("/") or "/"


def _resposta_json(dados: dict, status: int = 200, headers: dict | None = None) -> dict:
    cabecalhos = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        cabecalhos.update(headers)
    return {
        "statusCode": status,
        "headers": cabecalhos,
        "body": json.dumps(dados, ensure_ascii=False),
    }


# ---------------------------------------------------------------------------
# PRODUTORA — recebe HTTP e publica no SNS.
# ---------------------------------------------------------------------------
def publisher_handler(event, context):
    """Handler da PRODUTORA (HTTP → publica no tópico SNS)."""
    if _caminho(event) != ROTA_SELECIONAR:
        return _resposta_json({"erro": f"Rota não encontrada. Use POST {ROTA_SELECIONAR}"}, 404)

    if _metodo_http(event) != "POST":
        return _resposta_json(
            {"erro": f"Método não permitido. Use POST {ROTA_SELECIONAR}"},
            405,
            {"Allow": "POST"},
        )

    corpo = event.get("body") or ""
    if corpo and event.get("isBase64Encoded"):
        corpo = base64.b64decode(corpo).decode("utf-8")

    nome = _nome_de_json(corpo)
    if not nome or not nome.strip():
        return _resposta_json({"erro": "Informe o campo 'nome' no corpo JSON."}, 400)

    nome = nome.strip()
    resposta = _sns_client().publish(
        TopicArn=os.environ["TOPIC_ARN"],
        Message=json.dumps({"nome": nome}, ensure_ascii=False),
    )
    message_id = resposta.get("MessageId")
    logger.info("Publicado no tópico: nome=%s messageId=%s", nome, message_id)

    return _resposta_json(
        {
            "status": "aceito",
            "nome": nome,
            "messageId": message_id,
            "detalhe": "Processamento assíncrono; consulte GET /v1/alunos ou os logs.",
        },
        202,
    )


# ---------------------------------------------------------------------------
# LISTADORA — lê o DynamoDB e devolve todos os alunos.
# ---------------------------------------------------------------------------
def lister_handler(event, context):
    """Handler da LISTADORA (HTTP GET → lista alunos e casas do DynamoDB)."""
    if _caminho(event) != ROTA_ALUNOS:
        return _resposta_json({"erro": f"Rota não encontrada. Use GET {ROTA_ALUNOS}"}, 404)

    if _metodo_http(event) != "GET":
        return _resposta_json(
            {"erro": f"Método não permitido. Use GET {ROTA_ALUNOS}"},
            405,
            {"Allow": "GET"},
        )

    tabela = os.environ["TABLE_NAME"]
    resposta = _dynamodb_client().scan(TableName=tabela)
    alunos = [
        {
            "nome": item["nome"]["S"],
            "casa": item["casa"]["S"],
            "atualizado_em": item.get("atualizado_em", {}).get("S"),
        }
        for item in resposta.get("Items", [])
    ]
    alunos.sort(key=lambda a: a["nome"].lower())
    return _resposta_json({"total": len(alunos), "alunos": alunos})
