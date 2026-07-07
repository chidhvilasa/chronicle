import random
import time

import pytest

from chronicle.chaos import ChaosConfig, ChaosMixin, chaos


def test_tool_failure_rate_of_one_always_raises():
    random.seed(42)
    config = ChaosConfig(tool_failure_rate=1.0, tool_failure_message="boom")
    mixin = ChaosMixin(config)

    with pytest.raises(RuntimeError, match="boom"):
        mixin.wrap_tool_call("search", lambda: "result")


def test_tool_failure_rate_of_zero_never_raises():
    random.seed(42)
    config = ChaosConfig(tool_failure_rate=0.0)
    mixin = ChaosMixin(config)

    for _ in range(50):
        assert mixin.wrap_tool_call("search", lambda: "result") == "result"


def test_tool_failure_only_targets_configured_tools():
    random.seed(42)
    config = ChaosConfig(tool_failure_rate=1.0, tool_failure_tools=["other_tool"])
    mixin = ChaosMixin(config)

    # "search" isn't in tool_failure_tools, so it should never fail even at rate 1.0.
    assert mixin.wrap_tool_call("search", lambda: "result") == "result"

    with pytest.raises(RuntimeError):
        mixin.wrap_tool_call("other_tool", lambda: "result")


def test_tool_failure_uses_configured_exception_type():
    random.seed(42)

    class CustomError(Exception):
        pass

    config = ChaosConfig(tool_failure_rate=1.0, tool_failure_exception=CustomError, tool_failure_message="custom")
    mixin = ChaosMixin(config)

    with pytest.raises(CustomError, match="custom"):
        mixin.wrap_tool_call("search", lambda: "result")


def test_latency_injection_adds_the_correct_delay():
    random.seed(42)
    config = ChaosConfig(latency_injection_ms=50)
    mixin = ChaosMixin(config)

    start = time.perf_counter()
    mixin.wrap_tool_call("search", lambda: "result")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms >= 50


def test_latency_injection_only_targets_configured_tools():
    random.seed(42)
    config = ChaosConfig(latency_injection_ms=200, latency_injection_tools=["other_tool"])
    mixin = ChaosMixin(config)

    start = time.perf_counter()
    mixin.wrap_tool_call("search", lambda: "result")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < 100


def test_no_latency_injection_by_default():
    random.seed(42)
    config = ChaosConfig()
    mixin = ChaosMixin(config)

    start = time.perf_counter()
    mixin.wrap_tool_call("search", lambda: "result")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms < 50


def test_malformed_response_returned_when_rate_is_one():
    random.seed(42)
    config = ChaosConfig(malformed_response_rate=1.0, malformed_response_value="TRUNCATED")
    mixin = ChaosMixin(config)

    assert mixin.wrap_tool_call("search", lambda: "real result") == "TRUNCATED"


def test_real_result_returned_when_malformed_response_rate_is_zero():
    random.seed(42)
    config = ChaosConfig(malformed_response_rate=0.0)
    mixin = ChaosMixin(config)

    assert mixin.wrap_tool_call("search", lambda: "real result") == "real result"


def test_tool_failure_takes_priority_over_the_real_call():
    """A failure roll must raise before the wrapped callable is ever invoked."""
    random.seed(42)
    config = ChaosConfig(tool_failure_rate=1.0)
    mixin = ChaosMixin(config)
    calls = []

    with pytest.raises(RuntimeError):
        mixin.wrap_tool_call("search", lambda: calls.append("called"))

    assert calls == []


def test_chaos_config_to_dict_is_json_safe_and_stores_exception_name():
    config = ChaosConfig(tool_failure_rate=0.2, tool_failure_exception=ValueError)
    result = config.to_dict()

    assert result["tool_failure_rate"] == 0.2
    assert result["tool_failure_exception"] == "ValueError"
    assert isinstance(result["tool_failure_tools"], list)


def test_chaos_convenience_function_defaults_to_20_percent_tool_failure():
    config = chaos()
    assert config.tool_failure_rate == 0.2
    assert config.tool_failure_tools == []


def test_chaos_convenience_function_accepts_overrides():
    config = chaos(tool_failure_rate=0.5, tool_failure_tools=["search"])
    assert config.tool_failure_rate == 0.5
    assert config.tool_failure_tools == ["search"]


def test_no_chaos_config_by_default():
    """A ChaosConfig constructed with no arguments must be fully inert."""
    config = ChaosConfig()
    mixin = ChaosMixin(config)
    for _ in range(20):
        assert mixin.wrap_tool_call("search", lambda: "result") == "result"
