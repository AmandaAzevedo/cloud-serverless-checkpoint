"""Testes unitários das funções produtora, consumidora e listadora.

Rodar com:  python -m unittest   (ou  python -m pytest)
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import lambda_function
from lambda_function import (
    CASAS,
    ROTA_ALUNOS,
    ROTA_SELECIONAR,
    lambda_handler,
    lister_handler,
    publisher_handler,
    selecionar_casa,
)


def _evento_sns(*mensagens):
    return {"Records": [{"Sns": {"Message": m}} for m in mensagens]}


def _evento_http(metodo, caminho, corpo=None):
    event = {"requestContext": {"http": {"method": metodo, "path": caminho}}, "rawPath": caminho}
    if corpo is not None:
        event["body"] = corpo
    return event


class TestConsumidora(unittest.TestCase):
    def test_retorna_uma_casa_valida(self):
        for _ in range(50):
            self.assertIn(selecionar_casa("Amanda"), CASAS)

    def test_processa_e_ignora_sem_gravar_quando_sem_tabela(self):
        # Sem TABLE_NAME no ambiente, não tenta gravar no DynamoDB.
        resultado = lambda_handler(_evento_sns(json.dumps({"nome": "Amanda"})), None)
        self.assertEqual(resultado["processados"], 1)
        self.assertIn(resultado["resultados"][0]["casa"], CASAS)

    @patch.dict("os.environ", {"TABLE_NAME": "alunos-selecionados"})
    def test_grava_no_dynamodb(self):
        fake_db = MagicMock()
        with patch.object(lambda_function, "_dynamodb_client", return_value=fake_db):
            lambda_handler(_evento_sns(json.dumps({"nome": "Acerola"})), None)
        fake_db.put_item.assert_called_once()
        item = fake_db.put_item.call_args.kwargs["Item"]
        self.assertEqual(item["nome"]["S"], "Acerola")
        self.assertIn(item["casa"]["S"], CASAS)

    def test_mensagem_sem_nome_e_ignorada(self):
        self.assertEqual(lambda_handler(_evento_sns("{}"), None)["processados"], 0)


class TestProdutora(unittest.TestCase):
    @patch.dict("os.environ", {"TOPIC_ARN": "arn:aws:sns:us-east-1:000:alunos"})
    def test_publica_e_retorna_202(self):
        fake_sns = MagicMock()
        fake_sns.publish.return_value = {"MessageId": "abc-123"}
        with patch.object(lambda_function, "_sns_client", return_value=fake_sns):
            resposta = publisher_handler(
                _evento_http("POST", ROTA_SELECIONAR, json.dumps({"nome": "Amanda"})), None
            )
        self.assertEqual(resposta["statusCode"], 202)
        self.assertEqual(json.loads(resposta["body"])["messageId"], "abc-123")

    def test_sem_nome_retorna_400(self):
        resposta = publisher_handler(_evento_http("POST", ROTA_SELECIONAR, "{}"), None)
        self.assertEqual(resposta["statusCode"], 400)

    def test_get_retorna_405(self):
        resposta = publisher_handler(_evento_http("GET", ROTA_SELECIONAR), None)
        self.assertEqual(resposta["statusCode"], 405)


class TestListadora(unittest.TestCase):
    @patch.dict("os.environ", {"TABLE_NAME": "alunos-selecionados"})
    def test_lista_alunos(self):
        fake_db = MagicMock()
        fake_db.scan.return_value = {
            "Items": [
                {"nome": {"S": "Harry"}, "casa": {"S": "Grifinória"}},
                {"nome": {"S": "Amanda"}, "casa": {"S": "Corvinal"}},
            ]
        }
        with patch.object(lambda_function, "_dynamodb_client", return_value=fake_db):
            resposta = lister_handler(_evento_http("GET", ROTA_ALUNOS), None)
        self.assertEqual(resposta["statusCode"], 200)
        corpo = json.loads(resposta["body"])
        self.assertEqual(corpo["total"], 2)
        # Ordenado por nome.
        self.assertEqual(corpo["alunos"][0]["nome"], "Amanda")

    def test_post_retorna_405(self):
        resposta = lister_handler(_evento_http("POST", ROTA_ALUNOS), None)
        self.assertEqual(resposta["statusCode"], 405)

    def test_rota_errada_retorna_404(self):
        resposta = lister_handler(_evento_http("GET", "/v1/outra"), None)
        self.assertEqual(resposta["statusCode"], 404)


if __name__ == "__main__":
    unittest.main()
