variable "region" {
  description = "Região da AWS onde a função será implantada."
  type        = string
  default     = "us-east-1"
}

variable "function_name" {
  description = "Nome da função Lambda."
  type        = string
  default     = "chapeu-seletor"
}

variable "allowed_origins" {
  description = "Origens permitidas no CORS. Use [\"*\"] para público ou liste domínios (ex.: [\"https://meuapp.com\"])."
  type        = list(string)
  default     = ["*"]
}
