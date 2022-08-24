import hashlib
import logging
from typing import Dict, Generator, List, Optional, Tuple

from sqlitedict import SqliteDict
from sqlitedict import logger as sqlitedict_logger

sqlitedict_logger.setLevel(logging.ERROR)

import json
import sqlite3
import zlib

from credmark.dto.encoder import json_dumps


class Singleton:
    def __new__(cls, *args, **kw):
        if not hasattr(cls, '_instance'):
            orig = super(Singleton, cls)
            cls._instance = orig.__new__(cls, *args, **kw)
        return cls._instance


class Cache(Singleton):
    _cache = {}
    _trace = False


class ContractMetaCache(Cache):
    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
        super().__init__()

    def get(self, chain_id, address):
        if chain_id not in self._cache:
            return False, {}

        needle = self._cache[chain_id].get(address, None)
        if needle is None:
            if self._trace:
                self._logger.info(f'[Cache] Not found meta: {chain_id=}/{address}')
            return False, {}

        if self._trace:
            self._logger.info(f'[Cache] Found meta: {chain_id=}/{address}')
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
                self._logger.info(f'[Cache] Save {chain_id=}/{address} '
                                  f'valid from {block_number}')


def my_encode(obj):
    return sqlite3.Binary(zlib.compress(json_dumps(obj).encode()))


def my_decode(obj):
    return json.loads(zlib.decompress(bytes(obj)))


class SqliteDB:
    exclude_slugs = ['rpc.get-latest-blocknumber']

    _trace = False
    _stats = {'total': 0, 'hit': 0, 'miss': 0, 'exclude': 0}
    _enabled = True

    def __init__(self, db_uri, tablename, flag='c',
                 db_base_uris: Optional[List[str]] = None, outer_stack=True):
        self._db = SqliteDict(db_uri, outer_stack=outer_stack, flag=flag,
                              autocommit=True, tablename=tablename,
                              encode=my_encode, decode=my_decode)
        if db_base_uris is not None:
            self._db_base = [SqliteDict(db_base_uri, outer_stack=outer_stack, flag='r',
                                        tablename=tablename,
                                        encode=my_encode, decode=my_decode)
                             for db_base_uri in db_base_uris]
        else:
            self._db_base = None
        self._logger = logging.getLogger(self.__class__.__name__)

    def close(self):
        self._db.commit()
        self._db.close()

    def commit(self):
        self._db.commit()

    def __del__(self):
        pass

    def encode(self, key):
        return hashlib.sha256(key.encode('utf-8')).hexdigest()

    def cache_exclude(self):
        self._stats['exclude'] += 1
        self._stats['total'] += 1

    def cache_hit(self):
        self._stats['hit'] += 1
        self._stats['total'] += 1

    def cache_miss(self):
        self._stats['miss'] += 1
        self._stats['total'] += 1

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    @property
    def enabled(self):
        return self._enabled


class ModelRunCache(SqliteDB):
    def __init__(self, db_uri=':memory:', flag='c',
                 db_base_uris: Optional[List[str]] = None, enabled=True):
        super().__init__(db_uri=db_uri, tablename='model_run_cache',
                         flag=flag, db_base_uris=db_base_uris)
        self._enabled = enabled

    def stats(self):
        return self._stats

    def __getitem__(self, key):
        try:
            return self._db.__getitem__(key)
        except Exception as _err:
            if self._db_base is None:
                raise _err

            for d in self._db_base:
                try:
                    return d.__getitem__(key)
                except Exception as _err2:
                    pass
            raise _err

    def __setitem__(self, key, value):
        return self._db.__setitem__(key, value)

    def __delitem__(self, key):
        return self._db.__delitem__(key)

    def log_on(self):
        self._trace = True
        self._logger.setLevel(logging.INFO)

    def log_off(self):
        self._trace = False
        self._logger.setLevel(logging.INFO)

    def keys(self):
        yield from self._db.keys()
        if self._db_base is not None:
            for d in self._db_base:
                yield from d.keys()

    def items(self):
        yield from self._db.items()
        if self._db_base is not None:
            for d in self._db_base:
                yield from d.items()

    def __iter__(self):
        yield from self._db.iterkeys()
        if self._db_base is not None:
            for d in self._db_base:
                yield from d.iterkeys()

    def values(self):
        yield from self._db.values()
        if self._db_base is not None:
            for d in self._db_base:
                yield from d.values()

    def __len__(self):
        return (self._db.__len__() +
                (0 if self._db_base is None
                else sum([len(d) for d in self._db_base])))

    def slugs(self) -> Generator[Tuple[str, str, int, str], None, None]:
        for k, v in self._db.items():
            yield (v['slug'], v['version'], v['block_number'], k)

        if self._db_base is not None:
            for d in self._db_base:
                for k, v in d.items():
                    yield (v['slug'], v['version'], v['block_number'], k)

    def encode_runkey(self, chain_id, block_number, slug, version, input):
        return super().encode(repr((slug, version, chain_id, block_number, input)))

    def get(self, chain_id, block_number, slug, version, input) -> Tuple[Optional[str], Dict]:
        if not self._enabled:
            return None, {}

        if slug in self.exclude_slugs:
            self.cache_exclude()
            return None, {}

        key = self.encode_runkey(chain_id, block_number, slug, version, input)
        needle = self._db.get(key, None)
        if needle is None:
            if self._db_base is not None:
                for d in self._db_base:
                    needle = d.get(key, None)
                    if needle is not None:
                        break

            if needle is None:
                if self._trace:
                    self._logger.info(f'[{self.__class__.__name__}] Not found: '
                                      f'{chain_id}/{block_number}/{(slug, version)}/[{input}]')
                self.cache_miss()
                return None, {}

        self.cache_hit()
        if self._trace:
            self._logger.info(f'[{self.__class__.__name__}] Found: '
                              f'{chain_id}/{block_number}/{(slug, version)}/{input}'
                              f'={needle}')

        assert needle['chain_id'] == chain_id
        assert needle['block_number'] == block_number
        assert needle['slug'] == slug
        assert needle['version'] == version
        assert needle['input'] == input

        return key, needle['output']

    def put(self, chain_id, block_number, slug, version, input, output):
        if not self._enabled or slug in self.exclude_slugs:
            return

        key = self.encode_runkey(chain_id, block_number, slug, version, input)
        if key in self._db:
            raise KeyError('No case for overwriting cache: '
                           f'{chain_id}/{block_number}/{(slug, version)}/{input}')

        if self._db_base is not None:
            for d in self._db_base:
                if key in d:
                    raise KeyError('No case for overwriting cache: '
                                   f'{chain_id}/{block_number}/{(slug, version)}/{input}')

        result = dict(chain_id=chain_id, block_number=block_number,
                      slug=slug, version=version, input=input, output=output)

        if slug != 'contract.metadata':
            if self._trace:
                self._logger.info(result)

        self._db[key] = result