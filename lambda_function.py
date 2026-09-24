"""
Chapéu Seletor Serverless — Checkpoint 3 (Orquestração com AWS Step Functions).

Uma ÚNICA Lambda expõe dois endpoints HTTP (Function URL):
  * POST /v1/selecionar  → envia a entrada para o Step Functions e devolve o resultado.
  * GET  /v1/alunos      → lista os alunos gravados (lê o DynamoDB).

A orquestração (sortear a casa + persistir de forma idempotente) acontece
inteiramente dentro do Step Functions, com integrações nativas (sem Lambda):
sorteio via `States.MathRandom` e gravação via integração direta `dynamodb:putItem`.

Handler: lambda_function.lambda_handler
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ROTA_SELECIONAR = "/v1/selecionar"
ROTA_ALUNOS = "/v1/alunos"
ROTA_VERSAO = "/v1/versao"

# Versão da aplicação (bump manual). O commit é injetado no deploy (APP_VERSION).
VERSAO = "1.0.0"

# Namespace das métricas customizadas (CloudWatch / EMF).
NAMESPACE_METRICAS = "ChapeuSeletor"

_sfn = None
_dynamodb = None


# ---------------------------------------------------------------------------
# Observabilidade: logging estruturado (JSON) e métricas via EMF.
# ---------------------------------------------------------------------------
def _log(evento: str, **campos) -> None:
    """Emite um log estruturado em JSON (consultável no CloudWatch Logs Insights)."""
    logger.info(json.dumps({"evento": evento, **campos}, ensure_ascii=False))


def _metricas(valores: dict, dimensoes: dict, unidades: dict | None = None, extra: dict | None = None) -> None:
    """Emite métricas no formato EMF; o CloudWatch as extrai automaticamente do log.

    valores:   {"Cadastros": 1, ...}
    dimensoes: {"Endpoint": "selecionar"}
    unidades:  {"LatenciaMs": "Milliseconds"}  (default: Count)
    """
    unidades = unidades or {}
    documento = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": NAMESPACE_METRICAS,
                    "Dimensions": [list(dimensoes.keys())],
                    "Metrics": [{"Name": nome, "Unit": unidades.get(nome, "Count")} for nome in valores],
                }
            ],
        },
        **dimensoes,
        **valores,
    }
    if extra:
        documento.update(extra)
    print(json.dumps(documento, ensure_ascii=False))


def _sfn_client():
    global _sfn
    if _sfn is None:
        import boto3

        _sfn = boto3.client("stepfunctions")
    return _sfn


def _dynamodb_client():
    global _dynamodb
    if _dynamodb is None:
        import boto3

        _dynamodb = boto3.client("dynamodb")
    return _dynamodb


# ---------------------------------------------------------------------------
# Helpers HTTP.
# ---------------------------------------------------------------------------
def _metodo_http(event: dict) -> str | None:
    ctx = event.get("requestContext", {})
    return ctx.get("http", {}).get("method") or event.get("httpMethod")


def _caminho(event: dict) -> str:
    ctx = event.get("requestContext", {})
    caminho = event.get("rawPath") or ctx.get("http", {}).get("path") or "/"
    return caminho.rstrip("/") or "/"


def _corpo(event: dict) -> str:
    corpo = event.get("body") or ""
    if corpo and event.get("isBase64Encoded"):
        corpo = base64.b64decode(corpo).decode("utf-8")
    return corpo


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
# POST /v1/selecionar → inicia a execução síncrona do Step Functions.
# ---------------------------------------------------------------------------
def _selecionar(event: dict) -> dict:
    corpo = _corpo(event)
    try:
        dados = json.loads(corpo)
    except (ValueError, TypeError):
        dados = {}
    if not isinstance(dados, dict):
        dados = {}

    # Aceita: um aluno ("nome"+"email") ou uma lista ("alunos": [{"nome","email"}, ...]).
    if isinstance(dados.get("alunos"), list):
        entradas = [a for a in dados["alunos"] if isinstance(a, dict)]
    elif dados.get("nome") or dados.get("email"):
        entradas = [{"nome": dados.get("nome"), "email": dados.get("email")}]
    else:
        entradas = []

    if not entradas:
        return _resposta_json({"erro": "Informe 'nome' e 'email' no corpo JSON."}, 400)

    # E-mail é obrigatório para todos os alunos.
    alunos = []
    for item in entradas:
        nome = str(item.get("nome") or "").strip()
        email = str(item.get("email") or "").strip()
        if not nome or not email:
            return _resposta_json({"erro": "'nome' e 'email' são obrigatórios."}, 400)
        alunos.append({"nome": nome, "email": email})

    inicio = time.time()
    resposta = _sfn_client().start_sync_execution(
        stateMachineArn=os.environ["STATE_MACHINE_ARN"],
        input=json.dumps({"alunos": alunos}, ensure_ascii=False),
    )
    latencia_ms = int((time.time() - inicio) * 1000)

    if resposta.get("status") != "SUCCEEDED":
        _log("selecao_falhou", latencia_ms=latencia_ms, erro=resposta.get("error"), causa=resposta.get("cause"))
        _metricas({"FluxoFalhou": 1}, {"Endpoint": "selecionar"})
        return _resposta_json(
            {"status": "falha", "erro": resposta.get("error"), "causa": resposta.get("cause")}, 502
        )

    saida = json.loads(resposta.get("output") or "[]")

    # Contabiliza os resultados por status e por casa para as métricas.
    contagem = {"cadastrado": 0, "duplicado": 0, "cancelado": 0}
    for r in saida:
        status = r.get("status", "desconhecido")
        contagem[status] = contagem.get(status, 0) + 1
        if status == "cadastrado" and r.get("casa"):
            _metricas({"SelecoesPorCasa": 1}, {"Casa": r["casa"]})

    _log(
        "selecao_processada",
        total=len(saida),
        latencia_ms=latencia_ms,
        cadastrados=contagem["cadastrado"],
        duplicados=contagem["duplicado"],
        cancelados=contagem["cancelado"],
    )
    _metricas(
        {
            "Cadastros": contagem["cadastrado"],
            "Duplicados": contagem["duplicado"],
            "Cancelados": contagem["cancelado"],
            "LatenciaFluxoMs": latencia_ms,
        },
        {"Endpoint": "selecionar"},
        unidades={"LatenciaFluxoMs": "Milliseconds"},
    )

    # Desembrulha quando há um único aluno.
    resultado = saida[0] if isinstance(saida, list) and len(saida) == 1 else saida
    return _resposta_json({"status": "ok", "resultado": resultado})


# ---------------------------------------------------------------------------
# GET /v1/alunos → lista os alunos gravados.
# ---------------------------------------------------------------------------
def _listar() -> dict:
    tabela = os.environ["TABLE_NAME"]
    resposta = _dynamodb_client().scan(TableName=tabela)
    alunos = [
        {
            "nome": item["nome"]["S"],
            "email": item.get("email", {}).get("S", ""),
            "casa": item["casa"]["S"],
            "notificado": item.get("notificado", {}).get("BOOL", False),
            "criado_em": item.get("criado_em", {}).get("S"),
        }
        for item in resposta.get("Items", [])
    ]
    alunos.sort(key=lambda a: a["nome"].lower())
    _log("alunos_listados", total=len(alunos))
    _metricas({"Consultas": 1, "AlunosNaBase": len(alunos)}, {"Endpoint": "alunos"})
    return _resposta_json({"total": len(alunos), "alunos": alunos})


# ---------------------------------------------------------------------------
# GET /v1/versao → mostra a versão implantada (para verificar o deploy).
# ---------------------------------------------------------------------------
def _versao() -> dict:
    dados = {
        "versao": VERSAO,
        "commit": os.environ.get("APP_VERSION", "desconhecido"),
        "lambda_version": os.environ.get("AWS_LAMBDA_FUNCTION_VERSION", ""),
        "consultado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _log("versao_consultada", versao=dados["versao"], commit=dados["commit"])
    return _resposta_json(dados)


# ---------------------------------------------------------------------------
# Handler único: roteia por caminho + método.
# ---------------------------------------------------------------------------
def lambda_handler(event, context):
    metodo = _metodo_http(event)
    caminho = _caminho(event)

    if caminho == ROTA_SELECIONAR:
        if metodo != "POST":
            return _resposta_json({"erro": f"Use POST {ROTA_SELECIONAR}"}, 405, {"Allow": "POST"})
        return _selecionar(event)

    if caminho == ROTA_ALUNOS:
        if metodo != "GET":
            return _resposta_json({"erro": f"Use GET {ROTA_ALUNOS}"}, 405, {"Allow": "GET"})
        return _listar()

    if caminho == ROTA_VERSAO:
        if metodo != "GET":
            return _resposta_json({"erro": f"Use GET {ROTA_VERSAO}"}, 405, {"Allow": "GET"})
        return _versao()

    return _resposta_json(
        {"erro": f"Rota não encontrada. Use {ROTA_SELECIONAR}, {ROTA_ALUNOS} ou {ROTA_VERSAO}"}, 404
    )
