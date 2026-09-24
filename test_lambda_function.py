"""Testes unitários da API e do workflow do projeto final.

Rodar com:  python -m unittest   (ou  python -m pytest)
"""

import base64
import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import lambda_function
from lambda_function import ROTA_ALUNOS, ROTA_SELECIONAR, ROTA_VERSAO, VERSAO, lambda_handler


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
        self.assertEqual(entrada["alunos"][0]["perfil"], "Não informadas.")

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

    def test_json_invalido_retorna_400(self):
        resp = lambda_handler(_evento("POST", ROTA_SELECIONAR, "{"), None)
        self.assertEqual(resp["statusCode"], 400)

    def test_email_invalido_retorna_400(self):
        resp = lambda_handler(
            _evento("POST", ROTA_SELECIONAR, json.dumps({"nome": "Amanda", "email": "invalido"})), None
        )
        self.assertEqual(resp["statusCode"], 400)

    def test_lote_acima_do_limite_retorna_400(self):
        alunos = [{"nome": f"Aluno {i}", "email": f"a{i}@x.com"} for i in range(26)]
        resp = lambda_handler(_evento("POST", ROTA_SELECIONAR, json.dumps({"alunos": alunos})), None)
        self.assertEqual(resp["statusCode"], 400)

    @patch.dict("os.environ", {"STATE_MACHINE_ARN": "arn:sfn"})
    def test_caracteristicas_sao_enviadas_para_ia(self):
        fake_sfn = MagicMock()
        fake_sfn.start_sync_execution.return_value = {"status": "SUCCEEDED", "output": "[]"}
        with patch.object(lambda_function, "_sfn_client", return_value=fake_sfn):
            lambda_handler(
                _evento(
                    "POST",
                    ROTA_SELECIONAR,
                    json.dumps(
                        {
                            "nome": "Amanda",
                            "email": "A@B.COM",
                            "caracteristicas": "curiosa e estudiosa",
                        }
                    ),
                ),
                None,
            )
        entrada = json.loads(fake_sfn.start_sync_execution.call_args.kwargs["input"])
        self.assertEqual(entrada["alunos"][0]["email"], "a@b.com")
        self.assertEqual(entrada["alunos"][0]["perfil"], "curiosa e estudiosa")

    @patch.dict("os.environ", {"STATE_MACHINE_ARN": "arn:sfn"})
    def test_falha_ao_iniciar_fluxo_retorna_503(self):
        fake_sfn = MagicMock()
        fake_sfn.start_sync_execution.side_effect = RuntimeError("segredo interno")
        with patch.object(lambda_function, "_sfn_client", return_value=fake_sfn):
            resp = lambda_handler(
                _evento("POST", ROTA_SELECIONAR, json.dumps({"nome": "Amanda", "email": "a@b.com"})), None
            )
        self.assertEqual(resp["statusCode"], 503)
        self.assertNotIn("segredo interno", resp["body"])

    @patch.dict("os.environ", {"STATE_MACHINE_ARN": "arn:sfn"})
    def test_corpo_base64(self):
        fake_sfn = MagicMock()
        fake_sfn.start_sync_execution.return_value = {"status": "SUCCEEDED", "output": "[]"}
        corpo = base64.b64encode(json.dumps({"nome": "Amanda", "email": "a@b.com"}).encode()).decode()
        evento = _evento("POST", ROTA_SELECIONAR, corpo)
        evento["isBase64Encoded"] = True
        with patch.object(lambda_function, "_sfn_client", return_value=fake_sfn):
            resp = lambda_handler(evento, None)
        self.assertEqual(resp["statusCode"], 200)

    def test_metodo_errado_retorna_405(self):
        resp = lambda_handler(_evento("GET", ROTA_SELECIONAR), None)
        self.assertEqual(resp["statusCode"], 405)


class TestListar(unittest.TestCase):
    @patch.dict("os.environ", {"TABLE_NAME": "t"})
    def test_get_lista_alunos(self):
        fake_db = MagicMock()
        fake_db.scan.side_effect = [
            {
                "Items": [{"nome": {"S": "Harry"}, "casa": {"S": "Grifinória"}}],
                "LastEvaluatedKey": {"email": {"S": "h@x.com"}},
            },
            {"Items": [{"nome": {"S": "Amanda"}, "casa": {"S": "Corvinal"}}]},
        ]
        with patch.object(lambda_function, "_dynamodb_client", return_value=fake_db):
            resp = lambda_handler(_evento("GET", ROTA_ALUNOS), None)
        self.assertEqual(resp["statusCode"], 200)
        corpo = json.loads(resp["body"])
        self.assertEqual(corpo["total"], 2)
        self.assertEqual(corpo["alunos"][0]["nome"], "Amanda")  # ordenado
        fake_db.scan.assert_any_call(TableName="t", ExclusiveStartKey={"email": {"S": "h@x.com"}})

    def test_metodo_errado_retorna_405(self):
        resp = lambda_handler(_evento("POST", ROTA_ALUNOS), None)
        self.assertEqual(resp["statusCode"], 405)


class TestVersao(unittest.TestCase):
    @patch.dict("os.environ", {"APP_VERSION": "abc1234"})
    def test_get_versao(self):
        resp = lambda_handler(_evento("GET", ROTA_VERSAO), None)
        self.assertEqual(resp["statusCode"], 200)
        corpo = json.loads(resp["body"])
        self.assertEqual(corpo["versao"], VERSAO)
        self.assertEqual(corpo["commit"], "abc1234")

    def test_versao_metodo_errado_retorna_405(self):
        resp = lambda_handler(_evento("POST", ROTA_VERSAO), None)
        self.assertEqual(resp["statusCode"], 405)


class TestRoteamento(unittest.TestCase):
    def test_rota_desconhecida_retorna_404(self):
        resp = lambda_handler(_evento("GET", "/v1/outra"), None)
        self.assertEqual(resp["statusCode"], 404)


class TestStateMachine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        caminho = Path(__file__).with_name("statemachine.asl.json")
        cls.definition = json.loads(caminho.read_text(encoding="utf-8"))
        cls.states = cls.definition["States"]["Processar"]["ItemProcessor"]["States"]

    def test_transicoes_referenciam_estados_existentes(self):
        destinos = []
        for estado in self.states.values():
            if "Next" in estado:
                destinos.append(estado["Next"])
            if "Default" in estado:
                destinos.append(estado["Default"])
            destinos.extend(escolha["Next"] for escolha in estado.get("Choices", []))
            destinos.extend(captura["Next"] for captura in estado.get("Catch", []))
        self.assertFalse(set(destinos) - set(self.states))

    def test_fallback_inclui_as_quatro_casas(self):
        expressao = self.states["SortearFallback"]["Parameters"]["indice.$"]
        self.assertEqual(expressao, "States.MathRandom(0, 4)")

    def test_evento_de_dominio_e_publicado_no_sns(self):
        publicar = self.states["PublicarEvento"]
        self.assertEqual(publicar["Resource"], "arn:aws:states:::sns:publish")
        self.assertEqual(publicar["Parameters"]["Subject"], "AlunoSelecionado")

    def test_mensagens_da_dlq_sao_serializadas(self):
        estados_dlq = ["EventoParaDLQ", "AtualizacaoParaDLQ", "NotificacaoParaDLQ"]
        for nome in estados_dlq:
            self.assertEqual(
                self.states[nome]["Parameters"]["MessageBody.$"],
                "States.JsonToString($)",
            )


if __name__ == "__main__":
    unittest.main()
