from unittest.mock import MagicMock, patch
import pytest

from py_clob_client_v2.client import ClobClient
from py_clob_client_v2.clob_types import FeeInfo


HOST = "https://clob.example.com"
CHAIN_ID = 137
TOKEN_ID = "0xabc123"
CONDITION_ID = "0xdeadbeef"


def _make_client() -> ClobClient:
    return ClobClient(host=HOST, chain_id=CHAIN_ID)


def _inject_market_info(client: ClobClient, token_id: str, rate: float, exponent: float):
    """Simulate getClobMarketInfo populating all cache fields."""
    client._ClobClient__fee_infos[token_id] = FeeInfo(rate=rate, exponent=exponent)
    client._ClobClient__tick_sizes[token_id] = "0.01"
    client._ClobClient__neg_risk[token_id] = False
    client._ClobClient__token_condition_map[token_id] = CONDITION_ID


class TestFeeInfoDefaults:
    def test_fee_info_defaults_are_zero(self):
        fi = FeeInfo()
        assert fi.rate == 0.0
        assert fi.exponent == 0.0

    def test_fee_info_explicit_values(self):
        fi = FeeInfo(rate=0.02, exponent=2.0)
        assert fi.rate == 0.02
        assert fi.exponent == 2.0


class TestGetFeeRateBps:
    def test_returns_cached_rate_from_fee_rates(self):
        """Uses __fee_rates cache (separate from __fee_infos)."""
        client = _make_client()
        client._ClobClient__fee_rates[TOKEN_ID] = 200
        with patch.object(client, "_get") as mock_get:
            rate = client.get_fee_rate_bps(TOKEN_ID)
        assert rate == 200
        mock_get.assert_not_called()

    def test_does_not_use_fee_infos_as_cache(self):
        """Even if __fee_infos is populated, get_fee_rate_bps fetches from endpoint."""
        client = _make_client()
        _inject_market_info(client, TOKEN_ID, rate=0.02, exponent=2.0)
        with patch.object(client, "_get", return_value={"base_fee": 200}) as mock_get:
            rate = client.get_fee_rate_bps(TOKEN_ID)
        assert rate == 200
        mock_get.assert_called_once()

    def test_get_fee_rate_via_get_fee_rate_endpoint(self):
        """Falls through to GET_FEE_RATE when token not in __fee_rates."""
        client = _make_client()
        with patch.object(client, "_get", return_value={"base_fee": 200}) as mock_get:
            rate = client.get_fee_rate_bps(TOKEN_ID)
        assert rate == 200
        mock_get.assert_called_once()

    def test_stores_in_fee_rates_cache_not_fee_infos(self):
        """Result is cached in __fee_rates; __fee_infos is not touched."""
        client = _make_client()
        with patch.object(client, "_get", return_value={"base_fee": 150}):
            client.get_fee_rate_bps(TOKEN_ID)
        assert client._ClobClient__fee_rates[TOKEN_ID] == 150
        assert TOKEN_ID not in client._ClobClient__fee_infos

    def test_no_refetch_after_fee_rates_cache_hit(self):
        """Once in __fee_rates, no further _get calls."""
        client = _make_client()
        client._ClobClient__fee_rates[TOKEN_ID] = 100
        with patch.object(client, "_get") as mock_get:
            client.get_fee_rate_bps(TOKEN_ID)
        mock_get.assert_not_called()

    def test_zero_when_base_fee_missing(self):
        client = _make_client()
        with patch.object(client, "_get", return_value={}):
            rate = client.get_fee_rate_bps(TOKEN_ID)
        assert rate == 0


class TestGetFeeExponent:
    def test_returns_cached_exponent_from_market_info(self):
        client = _make_client()
        _inject_market_info(client, TOKEN_ID, rate=0.02, exponent=2.0)
        assert client.get_fee_exponent(TOKEN_ID) == 2.0

    def test_cache_hit_any_fee_info_entry(self):
        """Any entry in __fee_infos satisfies the cache check (returns stored exponent)."""
        client = _make_client()
        # Simulate GET_FEE_RATE fallback: exponent=0
        client._ClobClient__fee_infos[TOKEN_ID] = FeeInfo(rate=0.03, exponent=0.0)
        assert client.get_fee_exponent(TOKEN_ID) == 0.0

    def test_fetches_market_info_when_not_cached(self):
        client = _make_client()
        client._ClobClient__token_condition_map[TOKEN_ID] = CONDITION_ID

        clob_market_response = {
            "t": [{"t": TOKEN_ID}],
            "mts": "0.01",
            "nr": False,
            "fd": {"r": 0.02, "e": 4.0},
        }
        with patch.object(client, "_get", return_value=clob_market_response):
            exponent = client.get_fee_exponent(TOKEN_ID)

        assert exponent == 4.0

    def test_no_refetch_after_cache_hit(self):
        """Once in fee_infos, no further _get calls for exponent."""
        client = _make_client()
        _inject_market_info(client, TOKEN_ID, rate=0.02, exponent=1.5)

        with patch.object(client, "_get") as mock_get:
            exponent = client.get_fee_exponent(TOKEN_ID)

        assert exponent == 1.5
        mock_get.assert_not_called()


class TestGetClobMarketInfo:
    def test_sets_fee_info_with_defaults_when_fd_missing(self):
        """When fd is missing from response, fee info defaults to rate=0, exponent=0."""
        client = _make_client()

        response = {
            "t": [{"t": TOKEN_ID}],
            "mts": "0.01",
            "nr": False,
        }
        with patch.object(client, "_get", return_value=response):
            client.get_clob_market_info(CONDITION_ID)

        fi = client._ClobClient__fee_infos.get(TOKEN_ID)
        assert fi is not None
        assert fi.rate == 0.0
        assert fi.exponent == 0.0

    def test_sets_fee_info_from_fd(self):
        client = _make_client()

        response = {
            "t": [{"t": TOKEN_ID}],
            "mts": "0.01",
            "nr": False,
            "fd": {"r": 0.03, "e": 2.0},
        }
        with patch.object(client, "_get", return_value=response):
            client.get_clob_market_info(CONDITION_ID)

        fi = client._ClobClient__fee_infos[TOKEN_ID]
        assert fi.rate == 0.03
        assert fi.exponent == 2.0

    def test_no_repeated_fetch_after_clob_market_info(self):
        """After getClobMarketInfo populates fee_infos, get_fee_exponent does not re-fetch.
        get_fee_rate_bps uses its own __fee_rates cache and fetches from endpoint if not set."""
        client = _make_client()
        _inject_market_info(client, TOKEN_ID, rate=0.02, exponent=2.0)

        with patch.object(client, "_get", return_value={"base_fee": 200}):
            fee_rate = client.get_fee_rate_bps(TOKEN_ID)
            fee_exponent = client.get_fee_exponent(TOKEN_ID)

        assert fee_rate == 200      # fetched from endpoint (separate __fee_rates cache)
        assert fee_exponent == 2.0  # served from __fee_infos without re-fetch


class TestEnsureMarketInfoCached:
    def test_no_refetch_when_fee_infos_has_token(self):
        """Returns immediately if token already in __fee_infos."""
        client = _make_client()
        _inject_market_info(client, TOKEN_ID, rate=0.02, exponent=2.0)

        with patch.object(client, "_get") as mock_get:
            client._ClobClient__ensure_market_info_cached(TOKEN_ID)

        mock_get.assert_not_called()

    def test_fetches_when_not_in_fee_infos(self):
        client = _make_client()
        client._ClobClient__token_condition_map[TOKEN_ID] = CONDITION_ID

        clob_market_response = {
            "t": [{"t": TOKEN_ID}],
            "mts": "0.01",
            "nr": False,
            "fd": {"r": 0.01, "e": 1.0},
        }
        with patch.object(client, "_get", return_value=clob_market_response):
            client._ClobClient__ensure_market_info_cached(TOKEN_ID)

        assert TOKEN_ID in client._ClobClient__fee_infos

    def test_get_fee_rate_endpoint_entry_blocks_refetch(self):
        """If GET_FEE_RATE stored a FeeInfo, ensureMarketInfoCached returns early."""
        client = _make_client()
        # Simulate GET_FEE_RATE fallback result
        client._ClobClient__fee_infos[TOKEN_ID] = FeeInfo(rate=0.05, exponent=0.0)
        client._ClobClient__token_condition_map[TOKEN_ID] = CONDITION_ID

        with patch.object(client, "_get") as mock_get:
            client._ClobClient__ensure_market_info_cached(TOKEN_ID)

        mock_get.assert_not_called()
