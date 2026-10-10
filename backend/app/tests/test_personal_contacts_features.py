"""Focused, dependency-free checks for Maia's personal-contact operations."""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "mcp" / "personal_contacts.py"


def test_personal_contacts_cannot_start_as_separate_mcp():
    env = {**os.environ, "FORGEHUB_AGENT_SLUG": "maia"}
    result = subprocess.run(
        [sys.executable, str(MODULE)], capture_output=True, text=True, env=env, timeout=2,
    )
    assert result.returncode != 0
    assert "ForgeHub" in result.stderr
spec = importlib.util.spec_from_file_location("personal_contacts_features", MODULE)
contacts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contacts)


class PersonalContactFeaturesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        contacts.BASE = Path(self.temp.name)

    def test_create_category_and_use_it(self):
        self.assertIn("colaboradores", contacts.create_category("Colaboradores"))
        self.assertEqual(contacts.create_category("Colaboradores").count("colaboradores"), 1)
        saved = contacts.upsert_contact("+55 (21) 99897-5416", nome="Exemplo", categoria="Colaboradores")
        self.assertEqual(saved["categoria"], "colaboradores")
        self.assertIn("colaboradores", contacts.list_categories())

    def test_local_landline_and_international_format_identify_same_contact(self):
        saved = contacts.upsert_contact("(21) 2345-6789", nome="Empresa")
        self.assertEqual(saved["telefone"], "+55 21 2345-6789")
        self.assertEqual(contacts.get_contact("+55 21 2345-6789")["nome"], "Empresa")

    def test_append_observation_preserves_existing_text(self):
        contacts.upsert_contact("21998975416", nome="Exemplo", observacoes="Informação anterior")
        saved = contacts.append_observation("+55 21 99897-5416", "Colaboradora")
        self.assertEqual(saved["observacoes"], "Informação anterior; Colaboradora")

    def test_rename_updates_profile_heading(self):
        contacts.upsert_contact("21998975416", nome="Nome antigo")
        contacts.upsert_contact("21998975416", nome="Nome novo")
        profile = (contacts.BASE / "contatos" / "5521998975416.md").read_text()
        self.assertIn("# Nome novo (+55 21 99897-5416)", profile)

    def test_change_phone_keeps_profile_and_rejects_collision(self):
        contacts.upsert_contact("21998975416", nome="Exemplo", observacoes="Nota", quem_e="Conhecida")
        contacts.add_history("21998975416", "Conversa anterior")
        contacts.upsert_contact("21987654321", nome="Outra pessoa")
        with self.assertRaises(contacts.PersonalContactsError):
            contacts.change_phone("21998975416", "21987654321")
        moved = contacts.change_phone("21998975416", "+55 (21) 97777-2222")
        self.assertEqual(moved["nome"], "Exemplo")
        self.assertEqual(moved["observacoes"], "Nota")
        self.assertEqual(moved["quem_e"], "Conhecida")
        self.assertTrue(any("Conversa anterior" in row for row in moved["historico_recente"]))
        self.assertFalse((contacts.BASE / "contatos" / "5521998975416.md").exists())
        self.assertTrue((contacts.BASE / "contatos" / "5521977772222.md").exists())
        with self.assertRaises(contacts.PersonalContactsError):
            contacts.get_contact("21998975416")

    def test_nested_extra_data_round_trips_and_merges(self):
        contacts.upsert_contact("21998975416", nome="Exemplo", outros_dados={"setores": ["TI", "SEMED"]})
        saved = contacts.upsert_contact("21998975416", outros_dados={"vinculo": {"tipo": "colaborador"}})
        self.assertEqual(saved["outros_dados"], {
            "setores": ["TI", "SEMED"], "vinculo": {"tipo": "colaborador"},
        })

    def test_mcp_advertises_new_operations(self):
        class FakeMCP:
            def __init__(self):
                self.tools = {}

            def tool(self):
                def decorate(fn):
                    self.tools[fn.__name__] = fn
                    return fn
                return decorate

        previous = os.environ.get("FORGEHUB_AGENT_SLUG")
        os.environ["FORGEHUB_AGENT_SLUG"] = "maia"
        self.addCleanup(lambda: os.environ.pop("FORGEHUB_AGENT_SLUG", None) if previous is None
                        else os.environ.__setitem__("FORGEHUB_AGENT_SLUG", previous))
        mcp = FakeMCP()
        contacts.register(mcp)
        self.assertTrue({
            "personal_category_create", "personal_contact_append_observation", "personal_contact_change_phone",
        }.issubset(mcp.tools))


if __name__ == "__main__":
    unittest.main()
