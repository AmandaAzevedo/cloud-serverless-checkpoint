"""Testes unitários da Lambda única do Checkpoint 3.

Rodar com:  python -m unittest   (ou  python -m pytest)
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import lambda_function
from lambda_function import ROTA_ALUNOS, ROTA_SELECIONAR, lambda_handler


def _evento(metodo, caminho, corpo=None):
    event = {"requestContext": {"http": {"method": metodo, "path": caminho}}, "rawPath": caminho}
    if corpo is not None:
        event["body"] = corpo
    return event


class TestSelecionar(unittest.TestCase):
    @patch.dict("os.environ", {"STATE_MACHINE_ARN": "arn:sfn"})
    def test_post_inicia_fluxo_e_retorna_resultado(self):
        fake_sfn = MagicMock()
        # A state machine (Map) devolve uma lista; para 1 nome, a Lambda desembrulha.
        fake_sfn.start_sync_execution.return_value = {
            "status": "SUCCEEDED",
            "output": json.dumps([{"nome": "Amanda", "casa": "Corvinal", "idempotente": False}]),
        }
        with patch.object(lambda_function, "_sfn_client", return_value=fake_sfn):
            resp = lambda_handler(
                _evento("POST", ROTA_SELECIONAR, json.dumps({"nome": "Amanda", "email": "a@b.com"})), None
            )
        self.assertEqual(resp["statusCode"], 200)
        corpo = json.loads(resp["body"])
        self.assertEqual(corpo["resultado"]["casa"], "Corvinal")
        entrada = json.loads(fake_sfn.start_sync_execution.call_args.kwargs["input"])
        self.assertEqual(len(entrada["alunos"]), 1)
        self.assertEqual(entrada["alunos"][0]["email"], "a@b.com")

    @patch.dict("os.environ", {"STATE_MACHINE_ARN": "arn:sfn"})
    def test_email_e_repassado(self):
        fake_sfn = MagicMock()
        fake_sfn.start_sync_execution.return_value = {"status": "SUCCEEDED", "output": "[]"}
        with patch.object(lambda_function, "_sfn_client", return_value=fake_sfn):
            lambda_handler(
                _evento("POST", ROTA_SELECIONAR, json.dumps({"nome": "Amanda", "email": "a@b.com"})),
                None,
            )
        entrada = json.loads(fake_sfn.start_sync_execution.call_args.kwargs["input"])
        self.assertEqual(entrada["alunos"][0]["email"], "a@b.com")

    @patch.dict("os.environ", {"STATE_MACHINE_ARN": "arn:sfn"})
    def test_post_lote(self):
        fake_sfn = MagicMock()
        fake_sfn.start_sync_execution.return_value = {"status": "SUCCEEDED", "output": "[]"}
        alunos = [
            {"nome": "A", "email": "a@x.com"},
            {"nome": "B", "email": "b@x.com"},
            {"nome": "C", "email": "c@x.com"},
        ]
        with patch.object(lambda_function, "_sfn_client", return_value=fake_sfn):
            lambda_handler(_evento("POST", ROTA_SELECIONAR, json.dumps({"alunos": alunos})), None)
        entrada = json.loads(fake_sfn.start_sync_execution.call_args.kwargs["input"])
        self.assertEqual(len(entrada["alunos"]), 3)
        self.assertTrue(all(a["email"] for a in entrada["alunos"]))

    @patch.dict("os.environ", {"STATE_MACHINE_ARN": "arn:sfn"})
    def test_falha_do_fluxo_retorna_502(self):
        fake_sfn = MagicMock()
        fake_sfn.start_sync_execution.return_value = {"status": "FAILED", "error": "X", "cause": "Y"}
        with patch.object(lambda_function, "_sfn_client", return_value=fake_sfn):
            resp = lambda_handler(
                _evento("POST", ROTA_SELECIONAR, json.dumps({"nome": "Amanda", "email": "a@b.com"})), None
            )
        self.assertEqual(resp["statusCode"], 502)

    def test_sem_email_retorna_400(self):
        resp = lambda_handler(_evento("POST", ROTA_SELECIONAR, json.dumps({"nome": "Amanda"})), None)
        self.assertEqual(resp["statusCode"], 400)

    def test_sem_nome_retorna_400(self):
        resp = lambda_handler(_evento("POST", ROTA_SELECIONAR, "{}"), None)
        self.assertEqual(resp["statusCode"], 400)

    def test_metodo_errado_retorna_405(self):
        resp = lambda_handler(_evento("GET", ROTA_SELECIONAR), None)
        self.assertEqual(resp["statusCode"], 405)


class TestListar(unittest.TestCase):
    @patch.dict("os.environ", {"TABLE_NAME": "t"})
    def test_get_lista_alunos(self):
        fake_db = MagicMock()
        fake_db.scan.return_value = {
            "Items": [
                {"nome": {"S": "Harry"}, "casa": {"S": "Grifinória"}},
                {"nome": {"S": "Amanda"}, "casa": {"S": "Corvinal"}},
            ]
        }
        with patch.object(lambda_function, "_dynamodb_client", return_value=fake_db):
            resp = lambda_handler(_evento("GET", ROTA_ALUNOS), None)
        self.assertEqual(resp["statusCode"], 200)
        corpo = json.loads(resp["body"])
        self.assertEqual(corpo["total"], 2)
        self.assertEqual(corpo["alunos"][0]["nome"], "Amanda")  # ordenado

    def test_metodo_errado_retorna_405(self):
        resp = lambda_handler(_evento("POST", ROTA_ALUNOS), None)
        self.assertEqual(resp["statusCode"], 405)


class TestRoteamento(unittest.TestCase):
    def test_rota_desconhecida_retorna_404(self):
        resp = lambda_handler(_evento("GET", "/v1/outra"), None)
        self.assertEqual(resp["statusCode"], 404)


if __name__ == "__main__":
    unittest.main()
