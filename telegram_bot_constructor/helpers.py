import random
import string

from . import get_redis_connection


class ObjectDoesNotExist(Exception):
    pass


class StoredObject:
    """ Abstract class for stored in redis database objects """

    MNEMONIC = ''

    def __init__(self, id_, redis_=None):
        self.redis = redis_ if redis_ is not None else get_redis_connection()
        if not type(self).exists(id_, self.redis):
            raise ObjectDoesNotExist
        self.id = id_

    @classmethod
    def create(cls, *args, **kwargs):
        redis_ = get_redis_connection()
        mnemonic = cls.MNEMONIC or cls.__name__
        last_id = redis_.get('last_%s_id' % mnemonic)
        last_id = int(last_id) if last_id is not None else 0
        redis_.sadd('%s_exists' % mnemonic, last_id)
        redis_.incr('last_%s_id' % mnemonic)
        obj = cls(last_id, redis_)
        obj.init(*args, **kwargs)
        return obj

    def init(self, *args, **kwargs):
        pass

    def delete(self):
        mnemonic = self.MNEMONIC or type(self).__name__
        self.redis.srem('%s_exists' % mnemonic, self.id)
        self.clean_up()

    def clean_up(self):
        pass

    @classmethod
    def exists(cls, id_, redis_=None):
        mnemonic = cls.MNEMONIC or cls.__name__
        redis_ = redis_ if redis_ is not None else get_redis_connection()
        exists = redis_.sismember('%s_exists' % mnemonic, id_)
        return exists

    def __eq__(self, other):
        return self.id == other.id


TOKEN_ALPHABET = string.ascii_letters + string.digits


def random_token(length=16):
    return ''.join(random.choice(TOKEN_ALPHABET) for _ in range(length))
