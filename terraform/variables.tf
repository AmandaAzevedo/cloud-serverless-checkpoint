variable "region" {
  description = "Região da AWS onde os recursos serão implantados."
  type        = string
  default     = "us-east-1"
}

variable "prefix" {
  description = "Prefixo usado no nome de todos os recursos do cp3."
  type        = string
  default     = "chapeu-seletor-cp3"
}

variable "allowed_origins" {
  description = "Origens permitidas no CORS dos endpoints HTTP. Use [\"*\"] para público."
  type        = list(string)
  default     = ["*"]
}

variable "sender_email" {
  description = "E-mail remetente (From) verificado no SES para enviar as notificações."
  type        = string
  default     = ""
}
