variable "region" {
  description = "Região da AWS onde a função será implantada."
  type        = string
  default     = "us-east-1"
}

variable "function_name" {
  description = "Nome da função Lambda."
  type        = string
  default     = "chapeu-seletor-events"
}

variable "topic_name" {
  description = "Nome do tópico SNS que dispara a Lambda."
  type        = string
  default     = "alunos"
}

variable "publisher_name" {
  description = "Nome da função Lambda produtora (endpoint HTTP que publica no SNS)."
  type        = string
  default     = "chapeu-seletor-publisher"
}

variable "lister_name" {
  description = "Nome da função Lambda listadora (endpoint HTTP que lista os alunos)."
  type        = string
  default     = "chapeu-seletor-lister"
}

variable "table_name" {
  description = "Nome da tabela DynamoDB com os alunos selecionados."
  type        = string
  default     = "alunos-selecionados"
}

variable "allowed_origins" {
  description = "Origens permitidas no CORS da produtora. Use [\"*\"] para público."
  type        = list(string)
  default     = ["*"]
}
