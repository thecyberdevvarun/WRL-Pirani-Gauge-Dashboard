import pytest

from lines_config import ConfigError, load_config


def load_lines(env):
    """Just the lines of a validated configuration."""
    return load_config(env).lines


def _env(**over):
    """A valid 2-line environment; keyword args override/add entries."""
    env = {
        "LINES": "CHOC,FRZ",
        "POLL_LINES": "CHOC",
        "LINE_CHOC_USERNAME": "choc", "LINE_CHOC_PASSWORD": "pw1",
        "LINE_CHOC_GAUGES": "18", "LINE_CHOC_UPPER_LIMIT": "0.5",
        "LINE_CHOC_GATEWAYS": "10.0.0.1:502:1-6,10.0.0.2:502:7-12,10.0.0.3:502:13-18",
        "LINE_FRZ_USERNAME": "frz", "LINE_FRZ_PASSWORD": "pw2",
        "LINE_FRZ_GAUGES": "54", "LINE_FRZ_UPPER_LIMIT": "0.7",
        "LINE_FRZ_GATEWAYS": "10.1.0.1:502",
    }
    env.update(over)
    return env


def test_loads_lines_in_order_with_defaults():
    lines = load_lines(_env())
    assert list(lines) == ["CHOC", "FRZ"]

    choc = lines["CHOC"]
    assert choc.label == "Choc"                      # defaulted from the key
    assert choc.gauge_ids == list(range(1, 19))      # gauge number == slave id, 1..N
    assert [(g.host, g.first, g.last) for g in choc.gateways] == [
        ("10.0.0.1", 1, 6), ("10.0.0.2", 7, 12), ("10.0.0.3", 13, 18),
    ]
    assert choc.poll_interval_sec == 60 and choc.min_duration_sec == 600
    assert choc.gap == 0 and choc.reading_delay_sec == 0

    # Single gateway, no range given -> serves every gauge; default port 502.
    frz = lines["FRZ"]
    assert frz.gauge_ids == list(range(1, 55))
    assert frz.gateway_for(54).address == "10.1.0.1:502"


def test_each_gauge_resolves_to_its_own_usr_device():
    choc = load_lines(_env())["CHOC"]
    assert choc.gateway_for(1).host == "10.0.0.1"
    assert choc.gateway_for(6).host == "10.0.0.1"
    assert choc.gateway_for(7).host == "10.0.0.2"
    assert choc.gateway_for(18).host == "10.0.0.3"
    assert choc.gateway_for(19) is None


def test_disabled_gauges_are_excluded_but_still_need_a_gateway():
    lines = load_lines(_env(LINE_CHOC_DISABLED_GAUGES="3, 10-11"))
    assert 3 not in lines["CHOC"].gauge_ids
    assert 10 not in lines["CHOC"].gauge_ids and 11 not in lines["CHOC"].gauge_ids
    assert len(lines["CHOC"].gauge_ids) == 15


def test_optional_settings_are_read():
    lines = load_lines(_env(
        LINE_CHOC_LABEL="Chocolate", LINE_CHOC_GAP="5", LINE_CHOC_POLL_INTERVAL_SEC="120",
        LINE_CHOC_READING_DELAY_SEC="15", LINE_CHOC_MIN_DURATION_SEC="300",
    ))
    c = lines["CHOC"]
    assert (c.label, c.gap, c.poll_interval_sec, c.reading_delay_sec, c.min_duration_sec) == (
        "Chocolate", 5, 120, 15, 300)
    assert c.upper_limit == 0.5


def test_lines_variable_is_required():
    with pytest.raises(ConfigError, match="LINES is not set"):
        load_lines({})


def _problems(**over):
    """Every problem load_config() reports for the base environment plus `over`."""
    with pytest.raises(ConfigError) as exc:
        load_config(_env(**over))
    return "\n".join(exc.value.problems)


def test_gateway_ranges_must_cover_every_gauge():
    msg = _problems(LINE_CHOC_GATEWAYS="10.0.0.1:502:1-6,10.0.0.2:502:7-12")
    assert "13-18" in msg and "not assigned to any gateway" in msg


def test_gateway_ranges_must_not_overlap():
    msg = _problems(LINE_CHOC_GATEWAYS="10.0.0.1:502:1-10,10.0.0.2:502:9-18")
    assert "gauge 9 is assigned to both" in msg


def test_gateway_range_outside_line_is_rejected():
    assert "outside 1-18" in _problems(LINE_CHOC_GATEWAYS="10.0.0.1:502:1-19")


def test_multiple_gateways_need_ranges():
    assert "needs a gauge range" in _problems(LINE_CHOC_GATEWAYS="10.0.0.1:502,10.0.0.2:502")


def test_bad_port_and_bad_range_text():
    assert "invalid port" in _problems(LINE_CHOC_GATEWAYS="10.0.0.1:99999:1-18")
    assert "invalid gauge range" in _problems(LINE_CHOC_GATEWAYS="10.0.0.1:502:one-six")


def test_required_fields_missing():
    env = _env()
    for k in ("LINE_CHOC_USERNAME", "LINE_CHOC_PASSWORD", "LINE_CHOC_GAUGES",
              "LINE_CHOC_GATEWAYS", "LINE_CHOC_UPPER_LIMIT"):
        env.pop(k)
    with pytest.raises(ConfigError) as exc:
        load_lines(env)
    msg = "\n".join(exc.value.problems)
    for k in ("USERNAME", "PASSWORD", "GAUGES", "GATEWAYS", "UPPER_LIMIT"):
        assert f"LINE_CHOC_{k}" in msg


def test_all_problems_are_reported_at_once():
    msg = _problems(LINE_CHOC_GAP="9999", LINE_CHOC_POLL_INTERVAL_SEC="5",
                    LINE_FRZ_UPPER_LIMIT="-1")
    assert "LINE_CHOC_GAP" in msg and "LINE_CHOC_POLL_INTERVAL_SEC" in msg
    assert "LINE_FRZ_UPPER_LIMIT" in msg


def test_numbers_must_be_numbers():
    assert "not a whole number" in _problems(LINE_CHOC_GAP="abc")
    assert "must be a number" in _problems(LINE_FRZ_UPPER_LIMIT="high")
    assert "LINE_CHOC_GAUGES" in _problems(LINE_CHOC_GAUGES="0")
    assert "LINE_CHOC_GAUGES" in _problems(LINE_CHOC_GAUGES="300")


def test_disabled_gauge_outside_range():
    assert "outside 1-18" in _problems(LINE_CHOC_DISABLED_GAUGES="30")


def test_usernames_must_be_unique_across_lines_case_insensitively():
    assert "each line needs its own login" in _problems(LINE_FRZ_USERNAME="CHOC")


def test_a_gateway_cannot_be_shared_between_lines():
    msg = _problems(LINE_FRZ_GATEWAYS="10.0.0.2:502")
    assert "10.0.0.2:502 is used by both" in msg


def test_same_host_different_port_is_a_different_gateway():
    # e.g. one router port-forwarding a separate port to each USR device
    lines = load_lines(_env(
        LINE_CHOC_GATEWAYS="192.168.1.1:5001:1-6,192.168.1.1:5002:7-12,192.168.1.1:5003:13-18"))
    assert [g.port for g in lines["CHOC"].gateways] == [5001, 5002, 5003]


def test_line_keys_are_normalised_and_validated():
    lines = load_lines(_env(LINES="choc, frz"))   # lower case in LINES still finds LINE_CHOC_*
    assert list(lines) == ["CHOC", "FRZ"]
    assert "listed twice" in _problems(LINES="CHOC,choc")
    assert "may only contain" in _problems(LINES="CHOC,FR-Z")


# ===========================================================================
# USR identity, network validation, users, polling settings
# ===========================================================================
import os

from dotenv import dotenv_values

NET_CHOC = dict(
    LINE_CHOC_SUBNET="10.0.0.0/24", LINE_CHOC_PC_IP="10.0.0.1", LINE_CHOC_ROUTER_IP="10.0.0.2",
    LINE_CHOC_GATEWAYS="10.0.0.3:502:1-6,10.0.0.4:502:7-12,10.0.0.5:502:13-18",
)


def _cfg(**over):
    return load_config(_env(**over))


def test_usr_ids_are_stable_names_built_from_line_and_position():
    lines = load_config(_env(POLL_LINES="ALL", LINES="CHOC,FRZ",
                             LINE_FRZ_GATEWAYS="10.1.0.1:502:1-30,10.1.0.2:502:31-54")).lines
    assert [g.usr_id for g in lines["CHOC"].gateways] == ["choc-usr-01", "choc-usr-02", "choc-usr-03"]
    assert [g.usr_id for g in lines["FRZ"].gateways] == ["frz-usr-01", "frz-usr-02"]
    assert lines["CHOC"].gateway_by_id("choc-usr-02").host == "10.0.0.2"
    assert lines["CHOC"].gateway_by_id("nope") is None


def test_usr_id_uses_hyphens_for_underscored_keys():
    env = _env(LINES="VISI_COOLER", POLL_LINES="VISI_COOLER",
               LINE_VISI_COOLER_USERNAME="v", LINE_VISI_COOLER_PASSWORD="p",
               LINE_VISI_COOLER_GAUGES="10", LINE_VISI_COOLER_UPPER_LIMIT="1",
               LINE_VISI_COOLER_GATEWAYS="10.3.0.1:502:1-5,10.3.0.2:502:6-10")
    ids = [g.usr_id for g in load_config(env).lines["VISI_COOLER"].gateways]
    assert ids == ["visi-cooler-usr-01", "visi-cooler-usr-02"]


def test_changing_an_ip_does_not_change_a_usr_identity():
    a = _cfg(LINE_CHOC_GATEWAYS="10.0.0.3:502:1-6,10.0.0.4:502:7-12,10.0.0.5:502:13-18").lines["CHOC"]
    b = _cfg(LINE_CHOC_GATEWAYS="10.0.9.3:502:1-6,10.0.9.4:502:7-12,10.0.9.5:502:13-18").lines["CHOC"]
    assert [g.usr_id for g in a.gateways] == [g.usr_id for g in b.gateways]
    assert [g.host for g in a.gateways] != [g.host for g in b.gateways]


def test_disabled_usr_by_number_or_id_takes_its_gauges_out_of_service():
    for value in ("2", "choc-usr-02", "CHOC-USR-02"):
        line = _cfg(LINE_CHOC_DISABLED_USRS=value).lines["CHOC"]
        assert [g.enabled for g in line.gateways] == [True, False, True], value
        assert line.gauge_ids == [n for n in range(1, 19) if not 7 <= n <= 12]
    assert "not one of this line's USRs" in _problems(LINE_CHOC_DISABLED_USRS="9")


def test_valid_network_configuration_is_accepted_and_kept():
    line = _cfg(**NET_CHOC, LINE_CHOC_COMPANY_PC_IP="172.16.1.9").lines["CHOC"]
    assert (line.subnet, line.pc_line_ip, line.router_ip, line.company_pc_ip) == (
        "10.0.0.0/24", "10.0.0.1", "10.0.0.2", "172.16.1.9")


def test_network_settings_are_optional():
    line = _cfg().lines["CHOC"]
    assert line.subnet is None and line.pc_line_ip is None and line.company_pc_ip is None


def test_network_and_broadcast_addresses_may_not_be_assigned():
    msg = _problems(**{**NET_CHOC, "LINE_CHOC_GATEWAYS": "10.0.0.0:502:1-6,10.0.0.255:502:7-12,10.0.0.5:502:13-18"})
    assert msg.count("not a usable host address") == 2
    assert "10.0.0.255" in msg and "10.0.0.0" in msg
    assert "not a usable host address" in _problems(**{**NET_CHOC, "LINE_CHOC_PC_IP": "10.0.0.255"})
    assert "not a usable host address" in _problems(**{**NET_CHOC, "LINE_CHOC_ROUTER_IP": "10.0.0.0"})


def test_a_usr_must_be_inside_the_line_subnet():
    msg = _problems(**{**NET_CHOC, "LINE_CHOC_GATEWAYS": "10.0.0.3:502:1-6,10.0.1.4:502:7-12,10.0.0.5:502:13-18"})
    assert "choc-usr-02" in msg and "10.0.1.4" in msg


def test_a_usr_may_not_reuse_the_pc_or_router_address():
    msg = _problems(**{**NET_CHOC, "LINE_CHOC_GATEWAYS": "10.0.0.1:502:1-6,10.0.0.2:502:7-12,10.0.0.5:502:13-18"})
    assert "same as LINE_CHOC_PC_IP" in msg and "same as LINE_CHOC_ROUTER_IP" in msg
    assert "both" in _problems(**{**NET_CHOC, "LINE_CHOC_ROUTER_IP": "10.0.0.1"})


def test_duplicate_usr_addresses_within_a_line_are_rejected():
    msg = _problems(**{**NET_CHOC, "LINE_CHOC_GATEWAYS": "10.0.0.3:502:1-6,10.0.0.3:5020:7-12,10.0.0.5:502:13-18"})
    assert "10.0.0.3 is assigned to both choc-usr-01 and choc-usr-02" in msg


def test_hostnames_are_refused_when_a_subnet_is_set():
    msg = _problems(**{**NET_CHOC, "LINE_CHOC_GATEWAYS": "usr-a:502:1-6,10.0.0.4:502:7-12,10.0.0.5:502:13-18"})
    assert "must be an IPv4 address" in msg


def test_malformed_network_values_are_reported():
    assert "not a valid network" in _problems(LINE_CHOC_SUBNET="192.168.1.5/24")   # host bits set
    assert "not a valid network" in _problems(LINE_CHOC_SUBNET="banana")
    assert "not a valid IPv4" in _problems(LINE_CHOC_PC_IP="192.168.1.300")
    assert "not a valid IPv4" in _problems(LINE_CHOC_COMPANY_PC_IP="10.100.x.x")


def test_line_subnets_may_not_overlap():
    msg = _problems(**{**NET_CHOC, "LINE_FRZ_SUBNET": "10.0.0.128/25"})
    assert "Line networks overlap" in msg and "CHOC" in msg and "FRZ" in msg


def test_unknown_register_map_is_rejected():
    assert "unknown" in _problems(LINE_CHOC_REGISTER_MAP="mystery")
    assert _cfg(LINE_CHOC_REGISTER_MAP="pirani_default").lines["CHOC"].register_map == "pirani_default"


# ---- users ----
def _users_env(**over):
    base = dict(USERS="ADMIN,SUPER",
                USER_ADMIN_USERNAME="admin", USER_ADMIN_PASSWORD="a", USER_ADMIN_LINES="ALL", USER_ADMIN_ROLE="admin",
                USER_SUPER_USERNAME="super", USER_SUPER_PASSWORD="s", USER_SUPER_LINES="FRZ,CHOC")
    base.update(over)
    return base


def test_every_line_login_is_a_single_line_operator_and_extra_users_can_span_lines():
    users = _cfg(**_users_env()).users
    assert users["choc"].lines == ("CHOC",) and users["choc"].role == "operator"
    assert users["frz"].lines == ("FRZ",)
    assert users["admin"].lines == ("CHOC", "FRZ") and users["admin"].role == "admin"
    assert users["super"].lines == ("FRZ", "CHOC") and users["super"].role == "operator"


def test_user_problems_are_reported():
    assert "USER_ADMIN_LINES is required" in _problems(**_users_env(USER_ADMIN_LINES=""))
    assert "'GHOST' is not a line" in _problems(**_users_env(USER_SUPER_LINES="CHOC,GHOST"))
    assert "must be one of" in _problems(**_users_env(USER_ADMIN_ROLE="root"))
    assert "USER_SUPER_USERNAME is required" in _problems(**_users_env(USER_SUPER_USERNAME=""))
    assert "already used" in _problems(**_users_env(USER_SUPER_USERNAME="CHOC"))   # clashes with a line login
    assert "already used" in _problems(**_users_env(USER_SUPER_USERNAME="Admin"))


# ---- polling settings ----
def test_polling_defaults_preserve_the_values_the_app_already_used():
    s = _cfg().settings
    assert (s.modbus_timeout_sec, s.read_retries, s.cycle_pause_sec) == (5.0, 0, 2.0)
    assert (s.backoff_initial_sec, s.backoff_max_sec, s.stale_after_sec) == (5.0, 60.0, 30.0)
    assert s.polling_mode == "line_specific" and s.poll_lines == frozenset({"CHOC"})


def test_line_specific_mode_requires_naming_the_lines():
    env = _env()
    env.pop("POLL_LINES", None)
    with pytest.raises(ConfigError) as exc:
        load_config(env)
    assert "POLL_LINES is required" in "\n".join(exc.value.problems)


def test_centralized_mode_defaults_to_every_line_and_all_means_all():
    env = _env(POLLING_MODE="centralized")
    env.pop("POLL_LINES")
    assert load_config(env).settings.poll_lines == frozenset({"CHOC", "FRZ"})
    assert load_config(_env(POLL_LINES="ALL")).settings.poll_lines == frozenset({"CHOC", "FRZ"})
    assert load_config(_env(POLL_LINES="frz")).settings.poll_lines == frozenset({"FRZ"})


def test_polling_setting_problems():
    assert "POLLING_MODE" in _problems(POLLING_MODE="everywhere")
    assert "'GHOST' is not a line" in _problems(POLL_LINES="CHOC,GHOST")
    assert "MODBUS_TIMEOUT_SEC" in _problems(MODBUS_TIMEOUT_SEC="0")
    assert "MODBUS_READ_RETRIES" in _problems(MODBUS_READ_RETRIES="99")
    assert "must not be smaller" in _problems(MODBUS_BACKOFF_INITIAL_SEC="30", MODBUS_BACKOFF_MAX_SEC="10")
    assert "STALE_AFTER_SEC" in _problems(STALE_AFTER_SEC="abc")


# ---- the real topology from the requirements document ----
SPEC = {
    # line: (subnet, pc, router, [(usr ip, first, last), ...])
    "FREEZER": ("192.168.1.0/24", "192.168.1.1", "192.168.1.2",
                [(f"192.168.1.{3 + i}", 1 + 5 * i, 5 + 5 * i) for i in range(10)] + [("192.168.1.13", 51, 54)]),
    "CHOCOLATE": ("192.168.2.0/24", "192.168.2.1", "192.168.2.2",
                  [("192.168.2.3", 1, 6), ("192.168.2.4", 7, 12), ("192.168.2.5", 13, 18)]),
    "VISI_COOLER": ("192.168.3.0/24", "192.168.3.1", "192.168.3.2",
                    [(f"192.168.3.{3 + i}", 1 + 5 * i, 5 + 5 * i) for i in range(6)]),
    "SUS": ("192.168.4.0/24", "192.168.4.1", "192.168.4.2",
            [("192.168.4.3", 1, 5), ("192.168.4.4", 6, 10), ("192.168.4.5", 11, 15)]),
}


@pytest.mark.parametrize("filename", [".env", ".env.example"])
def test_shipped_env_files_match_the_documented_plant(filename):
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), filename)
    if not os.path.exists(path):
        pytest.skip(f"{filename} not present")
    cfg = load_config(dotenv_values(path))
    lines = cfg.lines

    assert list(lines) == ["FREEZER", "CHOCOLATE", "VISI_COOLER", "SUS"]
    assert {k: len(v.gauge_ids) for k, v in lines.items()} == {
        "FREEZER": 54, "CHOCOLATE": 18, "VISI_COOLER": 30, "SUS": 15}
    assert {k: len(v.gateways) for k, v in lines.items()} == {
        "FREEZER": 11, "CHOCOLATE": 3, "VISI_COOLER": 6, "SUS": 3}
    assert sum(len(v.gauge_ids) for v in lines.values()) == 117
    assert sum(len(v.gateways) for v in lines.values()) == 23

    for key, (subnet, pc, router, usrs) in SPEC.items():
        line = lines[key]
        assert (line.subnet, line.pc_line_ip, line.router_ip) == (subnet, pc, router), key
        assert [(g.host, g.first, g.last) for g in line.gateways] == usrs, key
        assert all(g.port == 502 for g in line.gateways)
    assert [g.usr_id for g in lines["FREEZER"].gateways][0] == "freezer-usr-01"
    assert [g.usr_id for g in lines["VISI_COOLER"].gateways][-1] == "visi-cooler-usr-06"
    assert lines["FREEZER"].company_pc_ip == "10.100.95.193"
    assert lines["CHOCOLATE"].company_pc_ip == "10.100.99.59"
    assert lines["VISI_COOLER"].company_pc_ip == "10.100.99.214"
    assert lines["SUS"].company_pc_ip is None            # not confirmed yet -- deliberately blank

    # Every line has its own login; there is one all-lines admin.
    assert {u.lines for u in cfg.users.values() if u.role == "operator"} == {
        ("FREEZER",), ("CHOCOLATE",), ("VISI_COOLER",), ("SUS",)}
    assert cfg.users["admin"].lines == tuple(lines)
