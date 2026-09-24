# Checkpoint 3 - Chapéu Seletor Serverless (Orquestração)

Este projeto evolui o Checkpoint 2 para uma orquestração de serviços com o AWS
Step Functions (equivalente ao Google Cloud Workflows). Uma **única Lambda**
expõe os endpoints HTTP; toda a lógica de negócio roda **dentro do Step Functions
com integrações nativas** — sem Lambda no fluxo. O cadastro exige **nome e e-mail**,
o **e-mail é único** na base, e o aluno é **notificado por e-mail** (SES).

* `POST /v1/selecionar` → a Lambda inicia a execução do fluxo e devolve o resultado.
* `GET  /v1/alunos`     → a Lambda lista os alunos gravados (lê o DynamoDB).

Dentro do Step Functions (tudo nativo, sem Lambda), na ordem:
* **Map** — processa vários alunos (lote) numa única execução;
* **Sortear** (`States.MathRandom`) → escolhe a casa;
* **Choice** — ramifica por casa, atribuindo um lema a cada uma;
* **Persistir** (`dynamodb:putItem` com `attribute_not_exists(email)`) — **idempotência / e-mail único**;
* **Notificar** (`ses:sendEmail`) → envia o resultado para o e-mail do aluno;
* **MarcarNotificado** (`dynamodb:updateItem`) → em caso de sucesso, marca `notificado = true`;
* **Retry** no envio do e-mail e, se ainda assim falhar, **rollback** (`dynamodb:deleteItem`)
  + **Catch → SQS DLQ** — o cadastro é **desfeito** (transação compensatória).

## Regras de cadastro
* **E-mail obrigatório:** requisição sem `nome` e `email` retorna `400`.
* **E-mail único:** e-mail já cadastrado retorna `status: "duplicado"` (não regrava).
* **Notificação obrigatória:** se o e-mail não for enviado, o cadastro é **desfeito**
  (`status: "cancelado"`); só permanecem na base alunos que foram notificados.
* A listagem inclui `notificado` (true/false) de cada aluno.

## Arquitetura

![Arquitetura do Checkpoint 3](docs/arquitetura.svg)

> Diagrama editável em [`docs/arquitetura.drawio`](docs/arquitetura.drawio) (abra no [draw.io](https://app.diagrams.net)).
> A definição do fluxo está em [`statemachine.asl.json`](statemachine.asl.json).

## Provedor Utilizado
* AWS (Step Functions + Lambda + DynamoDB + SQS + SES)

## Como rodar localmente

### Pré-requisitos
* Python instalado (versão 3.9 ou superior)
* Terminal de comandos aberto

### Passo a passo
1. Clone o repositório para sua máquina: git clone https://github.com/AmandaAzevedo/cloud-serverless-checkpoint.git

2. Entre na pasta do projeto: cd cloud-serveless-checkpoint

3. Instale as dependências do projeto:
   (não há dependências — a função usa apenas a biblioteca padrão do Python)

4. Rode os testes locais:
   python3 -m unittest -v

## Como testar na nuvem

As URLs (`<selecionar_endpoint>` e `<list_endpoint>`) são a mesma Function URL
com caminhos diferentes, impressas como outputs do Terraform.

**Cadastrar um aluno** (nome + e-mail obrigatórios) — executa o fluxo e notifica:

    curl -X POST "<selecionar_endpoint>" -H "Content-Type: application/json" \
      -d '{"nome":"Nome","email":"meuemailvalido@exemplo.com"}'
    # {"status":"ok","resultado":{"status":"cadastrado","notificado":true,"casa":"Corvinal","nome":"Nome","email":"meuemailvalido@exemplo.com","lema":"..."}}

**E-mail único** — repetir o mesmo e-mail não regrava:

    curl -X POST "<selecionar_endpoint>" -H "Content-Type: application/json" \
      -d '{"nome":"Outra","email":"meuemailvalido@exemplo.com"}'
    # {"status":"ok","resultado":{"status":"duplicado","mensagem":"E-mail já cadastrado."}}

**E-mail obrigatório** — sem e-mail retorna 400:

    curl -X POST "<selecionar_endpoint>" -H "Content-Type: application/json" -d '{"nome":"Nome"}'
    # {"erro":"'nome' e 'email' são obrigatórios."}

**Lote (Map)** — vários alunos numa execução:

    curl -X POST "<selecionar_endpoint>" -H "Content-Type: application/json" \
      -d '{"alunos":[{"nome":"Fred","email":"fred@x.com"},{"nome":"Jorge","email":"jorge@x.com"}]}'

**Retry + rollback + DLQ** — cadastre com um e-mail **não verificado** (em sandbox,
o envio falha): a notificação é reenviada (retry) e, ao falhar, o cadastro é
**desfeito** (rollback) e a mensagem vai para a DLQ.

    curl -X POST "<selecionar_endpoint>" -H "Content-Type: application/json" \
      -d '{"nome":"Fantasma","email":"nao-verificado@exemplo.com"}'
    # {"status":"ok","resultado":{"status":"cancelado","motivo":"Falha no envio do e-mail; cadastro desfeito.","enviadoParaDLQ":true,...}}

**Listar os alunos gravados** (nome, e-mail, casa, notificado):

    curl "<list_endpoint>"
    # {"total":1,"alunos":[{"nome":"Nome","email":"...","casa":"...","notificado":true,...}]}

## Conceitos de orquestração demonstrados

Cada execução é registrada em CloudWatch (`/aws/vendedlogs/states/chapeu-seletor-cp3`)
e visível no console do Step Functions.

| Conceito | Como é demonstrado | Evidência |
|---|---|---|
| Chamar na ordem correta | `Sortear → EscolherCasa → Choice → Persistir → Notificar → Sucesso` | histórico da execução |
| Gerenciar respostas | saída de um estado alimenta o próximo; execução devolve o resultado | output da execução |
| Idempotência | `attribute_not_exists(email)`; duplicado → `EmailDuplicado` | `status: "duplicado"` |
| Retry | política `Retry` com backoff no envio do e-mail | tentativas no histórico |
| Rollback (compensação) | e-mail falha → `DesfazerCadastro` (`dynamodb:deleteItem`) | `status: "cancelado"`; aluno some da listagem |
| Dead-letter queue | falha no envio do e-mail → `Catch → sqs:sendMessage` → `chapeu-seletor-cp3-dlq` | mensagem na SQS (`Ses.MessageRejectedException`) |

## Notificação por e-mail (SES)

O estado `Notificar` usa o Amazon SES. Como a conta inicia em **sandbox**:
* o **remetente** (`sender_email`) precisa ser verificado no SES;
* enquanto em sandbox, o **destinatário** também precisa ser verificado
  (para enviar a qualquer e-mail, solicite *production access* no console do SES).

Quando o envio falha (ex.: destinatário não verificado), o fluxo faz `Retry` e,
persistindo a falha, **desfaz o cadastro** (`dynamodb:deleteItem`) e envia a
mensagem para a **DLQ** via `Catch` — o aluno **não permanece** na base
(`status: cancelado`). Assim, só ficam cadastrados os alunos efetivamente
notificados.

## Deploy na nuvem (Terraform)

Requer Terraform e AWS CLI configurado (`aws configure`).

    cd cp3/terraform
    cp backend.tf.example backend.tf   # ajuste o nome do bucket (state no S3)
    # em terraform.tfvars, defina sender_email = "seu-email-verificado@dominio.com"
    terraform init
    terraform apply

Passos manuais após o `apply`:
1. **Function URL pública:** Lambda → `chapeu-seletor-cp3-api` → Configuration →
   Function URL → Edit → Auth type NONE (senão o `curl` retorna 403).
2. **Verificar o remetente SES:** clique no link do e-mail de verificação enviado
   pela AWS para o `sender_email`.
