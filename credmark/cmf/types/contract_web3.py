# pylint:disable=too-many-locals, too-many-arguments

import math

from typing import (
    Optional, Sequence
)
from web3._utils.abi import get_abi_input_names

from web3._utils.events import get_event_data
from web3._utils.filters import construct_event_filter_params

# from web3._utils.abi import get_constructor_abi, merge_args_and_kwargs
# from web3._utils.contracts import encode_abi


def fetch_events(
        event,
        argument_filters=None,
        from_block=None,
        to_block=None,
        address=None,
        topics=None,
        contract_address=None,
        argument_names: Optional[Sequence[str]] = None,
        by_range: Optional[int] = None):
    """Get events using eth_getLogs API.

    This is a stateless method, as opposite to createFilter and works with
    stateless nodes like QuikNode and Infura.

    :param event: Event instance from your contract.events
    :param argument_filters:
    :param from_block: Start block. Use 0 for all history/
    :param to_block: Fetch events until this contract
    :param address:
    :param topics:
    :return:
    """

    if from_block is None:
        raise TypeError(
            "Missing mandatory keyword argument to getLogs: from_Block")

    if to_block is None:
        to_block = event.web3.eth.block_number

    # TODO: existing code reports error with multiple events with same name, different input
    # abi = event._get_event_abi()  # pylint:disable=protected-access

    # TODO: Use manual filtering now: below code is adapted from web3
    # from web3._utils.contracts import find_matching_event_abi
    event_abis = [abi for abi in event.contract_abi
                  if 'name' in abi and
                  abi['name'] == event.event_name and
                  (argument_names is None or
                   set(get_abi_input_names(abi)) == set(argument_names))]
    if len(event_abis) > 1:
        raise ValueError(
            'Multiple events found with same name and argument names')
    event_abi = event_abis[0]

    abi_codec = event.web3.codec

    # Set up any indexed event filters if needed
    argument_filters = {} if argument_filters is None else argument_filters
    _filters = dict(**argument_filters)

    if by_range is None:
        _data_filter_set, event_filter_params = construct_event_filter_params(
            event_abi,
            abi_codec,
            contract_address=event.address if contract_address is None else contract_address,
            argument_filters=_filters,
            fromBlock=from_block,
            toBlock=to_block,
            address=address,
            topics=topics,
        )

        # Call node over JSON-RPC API
        logs = event.web3.eth.getLogs(event_filter_params)

        # Convert raw binary event data to easily manipulable Python objects
        for entry in logs:
            data = {**get_event_data(abi_codec, event_abi, entry)}
            args = data['args']
            yield {**data, **args}  # type: ignore
    else:
        n_range_upper = int(
            math.ceil((int(to_block) - int(from_block) + 1) / by_range))
        for n_range in range(n_range_upper):
            _from_block = from_block + n_range * by_range
            if n_range == n_range_upper - 1:
                _to_block = to_block
            else:
                _to_block = _from_block + by_range - 1
            _data_filter_set, event_filter_params = construct_event_filter_params(
                event_abi,
                abi_codec,
                contract_address=event.address if contract_address is None else contract_address,
                argument_filters=_filters,
                fromBlock=_from_block,
                toBlock=_to_block,
                address=address,
                topics=topics,
            )

            # Call node over JSON-RPC API
            logs = event.web3.eth.getLogs(event_filter_params)

            # Convert raw binary event data to easily manipulable Python objects
            for entry in logs:
                data = {**get_event_data(abi_codec, event_abi, entry)}
                args = data['args']
                yield {**data, **args}  # type: ignore
