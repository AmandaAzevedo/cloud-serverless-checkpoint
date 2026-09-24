"""Chapéu Seletor Serverless — projeto final.

Uma única Lambda expõe três endpoints HTTP (Function URL):
  * POST /v1/selecionar  → envia a entrada para o Step Functions e devolve o resultado.
  * GET  /v1/alunos      → lista os alunos gravados (lê o DynamoDB).
  * GET  /v1/versao      → identifica a versão e o commit implantados.

A orquestração (classificar + persistir + notificar) acontece
inteiramente dentro do Step Functions, com integrações nativas (sem Lambda):
classificação via Amazon Bedrock, fallback com `States.MathRandom` e integrações
diretas com DynamoDB, SES e SQS.

Handler: lambda_function.lambda_handler
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ROTA_SELECIONAR = "/v1/selecionar"
ROTA_ALUNOS = "/v1/alunos"
ROTA_VERSAO = "/v1/versao"
VERSAO = "2.0.0"

MAX_ALUNOS_POR_REQUISICAO = 25
MAX_NOME = 120
MAX_PERFIL = 500
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

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
    cabecalhos = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
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
    try:
        dados = json.loads(_corpo(event))
    except (ValueError, TypeError, UnicodeDecodeError):
        return _resposta_json({"erro": "O corpo deve ser um JSON válido."}, 400)
    if not isinstance(dados, dict):
        return _resposta_json({"erro": "O corpo JSON deve ser um objeto."}, 400)

    # Aceita: um aluno ("nome"+"email") ou uma lista ("alunos": [{"nome","email"}, ...]).
    if isinstance(dados.get("alunos"), list):
        entradas = [a for a in dados["alunos"] if isinstance(a, dict)]
    elif dados.get("nome") or dados.get("email"):
        entradas = [
            {
                "nome": dados.get("nome"),
                "email": dados.get("email"),
                "caracteristicas": dados.get("caracteristicas"),
                "perfil": dados.get("perfil"),
            }
        ]
    else:
        entradas = []

    if not entradas:
        return _resposta_json({"erro": "Informe 'nome' e 'email' no corpo JSON."}, 400)

    if len(entradas) > MAX_ALUNOS_POR_REQUISICAO:
        return _resposta_json(
            {"erro": f"Envie no máximo {MAX_ALUNOS_POR_REQUISICAO} alunos por requisição."}, 400
        )

    # E-mail é obrigatório para todos os alunos.
    alunos = []
    for item in entradas:
        nome = str(item.get("nome") or "").strip()
        email = str(item.get("email") or "").strip().lower()
        perfil = str(item.get("caracteristicas") or item.get("perfil") or "Não informadas.").strip()
        if not nome or not email:
            return _resposta_json({"erro": "'nome' e 'email' são obrigatórios."}, 400)
        if len(nome) > MAX_NOME:
            return _resposta_json({"erro": f"'nome' deve ter no máximo {MAX_NOME} caracteres."}, 400)
        if len(email) > 254 or not EMAIL_RE.fullmatch(email):
            return _resposta_json({"erro": "Informe um e-mail válido."}, 400)
        if len(perfil) > MAX_PERFIL:
            return _resposta_json(
                {"erro": f"'caracteristicas' deve ter no máximo {MAX_PERFIL} caracteres."}, 400
            )
        alunos.append({"nome": nome, "email": email, "perfil": perfil})

    inicio = time.time()
    try:
        resposta = _sfn_client().start_sync_execution(
            stateMachineArn=os.environ["STATE_MACHINE_ARN"],
            input=json.dumps({"alunos": alunos}, ensure_ascii=False),
        )
    except Exception as exc:  # a API não deve expor detalhes internos da AWS
        latencia_ms = int((time.time() - inicio) * 1000)
        _log("orquestracao_indisponivel", latencia_ms=latencia_ms, tipo_erro=type(exc).__name__)
        _metricas({"FluxoFalhou": 1}, {"Endpoint": "selecionar"})
        return _resposta_json({"status": "falha", "erro": "Orquestração temporariamente indisponível."}, 503)
    latencia_ms = int((time.time() - inicio) * 1000)

    if resposta.get("status") != "SUCCEEDED":
        _log("selecao_falhou", latencia_ms=latencia_ms, tipo_erro=resposta.get("error"))
        _metricas({"FluxoFalhou": 1}, {"Endpoint": "selecionar"})
        return _resposta_json({"status": "falha", "erro": "Não foi possível concluir a seleção."}, 502)

    try:
        saida = json.loads(resposta.get("output") or "[]")
    except (TypeError, ValueError):
        _log("resposta_orquestracao_invalida", latencia_ms=latencia_ms)
        _metricas({"FluxoFalhou": 1}, {"Endpoint": "selecionar"})
        return _resposta_json({"status": "falha", "erro": "Resposta inválida da orquestração."}, 502)

    if not isinstance(saida, list):
        _log("resposta_orquestracao_invalida", latencia_ms=latencia_ms)
        return _resposta_json({"status": "falha", "erro": "Resposta inválida da orquestração."}, 502)

    # Contabiliza os resultados por status e por casa para as métricas.
    contagem = {"cadastrado": 0, "duplicado": 0, "cancelado": 0, "pendente": 0}
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
        pendentes=contagem["pendente"],
    )
    _metricas(
        {
            "Cadastros": contagem["cadastrado"],
            "Duplicados": contagem["duplicado"],
            "Cancelados": contagem["cancelado"],
            "Pendentes": contagem["pendente"],
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
    cliente = _dynamodb_client()
    resposta = cliente.scan(TableName=tabela)
    itens = list(resposta.get("Items", []))
    while resposta.get("LastEvaluatedKey"):
        resposta = cliente.scan(TableName=tabela, ExclusiveStartKey=resposta["LastEvaluatedKey"])
        itens.extend(resposta.get("Items", []))
    alunos = [
        {
            "nome": item["nome"]["S"],
            "email": item.get("email", {}).get("S", ""),
            "casa": item["casa"]["S"],
            "justificativa": item.get("justificativa", {}).get("S", ""),
            "origem": item.get("origem", {}).get("S", ""),
            "notificado": item.get("notificado", {}).get("BOOL", False),
            "criado_em": item.get("criado_em", {}).get("S"),
        }
        for item in itens
    ]
    alunos.sort(key=lambda a: a["nome"].lower())
    _log("alunos_listados", total=len(alunos))
    _metricas({"Consultas": 1, "AlunosNaBase": len(alunos)}, {"Endpoint": "alunos"})
    return _resposta_json({"total": len(alunos), "alunos": alunos})


def _versao(context) -> dict:
    """Expõe metadados não sensíveis para comprovar o artefato implantado."""
    return _resposta_json(
        {
            "versao": VERSAO,
            "commit": os.environ.get("APP_VERSION", "local"),
            "lambda_version": getattr(context, "function_version", "$LATEST"),
        }
    )


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
        return _versao(context)

    return _resposta_json(
        {
            "erro": (
                f"Rota não encontrada. Use POST {ROTA_SELECIONAR}, "
                f"GET {ROTA_ALUNOS} ou GET {ROTA_VERSAO}"
            )
        },
        404,
    )
