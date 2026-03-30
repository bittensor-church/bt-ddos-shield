from server_shield.pulumi_runner.program import (
    build_waf_rule_names,
    build_waf_rules,
    should_create_domain_allow_rule,
)


def test_empty_desired_domains_skip_host_allow_rule() -> None:
    assert should_create_domain_allow_rule({}) is False
    assert build_waf_rule_names({}) == ["allow-manifest"]


def test_non_empty_desired_domains_include_host_allow_rule() -> None:
    desired_domains = {
        "validator-hotkey-1": {
            "domain": "miner.example.com",
            "public_cert": "cert-a",
        }
    }
    assert should_create_domain_allow_rule(desired_domains) is True
    assert build_waf_rule_names(desired_domains) == [
        "allow-predefined-domains",
        "allow-manifest",
    ]


def test_build_waf_rules_keeps_manifest_rule_when_domains_empty() -> None:
    rules = build_waf_rules({}, miner_port=9003)

    assert [rule.name for rule in rules] == ["allow-manifest"]
    assert rules[0].statement.byte_match_statement.search_string == "/shield_manifest.json"


def test_build_waf_rules_adds_host_rule_for_each_domain() -> None:
    rules = build_waf_rules(
        {
            "validator-hotkey-1": {
                "domain": "miner-a.example.com",
                "public_cert": "cert-a",
            },
            "validator-hotkey-2": {
                "domain": "miner-b.example.com",
                "public_cert": "cert-b",
            },
        },
        miner_port=9003,
    )

    assert [rule.name for rule in rules] == ["allow-predefined-domains", "allow-manifest"]
    statements = rules[0].statement.or_statement.statements
    assert len(statements) == 2
    assert statements[0].byte_match_statement.search_string == "miner-a.example.com:9003"
    assert statements[1].byte_match_statement.search_string == "miner-b.example.com:9003"


def test_build_waf_rules_uses_direct_match_for_single_domain_with_port() -> None:
    rules = build_waf_rules(
        {
            "validator-hotkey-1": {
                "domain": "miner.example.com",
                "public_cert": "cert-a",
            }
        },
        miner_port=9003,
    )

    assert [rule.name for rule in rules] == ["allow-predefined-domains", "allow-manifest"]
    assert rules[0].statement.byte_match_statement.search_string == "miner.example.com:9003"
    assert rules[0].statement.or_statement is None
