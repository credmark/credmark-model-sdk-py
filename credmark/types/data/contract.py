import re
from typing import (
    Dict,
    Any,
    Union,
    List,
)

from web3.contract import Contract as Web3Contract

import credmark.model
from credmark.types.data.address import Address
from credmark.types.data.json_dto import JsonSerializableObject
from credmark.types.dto import DTO, DTOField, PrivateAttr


class Hex0xStr(str):
    @classmethod
    def __modify_schema__(cls, field_schema: Dict[str, Any]) -> None:
        field_schema.update(type='string', format='json-string')

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, hex_0x_str: str) -> str:
        # Hex0xStr
        # (?:0x?)?[\p{XDigit}]+$
        # '^0x[0-9a-fA-F]+$'

        # r_hex_short = r'\s*(?:#|0x)?([0-9a-f])([0-9a-f])([0-9a-f])([0-9a-f])?\s*'
        r_hex_long = r'\s*(?:#|0x)?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})?\s*'

        m = re.fullmatch(r_hex_long, hex_0x_str)
        if not m:
            raise ValueError('Unknown no-0x-prefix hex: {hex_0x_str}')
        return hex_0x_str


class Contract(DTO):
    name: Union[str, None] = None
    address: Address = DTOField(..., description='Contract address')
    deploy_tx_hash: Union[str, None] = None
    constructor_args: Union[str, None] = None
    protocol: Union[str, None] = None
    product: Union[str, None] = None
    abi_hash: Union[str, None] = None
    abi: Union[List[JsonSerializableObject], None] = None
    _instance: Union[Web3Contract, None] = PrivateAttr(default=None)

    class Config:
        arbitrary_types_allowed = True
        underscore_attrs_are_private = True

    def __init__(self, **data):
        super().__init__(**data)
        self._instance = None

    @property
    def instance(self):
        if self._instance is None:
            if self.address is not None:
                context = credmark.model.ModelContext.current_context
                # TODO: Check if self.abi is None and fetch if necessary
                self._instance = context.web3.eth.contract(
                    address=context.web3.toChecksumAddress(self.address),
                    abi=self.abi
                )
            else:
                raise ValueError('Contract address is None. Unable to create contract')
        return self._instance

    @property
    def functions(self):
        return self.instance.functions
