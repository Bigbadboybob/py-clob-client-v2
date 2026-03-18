from unittest import TestCase

from py_clob_client_v2.clob_types import (
    CreateOrderOptions,
    MarketOrderArgsV2,
    OrderArgsV2,
    OrderSummary,
    OrderType,
)
from py_clob_client_v2.constants import AMOY, BYTES32_ZERO
from py_clob_client_v2.order_builder.builder import OrderBuilder, ROUNDING_CONFIG
from py_clob_client_v2.order_builder.constants import BUY, SELL
from py_clob_client_v2.order_builder.helpers import decimal_places, round_down, round_normal
from py_clob_client_v2.order_utils.model import Side, SignatureTypeV2
from py_clob_client_v2.signer import Signer

# publicly known private key
private_key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
chain_id = AMOY
signer = Signer(private_key=private_key, chain_id=chain_id)

TOKEN_ID = "71321045679252212594626385532706912750332728571942532289631379312455583992563"

class TestOrderBuilder(TestCase):

    def test_calculate_buy_market_price_FOK(self):
        builder = OrderBuilder(signer)

        with self.assertRaises(Exception):
            builder.calculate_buy_market_price([], 100, OrderType.FOK)

        with self.assertRaises(Exception):
            builder.calculate_buy_market_price(
                [OrderSummary(price="0.5", size="100"), OrderSummary(price="0.4", size="100")],
                100,
                OrderType.FOK,
            )

        positions = [
            OrderSummary(price="0.5", size="100"),
            OrderSummary(price="0.4", size="100"),
            OrderSummary(price="0.3", size="100"),
        ]
        self.assertEqual(builder.calculate_buy_market_price(positions, 100, OrderType.FOK), 0.5)

        positions = [
            OrderSummary(price="0.5", size="100"),
            OrderSummary(price="0.4", size="200"),
            OrderSummary(price="0.3", size="100"),
        ]
        self.assertEqual(builder.calculate_buy_market_price(positions, 100, OrderType.FOK), 0.4)

        positions = [
            OrderSummary(price="0.5", size="200"),
            OrderSummary(price="0.4", size="100"),
            OrderSummary(price="0.3", size="100"),
        ]
        self.assertEqual(builder.calculate_buy_market_price(positions, 100, OrderType.FOK), 0.5)

    def test_calculate_sell_market_price_FOK(self):
        builder = OrderBuilder(signer)

        with self.assertRaises(Exception):
            builder.calculate_sell_market_price([], 100, OrderType.FOK)

        with self.assertRaises(Exception):
            builder.calculate_sell_market_price(
                [OrderSummary(price="0.4", size="10"), OrderSummary(price="0.5", size="10")],
                100,
                OrderType.FOK,
            )

        positions = [
            OrderSummary(price="0.3", size="100"),
            OrderSummary(price="0.4", size="100"),
            OrderSummary(price="0.5", size="100"),
        ]
        self.assertEqual(builder.calculate_sell_market_price(positions, 100, OrderType.FOK), 0.5)

        positions = [
            OrderSummary(price="0.3", size="100"),
            OrderSummary(price="0.4", size="300"),
            OrderSummary(price="0.5", size="10"),
        ]
        self.assertEqual(builder.calculate_sell_market_price(positions, 100, OrderType.FOK), 0.4)

        positions = [
            OrderSummary(price="0.3", size="334"),
            OrderSummary(price="0.4", size="100"),
            OrderSummary(price="0.5", size="100"),
        ]
        self.assertEqual(builder.calculate_sell_market_price(positions, 300, OrderType.FOK), 0.3)

    def test_calculate_buy_market_price_FAK(self):
        builder = OrderBuilder(signer)

        with self.assertRaises(Exception):
            builder.calculate_buy_market_price([], 100, OrderType.FAK)

        # FAK accepts partial fills — no exception on insufficient liquidity
        positions = [
            OrderSummary(price="0.5", size="100"),
            OrderSummary(price="0.4", size="100"),
        ]
        self.assertEqual(builder.calculate_buy_market_price(positions, 100, OrderType.FAK), 0.5)

        positions = [
            OrderSummary(price="0.5", size="100"),
            OrderSummary(price="0.4", size="200"),
            OrderSummary(price="0.3", size="100"),
        ]
        self.assertEqual(builder.calculate_buy_market_price(positions, 100, OrderType.FAK), 0.4)

    def test_calculate_sell_market_price_FAK(self):
        builder = OrderBuilder(signer)

        with self.assertRaises(Exception):
            builder.calculate_sell_market_price([], 100, OrderType.FAK)

        # FAK accepts partial fills — returns positions[0].price (lowest bid) on insufficient liquidity
        positions = [
            OrderSummary(price="0.3", size="10"),
            OrderSummary(price="0.4", size="10"),
        ]
        self.assertEqual(builder.calculate_sell_market_price(positions, 100, OrderType.FAK), 0.3)

        positions = [
            OrderSummary(price="0.3", size="100"),
            OrderSummary(price="0.4", size="300"),
            OrderSummary(price="0.5", size="10"),
        ]
        self.assertEqual(builder.calculate_sell_market_price(positions, 100, OrderType.FAK), 0.4)

    def test_get_market_order_amounts_buy_0_1(self):
        builder = OrderBuilder(signer)
        delta_price = 0.1
        delta_size = 0.01
        amount = 0.01
        while amount <= 1000:
            price = 0.1
            while price <= 1:
                side, maker, taker = builder.get_market_order_amounts(
                    BUY, amount, price, ROUNDING_CONFIG["0.1"]
                )
                self.assertEqual(side, Side.BUY)
                self.assertEqual(decimal_places(maker), 0)
                self.assertEqual(decimal_places(taker), 0)
                self.assertGreaterEqual(
                    round_normal(maker / taker, 2), round_normal(price, 2)
                )
                price = round_normal(price + delta_price, 1)
            amount = round_normal(amount + delta_size, 2)

    def test_get_market_order_amounts_buy_0_01(self):
        builder = OrderBuilder(signer)
        delta_price = 0.01
        delta_size = 0.01
        amount = 0.01
        while amount <= 100:
            price = 0.01
            while price <= 1:
                side, maker, taker = builder.get_market_order_amounts(
                    BUY, amount, price, ROUNDING_CONFIG["0.01"]
                )
                self.assertEqual(side, Side.BUY)
                self.assertEqual(decimal_places(maker), 0)
                self.assertEqual(decimal_places(taker), 0)
                # V2 uses round_down for raw_price; compare against round_down(price, 2)
                # to match the actual price used in computation (avoids float drift issues)
                self.assertGreaterEqual(
                    round_normal(maker / taker, 4), round_down(price, 2)
                )
                price = round_normal(price + delta_price, 2)
            amount = round_normal(amount + delta_size, 2)

    def test_get_market_order_amounts_buy_0_001(self):
        builder = OrderBuilder(signer)
        delta_price = 0.001
        delta_size = 0.01
        amount = 0.01
        while amount <= 10:
            price = 0.001
            while price <= 1:
                side, maker, taker = builder.get_market_order_amounts(
                    BUY, amount, price, ROUNDING_CONFIG["0.001"]
                )
                self.assertEqual(side, Side.BUY)
                self.assertEqual(decimal_places(maker), 0)
                self.assertEqual(decimal_places(taker), 0)
                self.assertGreaterEqual(
                    round_normal(maker / taker, 6), round_normal(price, 6)
                )
                price = round_normal(price + delta_price, 3)
            amount = round_normal(amount + delta_size, 2)

    def test_get_market_order_amounts_buy_0_0001(self):
        builder = OrderBuilder(signer)
        delta_price = 0.0001
        delta_size = 0.01
        amount = 0.01
        while amount <= 1:
            price = 0.0001
            while price <= 1:
                side, maker, taker = builder.get_market_order_amounts(
                    BUY, amount, price, ROUNDING_CONFIG["0.0001"]
                )
                self.assertEqual(side, Side.BUY)
                self.assertEqual(decimal_places(maker), 0)
                self.assertEqual(decimal_places(taker), 0)
                # V2 uses round_down for raw_price; compare against round_down(price, 4)
                self.assertGreaterEqual(
                    round_normal(maker / taker, 8), round_down(price, 4)
                )
                price = round_normal(price + delta_price, 4)
            amount = round_normal(amount + delta_size, 2)

    def test_get_market_order_amounts_sell_0_1(self):
        builder = OrderBuilder(signer)
        delta_price = 0.1
        delta_size = 0.01
        amount = 0.01
        while amount <= 1000:
            price = 0.1
            while price <= 1:
                side, maker, taker = builder.get_market_order_amounts(
                    SELL, amount, price, ROUNDING_CONFIG["0.1"]
                )
                self.assertEqual(side, Side.SELL)
                self.assertEqual(decimal_places(maker), 0)
                self.assertEqual(decimal_places(taker), 0)
                self.assertGreaterEqual(
                    round_normal(maker / taker, 2), round_normal(price, 2)
                )
                price = round_normal(price + delta_price, 1)
            amount = round_normal(amount + delta_size, 2)

    def test_get_market_order_amounts_sell_0_01(self):
        builder = OrderBuilder(signer)
        delta_price = 0.01
        delta_size = 0.01
        amount = 0.01
        while amount <= 100:
            price = 0.01
            while price <= 1:
                side, maker, taker = builder.get_market_order_amounts(
                    SELL, amount, price, ROUNDING_CONFIG["0.01"]
                )
                self.assertEqual(side, Side.SELL)
                self.assertEqual(decimal_places(maker), 0)
                self.assertEqual(decimal_places(taker), 0)
                self.assertGreaterEqual(
                    round_normal(maker / taker, 4), round_normal(price, 4)
                )
                price = round_normal(price + delta_price, 2)
            amount = round_normal(amount + delta_size, 2)

    def test_get_market_order_amounts_sell_0_001(self):
        builder = OrderBuilder(signer)
        delta_price = 0.001
        delta_size = 0.01
        amount = 0.01
        while amount <= 10:
            price = 0.001
            while price <= 1:
                side, maker, taker = builder.get_market_order_amounts(
                    SELL, amount, price, ROUNDING_CONFIG["0.001"]
                )
                self.assertEqual(side, Side.SELL)
                self.assertEqual(decimal_places(maker), 0)
                self.assertEqual(decimal_places(taker), 0)
                self.assertGreaterEqual(
                    round_normal(maker / taker, 6), round_normal(price, 6)
                )
                price = round_normal(price + delta_price, 3)
            amount = round_normal(amount + delta_size, 2)

    def test_get_market_order_amounts_sell_0_0001(self):
        builder = OrderBuilder(signer)
        delta_price = 0.0001
        delta_size = 0.01
        amount = 0.01
        while amount <= 1:
            price = 0.0001
            while price <= 1:
                side, maker, taker = builder.get_market_order_amounts(
                    SELL, amount, price, ROUNDING_CONFIG["0.0001"]
                )
                self.assertEqual(side, Side.SELL)
                self.assertEqual(decimal_places(maker), 0)
                self.assertEqual(decimal_places(taker), 0)
                # V2 uses round_down for raw_price; compare against round_down(price, 4)
                self.assertGreaterEqual(
                    round_normal(taker / maker, 8), round_down(price, 4)
                )
                price = round_normal(price + delta_price, 4)
            amount = round_normal(amount + delta_size, 2)

    def test_get_order_amounts_buy_0_1(self):
        builder = OrderBuilder(signer)
        delta_price = 0.1
        delta_size = 0.01
        size = 0.01
        while size <= 1000:
            price = 0.1
            while price <= 1:
                side, maker, taker = builder.get_order_amounts(
                    BUY, size, price, ROUNDING_CONFIG["0.1"]
                )
                self.assertEqual(side, Side.BUY)
                self.assertEqual(decimal_places(maker), 0)
                self.assertEqual(decimal_places(taker), 0)
                self.assertGreaterEqual(
                    round_normal(maker / taker, 2), round_normal(price, 2)
                )
                price = round_normal(price + delta_price, 1)
            size = round_normal(size + delta_size, 2)

    def test_get_order_amounts_buy_0_01(self):
        builder = OrderBuilder(signer)
        delta_price = 0.01
        delta_size = 0.01
        size = 0.01
        while size <= 100:
            price = 0.01
            while price <= 1:
                side, maker, taker = builder.get_order_amounts(
                    BUY, size, price, ROUNDING_CONFIG["0.01"]
                )
                self.assertEqual(side, Side.BUY)
                self.assertEqual(decimal_places(maker), 0)
                self.assertEqual(decimal_places(taker), 0)
                self.assertGreaterEqual(
                    round_normal(maker / taker, 4), round_normal(price, 4)
                )
                price = round_normal(price + delta_price, 2)
            size = round_normal(size + delta_size, 2)

    def test_get_order_amounts_buy_0_001(self):
        builder = OrderBuilder(signer)
        delta_price = 0.001
        delta_size = 0.01
        size = 0.01
        while size <= 10:
            price = 0.001
            while price <= 1:
                side, maker, taker = builder.get_order_amounts(
                    BUY, size, price, ROUNDING_CONFIG["0.001"]
                )
                self.assertEqual(side, Side.BUY)
                self.assertEqual(decimal_places(maker), 0)
                self.assertEqual(decimal_places(taker), 0)
                self.assertGreaterEqual(
                    round_normal(maker / taker, 6), round_normal(price, 6)
                )
                price = round_normal(price + delta_price, 3)
            size = round_normal(size + delta_size, 2)

    def test_get_order_amounts_buy_0_0001(self):
        builder = OrderBuilder(signer)
        delta_price = 0.0001
        delta_size = 0.01
        size = 0.01
        while size <= 1:
            price = 0.0001
            while price <= 1:
                side, maker, taker = builder.get_order_amounts(
                    BUY, size, price, ROUNDING_CONFIG["0.0001"]
                )
                self.assertEqual(side, Side.BUY)
                self.assertEqual(decimal_places(maker), 0)
                self.assertEqual(decimal_places(taker), 0)
                self.assertGreaterEqual(
                    round_normal(maker / taker, 8), round_normal(price, 8)
                )
                price = round_normal(price + delta_price, 4)
            size = round_normal(size + delta_size, 2)

    def test_get_order_amounts_sell_0_1(self):
        builder = OrderBuilder(signer)
        delta_price = 0.1
        delta_size = 0.01
        size = 0.01
        while size <= 1000:
            price = 0.1
            while price <= 1:
                side, maker, taker = builder.get_order_amounts(
                    SELL, size, price, ROUNDING_CONFIG["0.1"]
                )
                self.assertEqual(side, Side.SELL)
                self.assertEqual(decimal_places(maker), 0)
                self.assertEqual(decimal_places(taker), 0)
                price = round_normal(price + delta_price, 1)
            size = round_normal(size + delta_size, 2)

    def test_get_order_amounts_sell_0_01(self):
        builder = OrderBuilder(signer)
        delta_price = 0.01
        delta_size = 0.01
        size = 0.01
        while size <= 100:
            price = 0.01
            while price <= 1:
                side, maker, taker = builder.get_order_amounts(
                    SELL, size, price, ROUNDING_CONFIG["0.01"]
                )
                self.assertEqual(side, Side.SELL)
                self.assertEqual(decimal_places(maker), 0)
                self.assertEqual(decimal_places(taker), 0)
                price = round_normal(price + delta_price, 2)
            size = round_normal(size + delta_size, 2)

    def test_get_order_amounts_sell_0_001(self):
        builder = OrderBuilder(signer)
        delta_price = 0.001
        delta_size = 0.01
        size = 0.01
        while size <= 10:
            price = 0.001
            while price <= 1:
                side, maker, taker = builder.get_order_amounts(
                    SELL, size, price, ROUNDING_CONFIG["0.001"]
                )
                self.assertEqual(side, Side.SELL)
                self.assertEqual(decimal_places(maker), 0)
                self.assertEqual(decimal_places(taker), 0)
                price = round_normal(price + delta_price, 3)
            size = round_normal(size + delta_size, 2)

    def test_get_order_amounts_sell_0_0001(self):
        builder = OrderBuilder(signer)
        delta_price = 0.0001
        delta_size = 0.01
        size = 0.01
        while size <= 1:
            price = 0.0001
            while price <= 1:
                side, maker, taker = builder.get_order_amounts(
                    SELL, size, price, ROUNDING_CONFIG["0.0001"]
                )
                self.assertEqual(side, Side.SELL)
                self.assertEqual(decimal_places(maker), 0)
                self.assertEqual(decimal_places(taker), 0)
                price = round_normal(price + delta_price, 4)
            size = round_normal(size + delta_size, 2)

    def _assert_signed_order_v2(self, order):
        self.assertIsNotNone(order.salt)
        self.assertIsNotNone(order.maker)
        self.assertIsNotNone(order.signer)
        self.assertIsNotNone(order.tokenId)
        self.assertIsNotNone(order.makerAmount)
        self.assertIsNotNone(order.takerAmount)
        self.assertIsNotNone(order.signature)
        self.assertIsNotNone(order.timestamp)
        self.assertIsNotNone(order.metadata)
        self.assertIsNotNone(order.builder)
        # V2 has no nonce or feeRateBps
        self.assertFalse(hasattr(order, "nonce"))
        self.assertFalse(hasattr(order, "feeRateBps"))

    def test_build_order_buy_0_1(self):
        builder = OrderBuilder(signer)
        order = builder.build_order(
            OrderArgsV2(token_id=TOKEN_ID, price=0.5, size=100, side=BUY),
            CreateOrderOptions(tick_size="0.1", neg_risk=False),
        )
        self._assert_signed_order_v2(order)
        self.assertEqual(order.side, Side.BUY)
        self.assertEqual(order.makerAmount, "50000000")
        self.assertEqual(order.takerAmount, "100000000")

    def test_build_order_sell_0_1(self):
        builder = OrderBuilder(signer)
        order = builder.build_order(
            OrderArgsV2(token_id=TOKEN_ID, price=0.5, size=100, side=SELL),
            CreateOrderOptions(tick_size="0.1", neg_risk=False),
        )
        self._assert_signed_order_v2(order)
        self.assertEqual(order.side, Side.SELL)
        self.assertEqual(order.makerAmount, "100000000")
        self.assertEqual(order.takerAmount, "50000000")

    def test_build_order_0_01(self):
        builder = OrderBuilder(signer)
        for side in [BUY, SELL]:
            order = builder.build_order(
                OrderArgsV2(token_id=TOKEN_ID, price=0.56, size=21.04, side=side),
                CreateOrderOptions(tick_size="0.01", neg_risk=False),
            )
            self._assert_signed_order_v2(order)
            if side == BUY:
                self.assertEqual(order.makerAmount, "11782400")
                self.assertEqual(order.takerAmount, "21040000")
            else:
                self.assertEqual(order.makerAmount, "21040000")
                self.assertEqual(order.takerAmount, "11782400")

    def test_build_order_0_001(self):
        builder = OrderBuilder(signer)
        for side in [BUY, SELL]:
            order = builder.build_order(
                OrderArgsV2(token_id=TOKEN_ID, price=0.056, size=21.04, side=side),
                CreateOrderOptions(tick_size="0.001", neg_risk=False),
            )
            self._assert_signed_order_v2(order)
            if side == BUY:
                self.assertEqual(order.makerAmount, "1178240")
                self.assertEqual(order.takerAmount, "21040000")
            else:
                self.assertEqual(order.makerAmount, "21040000")
                self.assertEqual(order.takerAmount, "1178240")

    def test_build_order_0_0001(self):
        builder = OrderBuilder(signer)
        for side in [BUY, SELL]:
            order = builder.build_order(
                OrderArgsV2(token_id=TOKEN_ID, price=0.0056, size=21.04, side=side),
                CreateOrderOptions(tick_size="0.0001", neg_risk=False),
            )
            self._assert_signed_order_v2(order)
            if side == BUY:
                self.assertEqual(order.makerAmount, "117824")
                self.assertEqual(order.takerAmount, "21040000")
            else:
                self.assertEqual(order.makerAmount, "21040000")
                self.assertEqual(order.takerAmount, "117824")

    def test_build_order_precision(self):
        # price=0.82, size=20.0 — tests rounding precision at 0.01 tick
        builder = OrderBuilder(signer)
        order = builder.build_order(
            OrderArgsV2(token_id=TOKEN_ID, price=0.82, size=20.0, side=BUY),
            CreateOrderOptions(tick_size="0.01", neg_risk=False),
        )
        self._assert_signed_order_v2(order)
        self.assertEqual(order.makerAmount, "16400000")
        self.assertEqual(order.takerAmount, "20000000")

    def test_build_order_neg_risk(self):
        builder = OrderBuilder(signer)
        for tick_size, price in [("0.1", 0.5), ("0.01", 0.56), ("0.001", 0.056), ("0.0001", 0.0056)]:
            for side in [BUY, SELL]:
                order = builder.build_order(
                    OrderArgsV2(token_id=TOKEN_ID, price=price, size=10, side=side),
                    CreateOrderOptions(tick_size=tick_size, neg_risk=True),
                )
                self._assert_signed_order_v2(order)

    def test_build_order_with_builder_code(self):
        builder = OrderBuilder(signer)
        builder_code = "0x" + "ab" * 32
        order = builder.build_order(
            OrderArgsV2(token_id=TOKEN_ID, price=0.5, size=100, side=BUY, builder_code=builder_code),
            CreateOrderOptions(tick_size="0.1", neg_risk=False),
        )
        self._assert_signed_order_v2(order)
        self.assertEqual(order.builder, builder_code)

    def test_build_order_poly_proxy_signature_type(self):
        b = OrderBuilder(signer, signature_type=SignatureTypeV2.POLY_PROXY)
        order = b.build_order(
            OrderArgsV2(token_id=TOKEN_ID, price=0.5, size=10, side=BUY),
            CreateOrderOptions(tick_size="0.1", neg_risk=False),
        )
        self._assert_signed_order_v2(order)
        self.assertEqual(order.signatureType, SignatureTypeV2.POLY_PROXY)

    def test_build_order_gnosis_safe_signature_type(self):
        b = OrderBuilder(signer, signature_type=SignatureTypeV2.POLY_GNOSIS_SAFE)
        order = b.build_order(
            OrderArgsV2(token_id=TOKEN_ID, price=0.5, size=10, side=BUY),
            CreateOrderOptions(tick_size="0.1", neg_risk=False),
        )
        self._assert_signed_order_v2(order)
        self.assertEqual(order.signatureType, SignatureTypeV2.POLY_GNOSIS_SAFE)

    def test_build_market_order_buy_0_1(self):
        builder = OrderBuilder(signer)
        order = builder.build_market_order(
            MarketOrderArgsV2(token_id=TOKEN_ID, amount=50, side=BUY, price=0.5),
            CreateOrderOptions(tick_size="0.1", neg_risk=False),
        )
        self._assert_signed_order_v2(order)
        self.assertEqual(order.side, Side.BUY)

    def test_build_market_order_sell_0_1(self):
        builder = OrderBuilder(signer)
        order = builder.build_market_order(
            MarketOrderArgsV2(token_id=TOKEN_ID, amount=100, side=SELL, price=0.5),
            CreateOrderOptions(tick_size="0.1", neg_risk=False),
        )
        self._assert_signed_order_v2(order)
        self.assertEqual(order.side, Side.SELL)

    def test_build_market_order_0_01(self):
        builder = OrderBuilder(signer)
        for side in [BUY, SELL]:
            order = builder.build_market_order(
                MarketOrderArgsV2(token_id=TOKEN_ID, amount=21.04, side=side, price=0.56),
                CreateOrderOptions(tick_size="0.01", neg_risk=False),
            )
            self._assert_signed_order_v2(order)

    def test_build_market_order_0_001(self):
        builder = OrderBuilder(signer)
        for side in [BUY, SELL]:
            order = builder.build_market_order(
                MarketOrderArgsV2(token_id=TOKEN_ID, amount=21.04, side=side, price=0.056),
                CreateOrderOptions(tick_size="0.001", neg_risk=False),
            )
            self._assert_signed_order_v2(order)

    def test_build_market_order_0_0001(self):
        builder = OrderBuilder(signer)
        for side in [BUY, SELL]:
            order = builder.build_market_order(
                MarketOrderArgsV2(token_id=TOKEN_ID, amount=10, side=side, price=0.0056),
                CreateOrderOptions(tick_size="0.0001", neg_risk=False),
            )
            self._assert_signed_order_v2(order)

    def test_build_market_order_neg_risk(self):
        builder = OrderBuilder(signer)
        for tick_size, price in [("0.1", 0.5), ("0.01", 0.56), ("0.001", 0.056), ("0.0001", 0.0056)]:
            for side in [BUY, SELL]:
                order = builder.build_market_order(
                    MarketOrderArgsV2(token_id=TOKEN_ID, amount=10, side=side, price=price),
                    CreateOrderOptions(tick_size=tick_size, neg_risk=True),
                )
                self._assert_signed_order_v2(order)

    def test_build_market_order_with_builder_code(self):
        builder = OrderBuilder(signer)
        builder_code = "0x" + "cd" * 32
        order = builder.build_market_order(
            MarketOrderArgsV2(
                token_id=TOKEN_ID, amount=50, side=BUY, price=0.5, builder_code=builder_code
            ),
            CreateOrderOptions(tick_size="0.1", neg_risk=False),
        )
        self._assert_signed_order_v2(order)
        self.assertEqual(order.builder, builder_code)

    def test_platform_fee_price_0_5(self):
        self.assertAlmostEqual(_platform_fee(50, 0.5, 0.25, 2), 1.5625, places=6)

    def test_platform_fee_price_0_3(self):
        self.assertAlmostEqual(_platform_fee(30, 0.3, 0.25, 2), 1.1025, places=6)

    def test_platform_fee_price_0_1(self):
        self.assertAlmostEqual(_platform_fee(10, 0.1, 0.25, 2), 0.2025, places=6)

    def test_platform_fee_price_0_05(self):
        self.assertAlmostEqual(_platform_fee(5, 0.05, 0.25, 2), 0.05640625, places=6)

    def test_platform_fee_price_0_01(self):
        self.assertAlmostEqual(_platform_fee(1, 0.01, 0.25, 2), 0.00245025, places=6)

    def test_platform_fee_symmetric_0_7(self):
        # price=0.7 is symmetric with price=0.3
        self.assertAlmostEqual(_platform_fee(70, 0.7, 0.25, 2), 1.1025, places=6)

    def test_platform_fee_symmetric_0_9(self):
        # price=0.9 is symmetric with price=0.1
        self.assertAlmostEqual(_platform_fee(90, 0.9, 0.25, 2), 0.2025, places=6)

    def test_platform_fee_symmetric_0_95(self):
        self.assertAlmostEqual(_platform_fee(95, 0.95, 0.25, 2), 0.05640625, places=6)

    def test_platform_fee_symmetric_0_99(self):
        self.assertAlmostEqual(_platform_fee(99, 0.99, 0.25, 2), 0.00245025, places=6)

    def test_platform_fee_c_125_5(self):
        self.assertAlmostEqual(_platform_fee(62.75, 0.5, 0.25, 2), 1.9609375, places=6)

    def test_builder_fee_1pct(self):
        # 1% on 100 tokens at 50c → fee = 0.5
        self.assertAlmostEqual(_builder_fee(50, 0.01), 0.5, places=6)

    def test_builder_fee_5pct(self):
        # 5% on 200 tokens at 75c → fee = 7.5
        self.assertAlmostEqual(_builder_fee(150, 0.05), 7.5, places=6)

    def test_effective_platform_fee_only(self):
        budget, price, fee_rate, fee_exponent = 50, 0.5, 0.25, 2
        effective = _calculate_effective(budget, price, fee_rate, fee_exponent)
        platform_fee = _platform_fee(effective, price, fee_rate, fee_exponent)
        self.assertAlmostEqual(effective + platform_fee, budget, places=10)

    def test_effective_builder_fee_only(self):
        budget, price, builder_rate = 50, 0.5, 0.01
        effective = _calculate_effective(budget, price, 0, 0, builder_rate)
        builder_fee = _builder_fee(effective, builder_rate)
        self.assertAlmostEqual(effective + builder_fee, budget, places=10)

    def test_effective_combined_fees(self):
        budget, price, fee_rate, fee_exponent, builder_rate = 50, 0.5, 0.25, 2, 0.01
        effective = _calculate_effective(budget, price, fee_rate, fee_exponent, builder_rate)
        platform_fee = _platform_fee(effective, price, fee_rate, fee_exponent)
        builder_fee = _builder_fee(effective, builder_rate)
        self.assertAlmostEqual(effective + platform_fee + builder_fee, budget, places=10)

    def test_combined_platform_and_builder_fee(self):
        price, contracts, fee_rate, fee_exponent, builder_rate = 0.5, 100, 0.25, 2, 0.01
        amount_usd = contracts * price
        platform_fee = _platform_fee(amount_usd, price, fee_rate, fee_exponent)
        builder_fee = _builder_fee(amount_usd, builder_rate)
        self.assertAlmostEqual(platform_fee, 1.5625, places=6)
        self.assertAlmostEqual(builder_fee, 0.5, places=6)
        self.assertAlmostEqual(platform_fee + builder_fee, 2.0625, places=6)

# Fee math helpers
def _platform_fee(amount_usd: float, price: float, fee_rate: float, fee_exponent: int) -> float:
    platform_fee_rate = fee_rate * (price * (1 - price)) ** fee_exponent
    return (amount_usd / price) * platform_fee_rate

def _builder_fee(amount_usd: float, builder_taker_fee_rate: float) -> float:
    return amount_usd * builder_taker_fee_rate

def _calculate_effective(
    budget: float,
    price: float,
    fee_rate: float,
    fee_exponent: int,
    builder_taker_fee_rate: float = 0,
) -> float:
    platform_fee_rate = fee_rate * (price * (1 - price)) ** fee_exponent
    return budget / (1 + platform_fee_rate / price + builder_taker_fee_rate)
