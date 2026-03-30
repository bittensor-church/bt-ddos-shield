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
        "allow-predefined-domain-0",
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

    assert [rule.name for rule in rules] == [
        "allow-predefined-domain-0",
        "allow-predefined-domain-1",
        "allow-manifest",
    ]
    assert rules[0].statement.byte_match_statement.search_string == "miner-a.example.com"
    assert rules[1].statement.byte_match_statement.search_string == "miner-b.example.com"
    assert rules[2].priority == 2


def test_build_waf_rules_uses_direct_match_for_single_domain() -> None:
    rules = build_waf_rules(
        {
            "validator-hotkey-1": {
                "domain": "miner.example.com",
                "public_cert": "cert-a",
            }
        },
        miner_port=9003,
    )

    assert [rule.name for rule in rules] == ["allow-predefined-domain-0", "allow-manifest"]
    assert rules[0].statement.byte_match_statement.search_string == "miner.example.com"
    assert rules[0].statement.or_statement is None


def test_build_waf_rules_lowercases_mixed_case_domain_match() -> None:
    rules = build_waf_rules(
        {
            "validator-hotkey-1": {
                "domain": "5Chngqcs-a1e210647c10.tubidudam.click",
                "public_cert": "cert-a",
            }
        },
        miner_port=9003,
    )

    assert rules[0].statement.byte_match_statement.search_string == (
        "5chngqcs-a1e210647c10.tubidudam.click"
    )
