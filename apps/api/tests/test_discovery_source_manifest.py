"""The six approved source identities are committed, but approval is NOT."""
from app.cli.source_registry_manifest import load_manifest


def test_manifest_exact_source_keys():
    sources = load_manifest()
    assert {row['key'] for row in sources} == {
        'unitree-robotics-official', 'booster-robotics-official',
        'agibot-official', 'agility-robotics-official',
        'figure-ai-official', 'alza-cz',
    }
    assert all(row['adapter_status'] != 'LIVE_APPROVED' for row in sources)


def test_manifest_hosts_do_not_claim_store_authorization():
    sources = load_manifest()
    hosts = {row['host'] for row in sources}
    assert 'shop.unitree.com' not in hosts
    assert 'store.agibot.com' not in hosts
