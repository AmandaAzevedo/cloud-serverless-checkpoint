# Checkpoint 1 - Chapéu Seletor Serverless

Este projeto contém uma função serverless simples que responde a requisições HTTP
e foi implantada em ambiente de nuvem. A função recebe o nome de um aluno e
sorteia a casa de Hogwarts dele (Grifinória, Sonserina, Corvinal ou Lufa-Lufa),
retornando o resultado em JSON.

## Provedor Utilizado
* AWS (AWS Lambda + Function URL)

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

## Como chamar a função publicada

Endpoint: POST /v1/selecionar

    curl -X POST "https://endereco-da-lambda.lambda-url.us-east-1.on.aws/v1/selecionar" \
      -H "Content-Type: application/json" \
      -d '{"nome":"Nome"}'

Resposta:

    { "nome": "Nome", "casa": "Corvinal" }

## Deploy na nuvem (Terraform)

Requer Terraform e AWS CLI configurado (`aws configure`).

O state fica em um bucket S3. Como o `backend.tf` leva o nome do bucket (com o
Account ID), ele não é versionado — configure o seu a partir do exemplo:

    cd cp1/terraform
    cp backend.tf.example backend.tf
    # edite o nome do bucket em backend.tf

    terraform init
    terraform apply
