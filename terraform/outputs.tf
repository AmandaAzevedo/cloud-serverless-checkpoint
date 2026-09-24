output "http_endpoint" {
  description = "URL pública (produtora) para testar com curl: POST /v1/selecionar."
  value       = "${aws_lambda_function_url.publisher.function_url}v1/selecionar"
}

output "list_endpoint" {
  description = "URL pública (listadora) para listar os alunos: GET /v1/alunos."
  value       = "${aws_lambda_function_url.lister.function_url}v1/alunos"
}

output "sns_topic_arn" {
  description = "ARN do tópico SNS onde as mensagens são publicadas."
  value       = aws_sns_topic.eventos.arn
}

output "consumer_function_name" {
  description = "Nome da função consumidora (veja os logs dela no CloudWatch)."
  value       = aws_lambda_function.chapeu_seletor.function_name
}
