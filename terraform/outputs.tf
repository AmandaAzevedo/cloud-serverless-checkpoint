output "selecionar_endpoint" {
  description = "URL da Função Ativa — POST para selecionar um aluno."
  value       = "${aws_lambda_function_url.api.function_url}v1/selecionar"
}

output "list_endpoint" {
  description = "URL para listar os alunos: GET /v1/alunos."
  value       = "${aws_lambda_function_url.api.function_url}v1/alunos"
}

output "function_url_base" {
  description = "Base da Function URL (a mesma Lambda atende os dois caminhos)."
  value       = aws_lambda_function_url.api.function_url
}

output "state_machine_arn" {
  description = "ARN da state machine (Step Functions) que orquestra o fluxo."
  value       = aws_sfn_state_machine.orquestrador.arn
}

output "dlq_url" {
  description = "URL da dead-letter queue (SQS)."
  value       = aws_sqs_queue.dlq.url
}

output "sender_email" {
  description = "E-mail remetente das notificações (precisa estar verificado no SES)."
  value       = var.sender_email
}
