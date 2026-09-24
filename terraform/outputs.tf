output "function_url" {
  description = "URL pública para invocar o Chapéu Seletor."
  value       = aws_lambda_function_url.chapeu_seletor.function_url
}
