"""Testes unitários da lógica de seleção e do handler do Chapéu Seletor.

Rodar com:  python -m unittest   (ou  python -m pytest)
"""

import json
import unittest

from lambda_function import CASAS, ROTA, lambda_handler, selecionar_casa


def _evento(metodo="POST", caminho=ROTA, corpo=None):
    """Monta um evento no formato Lambda Function URL (payload v2.0)."""
    event = {"requestContext": {"http": {"method": metodo, "path": caminho}}, "rawPath": caminho}
    if corpo is not None:
        event["body"] = corpo
    return event


class TestChapeuSeletor(unittest.TestCase):
    def test_retorna_uma_casa_valida(self):
        # Toda seleção deve ser uma das quatro casas de Hogwarts.
        for _ in range(50):
            self.assertIn(selecionar_casa("Amanda"), CASAS)

    def test_selecao_cobre_varias_casas(self):
        # Sendo aleatória, várias chamadas devem cair em mais de uma casa.
        casas_encontradas = {selecionar_casa("Amanda") for _ in range(200)}
        self.assertGreater(len(casas_encontradas), 1)

    def test_post_valido(self):
        resposta = lambda_handler(_evento(corpo=json.dumps({"nome": "Amanda"})), None)
        self.assertEqual(resposta["statusCode"], 200)
        corpo = json.loads(resposta["body"])
        self.assertEqual(corpo["nome"], "Amanda")
        self.assertIn(corpo["casa"], CASAS)

    def test_post_sem_nome_retorna_400(self):
        resposta = lambda_handler(_evento(corpo="{}"), None)
        self.assertEqual(resposta["statusCode"], 400)

    def test_get_retorna_405(self):
        # A rota existe, mas só aceita POST.
        resposta = lambda_handler(_evento(metodo="GET"), None)
        self.assertEqual(resposta["statusCode"], 405)
        self.assertEqual(resposta["headers"].get("Allow"), "POST")

    def test_rota_desconhecida_retorna_404(self):
        resposta = lambda_handler(_evento(caminho="/outra", corpo=json.dumps({"nome": "X"})), None)
        self.assertEqual(resposta["statusCode"], 404)

    def test_caminho_com_barra_final_funciona(self):
        # /v1/selecionar/ deve ser tratado igual a /v1/selecionar.
        resposta = lambda_handler(_evento(caminho=ROTA + "/", corpo=json.dumps({"nome": "Luna"})), None)
        self.assertEqual(resposta["statusCode"], 200)


if __name__ == "__main__":
    unittest.main()
