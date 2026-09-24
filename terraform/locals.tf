locals {
  fn     = "${var.prefix}-api"
  dlq    = "${var.prefix}-dlq"
  sm_arn = "arn:aws:states:${var.region}:${data.aws_caller_identity.atual.account_id}:stateMachine:${var.prefix}-sfn"
  ns     = "ChapeuSeletor"

  dashboard = {
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6,
        properties = {
          title  = "Lambda — Invocações e Erros",
          region = var.region, view = "timeSeries", stacked = false, period = 300,
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", local.fn, { stat = "Sum" }],
            ["AWS/Lambda", "Errors", "FunctionName", local.fn, { stat = "Sum" }],
            ["AWS/Lambda", "Throttles", "FunctionName", local.fn, { stat = "Sum" }]
          ]
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6,
        properties = {
          title  = "Lambda — Duração (ms)",
          region = var.region, view = "timeSeries", period = 300,
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", local.fn, { stat = "Average", label = "média" }],
            ["AWS/Lambda", "Duration", "FunctionName", local.fn, { stat = "p99", label = "p99" }]
          ]
        }
      },
      {
        type = "metric", x = 0, y = 6, width = 12, height = 6,
        properties = {
          title  = "Step Functions — Execuções",
          region = var.region, view = "timeSeries", period = 300,
          metrics = [
            ["AWS/States", "ExecutionsStarted", "StateMachineArn", local.sm_arn, { stat = "Sum" }],
            ["AWS/States", "ExecutionsSucceeded", "StateMachineArn", local.sm_arn, { stat = "Sum" }],
            ["AWS/States", "ExecutionsFailed", "StateMachineArn", local.sm_arn, { stat = "Sum" }]
          ]
        }
      },
      {
        type = "metric", x = 12, y = 6, width = 6, height = 6,
        properties = {
          title  = "DLQ — Mensagens",
          region = var.region, view = "timeSeries", period = 300,
          metrics = [
            ["AWS/SQS", "NumberOfMessagesSent", "QueueName", local.dlq, { stat = "Sum", label = "enviadas" }],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", local.dlq, { stat = "Maximum", label = "na fila" }]
          ]
        }
      },
      {
        type = "metric", x = 18, y = 6, width = 6, height = 6,
        properties = {
          title  = "Consultas (GET /v1/alunos)",
          region = var.region, view = "timeSeries", period = 300,
          metrics = [
            [local.ns, "Consultas", "Endpoint", "alunos", { stat = "Sum" }],
            [local.ns, "AlunosNaBase", "Endpoint", "alunos", { stat = "Maximum", label = "alunos na base" }]
          ]
        }
      },
      {
        type = "metric", x = 0, y = 12, width = 12, height = 6,
        properties = {
          title  = "Negócio — resultados do processamento",
          region = var.region, view = "timeSeries", stacked = true, period = 300,
          metrics = [
            [local.ns, "Cadastros", "Endpoint", "selecionar", { stat = "Sum" }],
            [local.ns, "Duplicados", "Endpoint", "selecionar", { stat = "Sum" }],
            [local.ns, "Cancelados", "Endpoint", "selecionar", { stat = "Sum" }],
            [local.ns, "Pendentes", "Endpoint", "selecionar", { stat = "Sum" }]
          ]
        }
      },
      {
        type = "metric", x = 12, y = 12, width = 12, height = 6,
        properties = {
          title  = "Latência do fluxo (Step Functions síncrono)",
          region = var.region, view = "timeSeries", period = 300,
          metrics = [
            [local.ns, "LatenciaFluxoMs", "Endpoint", "selecionar", { stat = "Average", label = "média" }],
            [local.ns, "LatenciaFluxoMs", "Endpoint", "selecionar", { stat = "p99", label = "p99" }]
          ]
        }
      },
      {
        type = "metric", x = 0, y = 18, width = 12, height = 6,
        properties = {
          title  = "Seleções por casa",
          region = var.region, view = "timeSeries", stacked = true, period = 300,
          metrics = [
            [{ "expression" = "SEARCH('{${local.ns},Casa} MetricName=\"SelecoesPorCasa\"', 'Sum', 300)", "label" = "", "id" = "porCasa" }]
          ]
        }
      },
      {
        type = "log", x = 12, y = 18, width = 12, height = 6,
        properties = {
          title  = "Logs estruturados (últimas seleções)",
          region = var.region,
          query  = "SOURCE '/aws/lambda/${local.fn}' | fields @timestamp, evento, cadastrados, duplicados, cancelados, pendentes, latencia_ms | filter evento = 'selecao_processada' | sort @timestamp desc | limit 20",
          view   = "table"
        }
      }
    ]
  }
}
