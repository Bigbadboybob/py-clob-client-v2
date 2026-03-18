from dataclasses import dataclass
from typing import Optional

from .side import Side
from .signature_type_v2 import SignatureTypeV2


@dataclass
class OrderDataV2:
    """Input data for building a V2 order."""

    maker: str
    tokenId: str
    makerAmount: str
    takerAmount: str
    side: Side
    signer: Optional[str] = None
    signatureType: Optional[SignatureTypeV2] = None
    timestamp: Optional[str] = None
    metadata: Optional[str] = None
    builder: Optional[str] = None


@dataclass
class OrderV2:
    """An unsigned V2 order ready for EIP712 signing."""

    salt: str
    maker: str
    signer: str
    tokenId: str
    makerAmount: str
    takerAmount: str
    side: Side
    signatureType: SignatureTypeV2
    timestamp: str
    metadata: str
    builder: str


@dataclass
class SignedOrderV2(OrderV2):
    """A signed V2 order including the EIP712 signature."""

    signature: str = ""
