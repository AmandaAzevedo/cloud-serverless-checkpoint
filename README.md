# Checkpoint 2 - Chapéu Seletor Serverless (Event-Driven)

Este projeto evolui o Checkpoint 1 para uma arquitetura orientada a eventos. Um
endpoint HTTP publica o nome do aluno em um tópico SNS; esse evento dispara uma
função que sorteia a casa de Hogwarts (Grifinória, Sonserina, Corvinal ou
Lufa-Lufa), grava o resultado no DynamoDB e registra no CloudWatch Logs. Um
segundo endpoint lista todos os alunos já selecionados.

## Arquitetura

![Arquitetura do Checkpoint 2](docs/arquitetura.svg)

> Diagrama editável em [`docs/arquitetura.drawio`](docs/arquitetura.drawio) (abra no [draw.io](https://app.diagrams.net)).

## Provedor Utilizado
* AWS (AWS Lambda + Amazon SNS + Amazon DynamoDB)

## Como rodar localmente

### Pré-requisitos
* Python instalado (versão 3.9 ou superior)
* Terminal de comandos aberto

### Passo a passo
1. Clone o repositório para sua máquina: 
   git clone https://github.com/AmandaAzevedo/cloud-serverless-checkpoint.git

2. Entre na pasta do projeto:
   cd cloud-serveless-checkpoint

3. Instale as dependências do projeto:
   (não há dependências — a função usa apenas a biblioteca padrão do Python)

4. Rode os testes locais:
   python3 -m unittest -v

## Como testar na nuvem

Endpoints públicos para teste:

* Selecionar aluno: `POST https://endereco-lambda-1.lambda-url.us-east-1.on.aws/v1/selecionar`
* Listar alunos: `GET  https://endereco-lambda-2.lambda-url.us-east-1.on.aws/v1/alunos`

Selecionar um aluno (dispara o fluxo, resposta assíncrona `202`):

    curl -X POST "https://endereco-lambda-1.lambda-url.us-east-1.on.aws/v1/selecionar" \
      -H "Content-Type: application/json" \
      -d '{"nome":"Nome"}'

Listar todos os alunos e suas casas:

    curl "https://endereco-lambda-2.lambda-url.us-east-1.on.aws/v1/alunos"

> As URLs também são impressas como outputs do Terraform (`http_endpoint` e `list_endpoint`).

## Deploy na nuvem (Terraform)

Requer Terraform e AWS CLI configurado (`aws configure`).

    cd cp2/terraform
    cp backend.tf.example backend.tf   # ajuste o nome do bucket (state no S3)
    terraform init
    terraform apply

Após o `apply`, habilite o acesso público das Function URLs pelo Console (a AWS
não permite fazer isso por Terraform nesta conta): em Lambda → função →
Configuration → Function URL → Edit → Auth type NONE, para `chapeu-seletor-publisher`
e `chapeu-seletor-lister`. Sem isso, o `curl` retorna 403.
