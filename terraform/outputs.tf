output "selecionar_endpoint" {
  description = "URL da Função Ativa — POST para selecionar um aluno."
  value       = "${aws_lambda_function_url.api.function_url}v1/selecionar"
  sensitive   = true
}

output "list_endpoint" {
  description = "URL para listar os alunos: GET /v1/alunos."
  value       = "${aws_lambda_function_url.api.function_url}v1/alunos"
  sensitive   = true
}

output "version_endpoint" {
  description = "URL para comprovar a versão implantada: GET /v1/versao."
  value       = "${aws_lambda_function_url.api.function_url}v1/versao"
  sensitive   = true
}

output "function_url_base" {
  description = "Base da Function URL (a mesma Lambda atende os dois caminhos)."
  value       = aws_lambda_function_url.api.function_url
  sensitive   = true
}

output "state_machine_arn" {
  description = "ARN da state machine (Step Functions) que orquestra o fluxo."
  value       = aws_sfn_state_machine.orquestrador.arn
  sensitive   = true
}

output "dlq_url" {
  description = "URL da dead-letter queue (SQS)."
  value       = aws_sqs_queue.dlq.url
  sensitive   = true
}

output "events_topic_arn" {
  description = "Tópico SNS dos eventos de domínio AlunoSelecionado."
  value       = aws_sns_topic.eventos.arn
  sensitive   = true
}

output "audit_queue_url" {
  description = "Fila consumidora usada como trilha assíncrona de auditoria."
  value       = aws_sqs_queue.auditoria.url
  sensitive   = true
}

output "sender_email" {
  description = "E-mail remetente das notificações (precisa estar verificado no SES)."
  value       = var.sender_email
  sensitive   = true
}

output "dashboard_url" {
  description = "URL do dashboard CloudWatch."
  value       = "https://${var.region}.console.aws.amazon.com/cloudwatch/home?region=${var.region}#dashboards/dashboard/${aws_cloudwatch_dashboard.observabilidade.dashboard_name}"
  sensitive   = true
}
