from os import path

ENEMY_TABLE = path.join("tables", "enemycodes.txt")


def hex2int(hexstr):
    return int(hexstr, 16)


def int2bytes(value, length=2, reverse=True):
    # reverse=True means high-order byte first
    bs = []
    while value:
        bs.append(value & 255)
        value = value >> 8

    while len(bs) < length:
        bs.append(0)

    if not reverse:
        bs = reversed(bs)

    return bs[:length]


def read_multi(f, length=2, reverse=True):
    vals = map(ord, f.read(length))
    if reverse:
        vals = reversed(vals)
    value = 0
    for val in vals:
        value = value << 8
        value = value | val
    return value
