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
    """
    Interestingly, this exact code is referenced here:
    https://www.reddit.com/r/learnpython/comments/b1o0en/typeerror_ord_expected_string_of_length_1_but_int/

    For this function in this project, length is ALWAYS 2 and reverse is ALWAYS True.

    :param f: a file to read from - the point to read from is already set coming into this method
    :param length: ALWAYS 2 in this project
    :param reverse: ALWAYS True in this project
    :return: an integer representing hp, mp, xp, or gp
    """
    vals = f.read(length)
    if reverse: # appears to also be always true in the project
        vals = reversed(vals) # reverses the iterable - seems like the high order byte(s) are stored last in the file and being reversed as a result here
    value = 0
    for val in vals:
        value = value << 8
        value = value | val
    return value
