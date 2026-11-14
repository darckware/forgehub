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
    memory = root / '.claude' / 'projects' / '-root-project-x' / 'memory'
    (memory / 'contact.md').write_text('Ficha em /root/memory/knowledge_base/maia/contatos/joao-silva.md\n')
    findings = k.memory_currency_findings(k.memory_inventory(profiles, root), tmp_path / 'foundation')
    assert all('secret-ish' not in f and 'joao-silva' not in f for f in findings)
    assert any('contact.md:1 links a missing path' in f for f in findings)


def test_dead_link_at_end_of_line_is_reported(tmp_path):
    root = foundation(tmp_path)
    (root / '36_governance' / 'C.md').write_text('see /root/memory/nope_missing_file.md\n')
    assert any('nope_missing_file.md' in f for f in k.foundation_findings(root))


def test_common_words_do_not_exempt_a_live_rule(tmp_path):
    root = foundation(tmp_path)
    (root / '36_governance' / 'D.md').write_text(
        'Use Kanboard in the camera opera.\nO tracking era bom; usar Kanboard até o fim.\n'
        'Previous notes were here.\n\nUse Kanboard now.\n')
    findings = k.foundation_findings(root)
    assert sum('kanboard' in f for f in findings) == 3


def test_marker_on_the_next_line_covers_a_wrapped_sentence(tmp_path):
    root = foundation(tmp_path)
    (root / '36_governance' / 'E.md').write_text('# E\n\nTracking: Kanboard was\nretired in 2026-08.\n\nFar below.\n\nKanboard again.\n')
    findings = k.foundation_findings(root)
    assert len(findings) == 1 and 'E.md:8' in findings[0]


def test_heading_inside_code_fence_does_not_change_the_section(tmp_path):
    root = foundation(tmp_path)
    (root / '36_governance' / 'F.md').write_text('# Retired things\n\n```\n# live\n```\n\nKanboard row.\n\n# Current\n\nKanboard now.\n')
    findings = k.foundation_findings(root)
    assert len(findings) == 1 and 'F.md:11' in findings[0]


def test_symlinked_documents_are_not_followed(tmp_path):
    root = foundation(tmp_path)
    outside = tmp_path / 'outside.md'
    outside.write_text('Kanboard is official.\n')
    (root / '36_governance' / 'link.md').symlink_to(outside)
    assert k.foundation_findings(root) == []


def test_unreadable_memory_and_config_are_reported_not_passed(tmp_path):
    profiles, root = home(tmp_path)
    (profiles / 'athos' / 'config.yaml').unlink()
    (profiles / 'athos' / 'config.yaml').mkdir()           # unreadable as a file
    broken = root / '.gemini' / 'config' / 'TOOLS.md'
    broken.symlink_to(tmp_path / 'gone.md')
    inventory = k.memory_inventory(profiles, root)
    sizes = k.memory_size_findings(inventory, tmp_path / 'kb')
    assert any('memory limits not verified' in f for f in sizes)
    assert any('TOOLS.md is a broken link' in f for f in k.memory_currency_findings(inventory, tmp_path / 'f'))


def test_only_the_first_megabyte_is_read(tmp_path):
    big = tmp_path / 'big.md'
    big.write_text('x' * (k.MAX_READ_BYTES + 10) + '\nKanboard\n')
    assert k.text_findings(big, 'big.md') == []


def test_generic_history_and_must_not_do_not_exempt(tmp_path):
    root = foundation(tmp_path)
    (root / '36_governance' / 'G.md').write_text('Keep the git history clean.\nTrack work in Kanboard.\n\nYou must not skip.\nKanboard is official.\n')
    assert sum('kanboard' in f for f in k.foundation_findings(root)) == 2


def test_a_history_section_is_exempt(tmp_path):
    root = foundation(tmp_path)
    (root / '36_governance' / 'H.md').write_text('# H\n\n## 4. History\n\n- 2026-09-04: the foundation_postgres pair was split.\n')
    assert k.foundation_findings(root) == []


def test_dispatch_preamble_over_the_limit_is_reported(tmp_path):
    claude = tmp_path / '.claude'
    claude.mkdir()
    (claude / 'SOUL.md').write_text('s' * 5000)
    (claude / 'MEMORY.md').write_text('m' * 4000)
    findings = k.preamble_findings(tmp_path)
    assert len(findings) == 1 and findings[0].startswith('porthus: dispatched identity and memory')


def test_one_soul_per_agent_and_no_stray_copies(tmp_path):
    profiles = tmp_path / 'profiles'
    for name in ('athos', 'old'):
        (profiles / name).mkdir(parents=True)
        (profiles / name / 'config.yaml').write_text('')
    (profiles / 'old' / 'gateway.parked').write_text('')
    (profiles / 'athos' / 'SOUL.md').write_text('x')
    (profiles / 'athos' / 'IDENTITY.md').write_text('x')
    (profiles / 'athos' / 'backup').mkdir()
    (profiles / 'athos' / 'backup' / 'SOUL.md').write_text('old')
    (profiles / 'athos' / 'state-snapshots').mkdir()
    (profiles / 'athos' / 'state-snapshots' / 'SOUL.md').write_text('kept backup')
    (profiles / 'old' / 'SOUL.md').write_text('parked')
    home = tmp_path / 'home'
    for parts in (('.claude',), ('.codex',), ('.gemini', 'config')):
        d = home.joinpath(*parts)
        d.mkdir(parents=True)
        for name in k.DISPATCH_PREAMBLE_FILES:
            (d / name).write_text('x')
    (home / '.codex' / 'MEMORY.md').unlink()
    foundation = tmp_path / 'foundation'
    (foundation / '14_agents').mkdir(parents=True)
    (foundation / '14_agents' / 'IDENTITY.md').write_text('stray')
    findings = k.profile_file_findings(profiles, home, foundation, tmp_path / 'kb')
    assert any('stray SOUL.md' in f and 'backup' in f for f in findings)
    assert any('stray IDENTITY.md' in f and '14_agents' in f for f in findings)
    assert any(f.startswith('aramis: missing') and 'MEMORY.md' in f for f in findings)
    assert not any('state-snapshots' in f or '/old/' in f for f in findings)
    assert len(findings) == 3


def test_service_rule_files_must_match_forgehub(tmp_path):
    import hashlib
    profiles = tmp_path / 'profiles'
    (profiles / 'lara').mkdir(parents=True)
    (profiles / 'maia').mkdir(parents=True)
    ok_text = 'regras do site\n'
    (profiles / 'lara' / 'ATENDIMENTO_SITE.md').write_text(ok_text)
    (profiles / 'lara' / 'ATENDIMENTO_WHATSAPP.md').write_text('editado a mão\n')
    (profiles / 'lara' / 'ATENDIMENTO_EMAIL.md').write_text('x' * (k.SERVICE_RULE_MAX_CHARS + 5))
    legacy = tmp_path / 'REGRAS.md'
    legacy.write_text('old')
    hashes = {('lara', 'site'): hashlib.sha256(ok_text.encode()).hexdigest(),
              ('lara', 'whatsapp'): 'f' * 64,
              ('lara', 'email'): hashlib.sha256(('x' * (k.SERVICE_RULE_MAX_CHARS + 5)).encode()).hexdigest()}
    findings = k.service_rule_findings(hashes, profiles, (str(legacy),))
    assert not any('lara/site' in f for f in findings)
    assert any('lara/whatsapp' in f and 'differs from ForgeHub' in f for f in findings)
    assert any('lara/email' in f and 'limit' in f for f in findings)
    assert any(f.startswith('maia/whatsapp: missing') and 'not registered' in f for f in findings)
    assert any('legacy service-rule copy' in f for f in findings)
