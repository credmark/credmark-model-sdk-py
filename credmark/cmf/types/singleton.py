import hashlib
import logging


class Singleton:
    def __new__(cls, *args, **kw):
        if not hasattr(cls, '_instance'):
            orig = super(Singleton, cls)
            cls._instance = orig.__new__(cls, *args, **kw)
        return cls._instance

    def encode(self, key):
        return hashlib.sha3_512(key.encode('utf-8')).hexdigest()


class ContractMetaCache(Singleton):
    _cache = {}
    _trace = False

    def get(self, chain_id, address):
        if chain_id not in self._cache:
            return False, {}

        needle = self._cache[chain_id].get(address, None)
        if needle is None:
            if self._trace:
                logging.info(f'[Cache] Not found meta: {chain_id=}/{address}')
            return False, {}

        if self._trace:
            logging.info(f'[Cache] Found meta: {chain_id=}/{address}')
        return True, needle

    def put(self, chain_id, address, meta):
        if chain_id not in self._cache:
            self._cache[chain_id] = {}

        if address not in self._cache[chain_id]:
            block_number = None
            if len(meta['contracts']) > 0:
                block_number = meta['contracts'][0]['block_number']
            self._cache[chain_id][address] = meta
            if self._trace:
                logging.info(f'[Cache] Save {chain_id=}/{address} '
                             f'valid from {block_number}')


class ModelRunCache(Singleton):
    _cache = {}
    _trace = False

    def get(self, chain_id, block_number, slug, version, input):
        if chain_id not in self._cache:
            if self._trace:
                logging.info(f'[{self.__class__.__name__}] Not found '
                             f'[{chain_id}]/{block_number}/{(slug, version)}/{input}')
            return False, {}

        needle = self._cache[chain_id].get(block_number, None)
        if needle is None:
            if self._trace:
                logging.info(f'[{self.__class__.__name__}] Not found '
                             f'{chain_id}/[{block_number}]/{(slug, version)}/{input}')
            return False, {}

        needle = needle.get((slug, version), None)
        if needle is None:
            if self._trace:
                logging.info(f'[{self.__class__.__name__}] Not found '
                             f'{chain_id}/{block_number}/[{(slug, version)}]/{input}')
            return False, {}

        encoded_input = self.encode(repr(input))
        needle = needle.get(encoded_input, None)
        if needle is None:
            if self._trace:
                logging.info(f'[{self.__class__.__name__}] Not found: '
                             f'{chain_id}/{block_number}/{(slug, version)}/[{input}]')
            return False, {}

        if self._trace:
            logging.info(f'[{self.__class__.__name__}] Found: '
                         f'{chain_id}/{block_number}/{(slug, version)}/{input}'
                         f'={needle}')
        return True, needle['output']

    def put(self, chain_id, block_number, slug, version, input, output):
        if chain_id not in self._cache:
            self._cache[chain_id] = {}

        if block_number not in self._cache[chain_id]:
            self._cache[chain_id][block_number] = {}

        if (slug, version) not in self._cache[chain_id][block_number]:
            self._cache[chain_id][block_number][(slug, version)] = {}

        repr_input = repr(input)
        encoded_input = self.encode(repr_input)
        if encoded_input in self._cache[chain_id][block_number][(slug, version)]:
            if self._trace:
                logging.info(f'[{self.__class__.__name__}] Overwriting existing '
                             f'{chain_id}/{block_number}/{(slug, version)}/{input}')

        result = dict(output=output, input=input)
        self._cache[chain_id][block_number][(slug, version)][encoded_input] = result
