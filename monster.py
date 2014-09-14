from utils import hex2int, read_multi, ENEMY_TABLE


stat_order = ['speed', 'attack', 'hit%', 'evade%', 'mblock%',
              'def', 'mdef', 'mpow']


class MonsterBlock:
    def __init__(self, name, pointer, itemptr, controlptr,
                 sketchptr, rageptr, aiptr):
        self.name = name.strip('_')
        if not self.name:
            self.name = "?????"
        self.graphicname = self.name
        self.pointer = hex2int(pointer)
        self.itemptr = hex2int(itemptr)
        self.controlptr = hex2int(controlptr)
        self.sketchptr = hex2int(sketchptr)
        self.rageptr = hex2int(rageptr)
        self.aiptr = hex2int(aiptr)
        self.stats = {}
        self.moulds = set([])
        self.width, self.height = None, None
        self.miny, self.maxy = None, None

    def set_id(self, i):
        self.id = i

    def add_mould(self, mould):
        self.moulds.add(mould)

    def read_stats(self, filename):
        global all_spells, valid_spells, items, itemids

        f = open(filename, 'r+b')
        f.seek(self.pointer)
        for key in stat_order:
            self.stats[key] = ord(f.read(1))
        self.stats['hp'] = read_multi(f, length=2)
        self.stats['mp'] = read_multi(f, length=2)
        self.stats['xp'] = read_multi(f, length=2)
        self.stats['gp'] = read_multi(f, length=2)
        self.stats['level'] = ord(f.read(1))

        self.morph = ord(f.read(1))
        self.misc1 = ord(f.read(1))
        self.misc2 = ord(f.read(1))

        f.seek(self.pointer + 20)
        self.immunities = map(ord, f.read(3))
        self.absorb = ord(f.read(1))
        self.null = ord(f.read(1))
        self.weakness = ord(f.read(1))

        f.seek(self.pointer + 27)
        self.statuses = map(ord, f.read(4))
        self.special = ord(f.read(1))

        f.seek(self.itemptr)
        self.items = map(ord, f.read(4))

        f.seek(self.controlptr)
        self.controls = map(ord, f.read(4))

        f.seek(self.sketchptr)
        self.sketches = map(ord, f.read(2))

        f.seek(self.rageptr)
        self.rages = map(ord, f.read(2))

        f.seek(self.aiptr)
        self.ai = read_multi(f, length=2)

        f.close()

    @property
    def humanoid(self):
        return self.misc1 & 0x10

    @property
    def undead(self):
        return self.misc1 & 0x80

    @property
    def floating(self):
        return self.statuses[2] & 0x1

    @property
    def inescapable(self):
        return self.misc2 & 0x08

    @property
    def escape_difficult(self):
        if self.inescapable:
            return False
        return self.misc2 & 0x01

monsterdict = {}


def monsters_from_table():
    monsters = []
    for i, line in enumerate(open(ENEMY_TABLE)):
        line = line.strip()
        if line[0] == '#':
            continue

        while '  ' in line:
            line = line.replace('  ', ' ')
        c = MonsterBlock(*line.split(','))
        c.set_id(i)
        monsterdict[i] = c
        monsters.append(c)
    return monsters
