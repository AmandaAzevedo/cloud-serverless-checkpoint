terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.region
}

# Empacota o código-fonte da (única) Lambda HTTP.
data "archive_file" "source" {
  type        = "zip"
  source_file = "${path.module}/../lambda_function.py"
  output_path = "${path.module}/build/lambda_function.zip"
}

# ===========================================================================
# Armazenamento (DynamoDB) e Dead-Letter Queue (SQS).
# ===========================================================================
resource "aws_dynamodb_table" "selecoes" {
  name         = "${var.prefix}-selecoes"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "email" # e-mail é a chave única (não pode repetir)

  attribute {
    name = "email"
    type = "S"
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.prefix}-dlq"
  message_retention_seconds = 1209600 # 14 dias
  sqs_managed_sse_enabled   = true
}

# Evento de domínio: o fluxo crítico termina no Step Functions e os consumidores
# posteriores reagem por coreografia, sem acoplar seu tempo de execução ao HTTP.
resource "aws_sns_topic" "eventos" {
  name = "${var.prefix}-eventos"
}

resource "aws_sqs_queue" "auditoria" {
  name                      = "${var.prefix}-auditoria"
  message_retention_seconds = 345600 # 4 dias
  sqs_managed_sse_enabled   = true
}

data "aws_iam_policy_document" "auditoria" {
  statement {
    sid       = "PermitirSomenteTopicoDeEventos"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.auditoria.arn]

    principals {
      type        = "Service"
      identifiers = ["sns.amazonaws.com"]
    }

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_sns_topic.eventos.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "auditoria" {
  queue_url = aws_sqs_queue.auditoria.id
  policy    = data.aws_iam_policy_document.auditoria.json
}

resource "aws_sns_topic_subscription" "auditoria" {
  topic_arn            = aws_sns_topic.eventos.arn
  protocol             = "sqs"
  endpoint             = aws_sqs_queue.auditoria.arn
  raw_message_delivery = true
}

# Amazon SES — envio de e-mail para o destinatário informado no request.
# Cria a identidade do remetente (a AWS envia um e-mail de verificação a ele).
resource "aws_ses_email_identity" "remetente" {
  email = var.sender_email
}

# ===========================================================================
# Step Functions (EXPRESS) — orquestração nativa, sem Lambda.
# ===========================================================================
resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/aws/vendedlogs/states/${var.prefix}"
  retention_in_days = 14
}

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "sfn" {
  statement {
    sid       = "GravarNoDynamoDB"
    actions   = ["dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
    resources = [aws_dynamodb_table.selecoes.arn]
  }
  statement {
    sid       = "EnviarParaDLQ"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.dlq.arn]
  }
  statement {
    sid       = "PublicarEventosDeDominio"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.eventos.arn]
  }
  statement {
    sid       = "EnviarEmail"
    actions   = ["ses:SendEmail", "ses:SendRawEmail"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "ses:FromAddress"
      values   = [var.sender_email]
    }
  }

  statement {
    sid       = "ClassificarComIA"
    actions   = ["bedrock:InvokeModel"]
    resources = ["arn:aws:bedrock:${var.region}::foundation-model/${var.bedrock_model_id}"]
  }

  statement {
    sid = "LogsDoStepFunctions"
    actions = [
      "logs:CreateLogDelivery",
      "logs:GetLogDelivery",
      "logs:UpdateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:DescribeResourcePolicies",
      "logs:DescribeLogGroups",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role" "sfn" {
  name               = "${var.prefix}-sfn-role"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

resource "aws_iam_role_policy" "sfn" {
  name   = "${var.prefix}-sfn-policy"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn.json
}

resource "aws_sfn_state_machine" "orquestrador" {
  name     = "${var.prefix}-sfn"
  role_arn = aws_iam_role.sfn.arn
  type     = "EXPRESS"

  definition = templatefile("${path.module}/../statemachine.asl.json", {
    TableName      = aws_dynamodb_table.selecoes.name
    DlqUrl         = aws_sqs_queue.dlq.url
    SenderEmail    = var.sender_email
    BedrockModelId = var.bedrock_model_id
    EventsTopicArn = aws_sns_topic.eventos.arn
  })

  logging_configuration {
    log_destination = "${aws_cloudwatch_log_group.sfn.arn}:*"
    # Nome, perfil e e-mail são dados pessoais; mantemos apenas eventos do fluxo.
    include_execution_data = false
    level                  = "ALL"
  }
}

# ===========================================================================
# A ÚNICA Lambda: endpoints HTTP (POST /v1/selecionar e GET /v1/alunos).
# ===========================================================================
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api" {
  name               = "${var.prefix}-api-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "api_logs" {
  role       = aws_iam_role.api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "api" {
  statement {
    sid       = "IniciarFluxo"
    actions   = ["states:StartSyncExecution"]
    resources = [aws_sfn_state_machine.orquestrador.arn]
  }
  statement {
    sid       = "LerAlunos"
    actions   = ["dynamodb:Scan"]
    resources = [aws_dynamodb_table.selecoes.arn]
  }
}

resource "aws_iam_role_policy" "api" {
  name   = "${var.prefix}-api-policy"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

resource "aws_lambda_function" "api" {
  function_name    = "${var.prefix}-api"
  role             = aws_iam_role.api.arn
  runtime          = "python3.12"
  handler          = "lambda_function.lambda_handler"
  filename         = data.archive_file.source.output_path
  source_code_hash = data.archive_file.source.output_base64sha256
  timeout          = 30

  environment {
    variables = {
      STATE_MACHINE_ARN = aws_sfn_state_machine.orquestrador.arn
      TABLE_NAME        = aws_dynamodb_table.selecoes.name
      APP_VERSION       = var.app_version
    }
  }
}

resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = var.allowed_origins
    allow_methods = ["GET", "POST"]
    allow_headers = ["content-type"]
    max_age       = 3600
  }
}

resource "aws_lambda_permission" "api_public_url" {
  statement_id           = "AllowPublicFunctionUrlInvoke"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

# Desde outubro de 2025, Function URLs novas exigem também InvokeFunction.
# A condição impede que o acesso público seja usado por outra via de invocação.
resource "aws_lambda_permission" "api_public_invoke" {
  statement_id             = "AllowPublicInvokeOnlyViaFunctionUrl"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.api.function_name
  principal                = "*"
  invoked_via_function_url = true
}

data "aws_caller_identity" "atual" {}

resource "aws_cloudwatch_dashboard" "observabilidade" {
  dashboard_name = "${var.prefix}-observabilidade"
  dashboard_body = jsonencode(local.dashboard)
}

# Alarmes operacionais: ficam visíveis no CloudWatch mesmo sem um canal de SNS.
resource "aws_cloudwatch_metric_alarm" "lambda_erros" {
  alarm_name          = "${var.prefix}-lambda-erros"
  alarm_description   = "A Lambda HTTP apresentou erro não tratado."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.api.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "dlq_com_mensagens" {
  alarm_name          = "${var.prefix}-dlq-com-mensagens"
  alarm_description   = "Há falha que precisa de análise ou reconciliação na DLQ."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
}
