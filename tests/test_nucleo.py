"""Testes do núcleo jurídico. Sem rede e sem chave de IA."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

_RAIZ = Path(tempfile.mkdtemp(prefix="xthemis-test-"))
os.environ["DATA_DIR"] = str(_RAIZ)
os.environ["WEB_MODE"] = "1"

import contas  # noqa: E402
import docx_out  # noqa: E402
import extractor  # noqa: E402
import memory  # noqa: E402
import prazos  # noqa: E402
import prompts  # noqa: E402
from app import area_do_processo  # noqa: E402


class Prazos(unittest.TestCase):
    def test_pascoa_2026(self):
        self.assertEqual(prazos._pascoa(2026), date(2026, 4, 5))

    def test_sexta_da_paixao_nao_conta(self):
        self.assertFalse(prazos.dia_util(date(2026, 4, 3), "regional"))

    def test_recesso_nao_conta(self):
        self.assertFalse(prazos.dia_util(date(2026, 1, 5), "regional"))
        self.assertTrue(prazos.dia_util(date(2026, 1, 21), "regional"))

    def test_exclui_o_dia_da_ciencia(self):
        conta = prazos.calcular("2026-03-02", "ciencia", "outro", 1, "regional")
        self.assertEqual(conta["vencimento"], "2026-03-03")
        self.assertEqual(conta["dias"], 1)

    def test_recurso_ordinario_oito_dias(self):
        conta = prazos.calcular("2026-03-02", "ciencia", "recurso", None, "regional")
        self.assertEqual(conta["dias"], 8)
        self.assertEqual(conta["vencimento"], "2026-03-12")
        self.assertIn("CLT", conta["fundamento"])

    def test_carnaval_do_trt_sai_da_conta_trabalhista(self):
        conta = prazos.calcular("2026-02-13", "ciencia", "recurso", None, "regional")
        self.assertEqual(conta["vencimento"], "2026-03-02")
        self.assertTrue(any("16/02/2026" in item for item in conta["pulados"]))

    def test_feriado_de_cotia_nao_vale_para_a_regiao(self):
        dia = date(2026, 9, 8)
        self.assertFalse(prazos.dia_util(dia, "cotia"))
        self.assertTrue(prazos.dia_util(dia, "regional"))

    def test_suspensao_do_trt_nao_entra_em_familia(self):
        dia = date(2026, 6, 5)
        self.assertFalse(prazos.dia_util(dia, "regional", "trabalhista"))
        self.assertTrue(prazos.dia_util(dia, "regional", "familia"))

    def test_apelacao_de_familia_e_quinze_dias_do_cpc(self):
        conta = prazos.calcular("2026-03-02", "ciencia", "recurso", None, "regional", "familia")
        self.assertEqual(conta["dias"], 15)
        self.assertEqual(conta["area"], "familia")
        self.assertIn("CPC", conta["fundamento"])
        self.assertNotIn("CLT", conta["fundamento"])
        self.assertNotIn("Portaria GP", conta["aviso"])

    def test_carnaval_do_trt_nao_encurta_prazo_civel(self):
        conta = prazos.calcular("2026-02-13", "ciencia", "outro", 1, "regional", "civel")
        self.assertEqual(conta["vencimento"], "2026-02-16")
        self.assertFalse(any("16/02/2026" in item for item in conta["pulados"]))

    def test_data_invalida(self):
        with self.assertRaises(ValueError):
            prazos.calcular("13/02/2026", "ciencia", "recurso", None, "regional")

    def test_comarca_sai_da_vara(self):
        self.assertEqual(prazos.comarca_do_processo({}, "1ª Vara do Trabalho de Cotia"), "cotia")
        self.assertEqual(
            prazos.comarca_do_processo({"numero": "0053278-93.2012.8.26.0001"}, "Foro Regional I Santana"),
            "regional",
        )


class Area(unittest.TestCase):
    def test_cnj_trabalhista(self):
        self.assertEqual(
            area_do_processo({"numero": "1000526-16.2026.5.02.0241"}, ""),
            "trabalhista",
        )

    def test_familia_pela_vara(self):
        self.assertEqual(
            area_do_processo(
                {"numero": "0053278-93.2012.8.26.0001"},
                "2ª Vara da Família e Sucessões",
            ),
            "familia",
        )


class Nomes(unittest.TestCase):
    def test_resumo_com_representacao(self):
        texto = (
            "Exequente/Requerente: Enzo Nardoni, representado por sua genitora "
            "Gislaine Cristina Machado Geraldo.\n"
            "Executado/Requerido: Fábio Nardoni de Oliveira."
        )
        self.assertEqual(
            extractor.partes_no_texto(texto),
            ("Enzo Nardoni", "Fábio Nardoni de Oliveira"),
        )

    def test_frase_de_lei_nao_e_nome(self):
        self.assertEqual(extractor._limpa_parte("Nos termos do art. 319 do CPC, a parte autora requer"), "")
        self.assertFalse(extractor._parece_nome("NÃO CONSTA DO EXTRATO LIDO"))


class Posicao(unittest.TestCase):
    def test_familia_pelo_requerente(self):
        texto = prompts.aplicar_posicao(
            "Peça pela RECLAMADA. advogado da RECLAMADA.",
            "reclamante",
            "familia",
        )
        self.assertIn("REQUERENTE", texto)
        self.assertNotIn("pela RECLAMADA", texto)

    def test_juizo_nao_advoga(self):
        texto = prompts.aplicar_posicao("Peça pela RECLAMADA.", "juizo", "trabalhista")
        self.assertIn("JUÍZO", texto)
        self.assertNotIn("pela RECLAMADA", texto)


class PdfDoJuiz(unittest.TestCase):
    def test_tira_checklist_e_auditoria(self):
        bruto = "DOS FATOS\n\nO autor pediu.\n\nAUDITORIA DOCUMENTAL\nfalta folha\n\nCHECKLIST FORENSE\n- item"
        limpo = docx_out.limpar_para_juiz(bruto)
        self.assertIn("DOS FATOS", limpo)
        self.assertIn("O autor pediu.", limpo)
        self.assertNotIn("CHECKLIST", limpo)
        self.assertNotIn("AUDITORIA", limpo)


class Aprendizado(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(_RAIZ / "aprendizado", ignore_errors=True)
        self.caso_a = _RAIZ / "caso-a"
        self.caso_b = _RAIZ / "caso-b"
        self.caso_a.mkdir(exist_ok=True)
        self.caso_b.mkdir(exist_ok=True)

    def test_nota_do_processo_nao_vaza_para_outro(self):
        memory.append_learning(
            self.caso_a, "defesa", "O filho se chama Enzo.", also_global=False, user_id="u"
        )
        memory.append_learning(
            self.caso_a, "defesa", "Sempre citar a folha.", also_global=True, user_id="u"
        )
        bloco = memory.combined_instructions(self.caso_b, "defesa", "", "u")
        self.assertIn("Sempre citar a folha.", bloco)
        self.assertNotIn("Enzo", bloco)

    def test_tirar_do_global_deixa_o_processo(self):
        memory.append_learning(self.caso_a, "defesa", "Citar a folha.", also_global=True, user_id="u")
        memory.remover_aprendizado(self.caso_a, "Citar a folha.", onde="global", user_id="u")
        self.assertIn("Citar a folha.", memory.load_case_prompts(self.caso_a)["geral"])
        self.assertEqual(memory.load_global("u")["todos"], [])


class Contas(unittest.TestCase):
    def setUp(self):
        if contas.USERS.exists():
            contas.USERS.unlink()

    def test_primeiro_logado_vira_administrador(self):
        self.assertEqual(contas.garantir_dono({"id": "fabio", "nome": "Fabio"}), "dono")
        self.assertEqual(contas.acesso("fabio"), "dono")

    def test_outro_perfil_nao_rouba_o_admin(self):
        contas.garantir_dono({"id": "fabio", "nome": "Fabio"})
        self.assertEqual(contas.garantir_dono({"id": "teste", "nome": "Teste"}), "avulso")
        self.assertEqual(contas.acesso("fabio"), "dono")


if __name__ == "__main__":
    unittest.main()
