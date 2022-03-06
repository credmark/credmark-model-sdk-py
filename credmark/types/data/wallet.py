from typing import List
from .address import Address
from ..dto import DTO, IterableListDto


class Wallet(DTO):
    address: Address


class Wallets(IterableListDto):
    list: List[Wallet]