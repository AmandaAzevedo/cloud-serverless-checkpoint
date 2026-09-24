terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
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

# Compacta o código-fonte da função em um .zip para envio à Lambda.
data "archive_file" "source" {
  type        = "zip"
  source_file = "${path.module}/../lambda_function.py"
  output_path = "${path.module}/build/lambda_function.zip"
}

# ---------------------------------------------------------------------------
# IAM: papel de execução que a Lambda assume.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${var.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

# Permite que a função escreva logs no CloudWatch.
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ---------------------------------------------------------------------------
# Armazenamento: tabela DynamoDB com os alunos e suas casas.
# ---------------------------------------------------------------------------
resource "aws_dynamodb_table" "alunos" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "nome"

  attribute {
    name = "nome"
    type = "S"
  }
}

# Permite que a CONSUMIDORA grave na tabela.
data "aws_iam_policy_document" "consumer_dynamodb" {
  statement {
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.alunos.arn]
  }
}

resource "aws_iam_role_policy" "consumer_dynamodb" {
  name   = "${var.function_name}-dynamodb-write"
  role   = aws_iam_role.lambda_exec.id
  policy = data.aws_iam_policy_document.consumer_dynamodb.json
}

# ---------------------------------------------------------------------------
# Função CONSUMIDORA: acionada pelo SNS, sorteia, grava no DynamoDB e loga.
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "chapeu_seletor" {
  function_name    = var.function_name
  role             = aws_iam_role.lambda_exec.arn
  runtime          = "python3.12"
  handler          = "lambda_function.lambda_handler"
  filename         = data.archive_file.source.output_path
  source_code_hash = data.archive_file.source.output_base64sha256
  timeout          = 10
  memory_size      = 128

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.alunos.name
    }
  }
}

# ---------------------------------------------------------------------------
# Mensageria: tópico SNS (pub/sub) que dispara a Lambda.
# ---------------------------------------------------------------------------
resource "aws_sns_topic" "eventos" {
  name = var.topic_name
}

# Inscreve a Lambda no tópico: toda mensagem publicada dispara a função.
resource "aws_sns_topic_subscription" "lambda" {
  topic_arn = aws_sns_topic.eventos.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.chapeu_seletor.arn
}

# Permite que o SNS invoque a Lambda.
resource "aws_lambda_permission" "sns" {
  statement_id  = "AllowSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.chapeu_seletor.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.eventos.arn
}

# ---------------------------------------------------------------------------
# Função PRODUTORA: endpoint HTTP que publica mensagens no tópico SNS.
# Permite testar todo o fluxo com um simples `curl`, sem credenciais AWS.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "publisher_exec" {
  name               = "${var.publisher_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "publisher_logs" {
  role       = aws_iam_role.publisher_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Permite que a produtora publique SOMENTE neste tópico (least privilege).
data "aws_iam_policy_document" "publisher_sns" {
  statement {
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.eventos.arn]
  }
}

resource "aws_iam_role_policy" "publisher_sns" {
  name   = "${var.publisher_name}-sns-publish"
  role   = aws_iam_role.publisher_exec.id
  policy = data.aws_iam_policy_document.publisher_sns.json
}

resource "aws_lambda_function" "publisher" {
  function_name    = var.publisher_name
  role             = aws_iam_role.publisher_exec.arn
  runtime          = "python3.12"
  handler          = "lambda_function.publisher_handler"
  filename         = data.archive_file.source.output_path
  source_code_hash = data.archive_file.source.output_base64sha256
  timeout          = 10
  memory_size      = 128

  environment {
    variables = {
      TOPIC_ARN = aws_sns_topic.eventos.arn
    }
  }
}

# Function URL pública da produtora (endpoint HTTPS, sem API Gateway).
resource "aws_lambda_function_url" "publisher" {
  function_name      = aws_lambda_function.publisher.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = var.allowed_origins
    allow_methods = ["POST"]
    allow_headers = ["content-type"]
    max_age       = 3600
  }
}

resource "aws_lambda_permission" "publisher_public_url" {
  statement_id           = "AllowPublicFunctionUrlInvoke"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.publisher.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

# ---------------------------------------------------------------------------
# Função LISTADORA: endpoint HTTP GET que lista os alunos do DynamoDB.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "lister_exec" {
  name               = "${var.lister_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lister_logs" {
  role       = aws_iam_role.lister_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Permite que a listadora leia a tabela (somente leitura).
data "aws_iam_policy_document" "lister_dynamodb" {
  statement {
    actions   = ["dynamodb:Scan"]
    resources = [aws_dynamodb_table.alunos.arn]
  }
}

resource "aws_iam_role_policy" "lister_dynamodb" {
  name   = "${var.lister_name}-dynamodb-read"
  role   = aws_iam_role.lister_exec.id
  policy = data.aws_iam_policy_document.lister_dynamodb.json
}

resource "aws_lambda_function" "lister" {
  function_name    = var.lister_name
  role             = aws_iam_role.lister_exec.arn
  runtime          = "python3.12"
  handler          = "lambda_function.lister_handler"
  filename         = data.archive_file.source.output_path
  source_code_hash = data.archive_file.source.output_base64sha256
  timeout          = 10
  memory_size      = 128

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.alunos.name
    }
  }
}

resource "aws_lambda_function_url" "lister" {
  function_name      = aws_lambda_function.lister.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = var.allowed_origins
    allow_methods = ["GET"]
    allow_headers = ["content-type"]
    max_age       = 3600
  }
}

resource "aws_lambda_permission" "lister_public_url" {
  statement_id           = "AllowPublicFunctionUrlInvoke"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.lister.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}
