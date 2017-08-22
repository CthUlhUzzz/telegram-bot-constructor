import random
import string

ALPHABET = string.ascii_lowercase + string.ascii_uppercase + string.digits

ZSET = 0
HASH = 1
SET = 2


def random_token(length=16):
    return ''.join(random.choice(ALPHABET) for _ in range(length))


def redis_iter(redis, key, type):
    """ Helper generator for iterating sequences """
    assert type in (ZSET, HASH, SET)
    index = 0
    scan_function = None
    if type == HASH:
        scan_function = redis.zscan
    elif type == HASH:
        scan_function = redis.hscan
    elif type == SET:
        scan_function = redis.sscan
    while True:
        index, elements = scan_function(key, index)
        if isinstance(elements, dict):
            for e in elements.items():
                yield e
        elif isinstance(elements, list):
            for e in elements:
                if isinstance(e, list):
                    yield tuple(e)
                else:
                    yield e
        if index == 0:
            break
