"""ECO-067/068/069: Foundation integrity and agent-memory hygiene, on temporary trees only."""
import importlib.util
import sys
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / 'knowledge_hygiene.py'
spec = importlib.util.spec_from_file_location('knowledge_hygiene_tests', PATH)
k = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = k
spec.loader.exec_module(k)


def foundation(tmp_path):
    root = tmp_path / 'foundation'
    for folder in ('14_agents', '36_governance', '47_migrations'):
        (root / folder).mkdir(parents=True)
    (root / '09_MANIFEST.yaml').write_text(f'canonical_root: {root}\n')
    (root / '10_README.md').write_text('# Foundation\n')
    (root / '14_agents' / 'ECOSYSTEM_AGENTS.md').write_text('# Agents\n')
    return root


def test_clean_foundation_passes(tmp_path):
    root = foundation(tmp_path)
    (root / '36_governance' / 'RULES.md').write_text('See `14_agents/ECOSYSTEM_AGENTS.md`.\n')
    assert k.foundation_findings(root) == []


def test_retired_term_in_a_live_rule_fails_but_history_paragraph_passes(tmp_path):
    root = foundation(tmp_path)
    (root / '36_governance' / 'RULES.md').write_text(
        '# Rules\n\nOfficial tracking is Kanboard.\n\n'
        'Kanboard was retired in 2026-08; ForgeHub Messages replaced it.\n')
    findings = k.foundation_findings(root)
    assert len(findings) == 1 and 'RULES.md:3' in findings[0] and 'kanboard' in findings[0]


def test_history_heading_and_retired_file_header_are_exempt(tmp_path):
    root = foundation(tmp_path)
    (root / '36_governance' / 'A.md').write_text('# A\n\n## Vector (retired 2026-10-12)\n\nruntime: OpenClaw\n')
    (root / '14_agents' / 'VECTOR.md').write_text('# Vector\n\n**Status:** Retired 2026-10-12\n\nRuntime: OpenClaw\n')
    assert k.foundation_findings(root) == []


def test_dated_records_are_not_checked(tmp_path):
    root = foundation(tmp_path)
    (root / '47_migrations' / '2026-07-01-x.md').write_text('Kanboard is official. See `56_report/x.md`.\n')
    assert k.foundation_findings(root) == []


def test_legacy_foundation_path_and_dead_links_fail(tmp_path):
    root = foundation(tmp_path)
    (root / '36_governance' / 'B.md').write_text(
        'Read /root/.hermes/foundation/36_governance/B.md\n\nSee `56_report/db-health`.\n\n'
        'Template `/root/memory/foundation/<agent>/x.md` and `SUBSCRIPTION_*_REFERENCE.md`.\n')
    findings = k.foundation_findings(root)
    assert any('/root/.hermes/foundation' in f for f in findings)
    assert any('56_report/db-health' in f for f in findings)
    assert not any('<agent>' in f or 'SUBSCRIPTION' in f for f in findings)


def test_unexpected_root_entry_and_wrong_canonical_root_fail(tmp_path):
    root = foundation(tmp_path)
    (root / '18_athos').mkdir()
    (root / '09_MANIFEST.yaml').write_text('canonical_root: /root/.hermes/foundation\n')
    findings = k.foundation_findings(root)
    assert any('18_athos' in f for f in findings)
    assert any('canonical_root' in f for f in findings)


def home(tmp_path):
    profiles = tmp_path / 'profiles'
    p = profiles / 'athos'
    (p / 'memories').mkdir(parents=True)
    (p / 'config.yaml').write_text('memory:\n  memory_char_limit: 100\n  user_char_limit: 50\n')
    (p / 'memories' / 'MEMORY.md').write_text('ok')
    (p / 'memories' / 'USER.md').write_text('é' * 60)          # 60 chars, 120 bytes
    parked = profiles / 'old'
    parked.mkdir()
    (parked / 'config.yaml').write_text('')
    (parked / 'gateway.parked').write_text('')
    (parked / 'SOUL.md').write_text('x' * 100_000)
    root = tmp_path / 'home'
    memory = root / '.claude' / 'projects' / '-root-project-x' / 'memory'
    memory.mkdir(parents=True)
    (memory / 'MEMORY.md').write_text('\n'.join(f'- line {n}' for n in range(205)))
    (memory / 'note.md').write_text('Uses Kanboard for tracking.\n')
    (root / '.codex').mkdir()
    (root / '.codex' / 'AGENTS.md').write_text('a' * 9000)
    (root / '.gemini' / 'config').mkdir(parents=True)
    (root / '.gemini' / 'config' / 'MEMORY.md').write_text('Foundation: /root/.hermes/foundation\n')
    return profiles, root


def test_memory_size_uses_each_profiles_own_limits_and_skips_parked(tmp_path):
    profiles, root = home(tmp_path)
    findings = k.memory_size_findings(k.memory_inventory(profiles, root), tmp_path / 'kb')
    assert any('athos' in f and 'USER.md is 60 chars (limit 50)' in f for f in findings)
    assert not any('old' in f for f in findings)
    assert any('205 lines' in f for f in findings)
    assert any('AGENTS.md is 9000 bytes' in f for f in findings)
    assert not any('memories/MEMORY.md' in f for f in findings)


def test_memory_currency_covers_hermes_claude_and_external_runtimes(tmp_path):
    profiles, root = home(tmp_path)
    findings = k.memory_currency_findings(k.memory_inventory(profiles, root), tmp_path / 'foundation')
    assert any('note.md:1' in f and 'kanboard' in f for f in findings)
    assert any('.gemini/config/MEMORY.md:1' in f and '/root/.hermes/foundation' in f for f in findings)


def test_findings_never_quote_memory_text(tmp_path):
    profiles, root = home(tmp_path)
    (root / '.claude' / 'projects' / '-root-project-x' / 'memory' / 'note.md').write_text('secret-ish note on Kanboard\n')
    findings = k.memory_currency_findings(k.memory_inventory(profiles, root), tmp_path / 'foundation')
    assert all('secret-ish' not in f for f in findings)
