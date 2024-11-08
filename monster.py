from utils import hex2int, read_multi, ENEMY_TABLE

"""
Looking at the location values here:
Guard_____,f0000,f3000,f3d00,f4300,f4600,f8400
Soldier___,f0020,f3004,f3d04,f4302,f4602,f8402

it seems like the data for monsters in the rom is stored like so:
[statsDataForMonster1, statsDataForMonster2, statsDataForMonster3, ...]
[itemDataForMonster1, itemDataForMonster2, itemDataForMonster3, ...]
[controlDataForMonster1, controlDataForMonster2, controlDataForMonster3, ...]
[sketchDataForMonster1, sketchDataForMonster2, sketchDataForMonster3, ...]
[rageDataForMonster1, rageDataForMonster2, rageDataForMonster3, ...]
[aiDataForMonster1, aiDataForMonster2, aiDataForMonster3, ...]

Stats data is 32 bytes and includes:
stats
morph
misc1
misc2
immunities
absorb
null
weakness
statuses
special

itemptr - 4 bytes each monster
controlptr - 4 bytes each monster
sketchptr - 2 bytes each monster
rageptr - 2 bytes each monster
aiptr - 2 bytes each monster
"""

stat_order = ['speed', 'attack', 'hit%', 'evade%', 'mblock%',
              'def', 'mdef', 'mpow']
"""The first 8 bytes of a monster's data are apparently 1 byte each of these stat values in this order"""


class MonsterBlock:
    """
    MonsterBlock stores information about a single monster including stats, items, controls, sketch, rage, and ai data.
    """

    def __init__(self, name, pointer, itemptr, controlptr,
                 sketchptr, rageptr, aiptr):
        """
        Construct a MonsterBlock object
        :param name: monster's name 10 chars in length containing 0 or more _ characters or only _ characters ie: Guard_____ or __________
        :param pointer: location in rom file of the monster's information. Note that the filename is provided as an arg to the program's main method
                        in encrouter.py as 'filename = argv[1]'
        :param itemptr: the location within rom of the monster's item data
        :param controlptr: the location within rom of the monster's control data - not sure what control data is just yet
        :param sketchptr: the location within rom of the monster's sketch data
        :param rageptr: the location within rom of the monster's rage data
        :param aiptr: the location within rom of the monster's ai data
        """
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
        f"""
        The id of a MonsterBlock object is equivalent to the line it is on in the L{ENEMY_TABLE} file
        :param i: an int
        :return: None
        """
        self.id = i

    def add_mould(self, mould):
        """
        Has something to do with formations - not sure yet what
        :param mould:
        :return:
        """
        self.moulds.add(mould)

    def read_stats(self, filename):
        f"""
        Reads the associated monster data starting with stats stored at L{self.pointer} from the given file.
        Then Reads associated itemdata for this monster at at L{self.itemptr}, control data at L{self.controlptr}
        sketch data at L{self.sketchptr}, and rage data at L{self.rageptr}, and ai data at L{self.aiptr}.

        The statuses, misc1, and misc2 fields appear to be bit arrays based on the bit masking being used.
        :param filename:
        :return:
        """
        global all_spells, valid_spells, items, itemids

        f = open(filename, 'r+b')
        f.seek(self.pointer)
        for key in stat_order:
            # these stats are values <= 255
            self.stats[key] = ord(f.read(1))
        self.stats['hp'] = read_multi(f, length=2)
        self.stats['mp'] = read_multi(f, length=2)
        self.stats['xp'] = read_multi(f, length=2)
        self.stats['gp'] = read_multi(f, length=2)
        self.stats['level'] = ord(f.read(1))

        self.morph = ord(f.read(1))
        self.misc1 = ord(f.read(1))
        self.misc2 = ord(f.read(1))

        # the previous bytes read would result in us being 20 beyond the original starting place now
        f.seek(self.pointer + 20)
        self.immunities = list(f.read(3))
        self.absorb = ord(f.read(1))
        self.null = ord(f.read(1))
        self.weakness = ord(f.read(1))

        f.seek(self.pointer + 27)
        self.statuses = list(f.read(4))
        self.special = ord(f.read(1))

        f.seek(self.itemptr)
        self.items = list(f.read(4))

        f.seek(self.controlptr)
        self.controls = list(f.read(4))

        f.seek(self.sketchptr)
        self.sketches = list(f.read(2))

        f.seek(self.rageptr)
        self.rages = list(f.read(2))

        f.seek(self.aiptr)
        self.ai = read_multi(f, length=2)

        f.close()

    @property
    def humanoid(self):
        # 0x10 == 00010000
        return self.misc1 & 0x10

    @property
    def undead(self):
        # 0x80 == 10000000
        return self.misc1 & 0x80

    @property
    def floating(self):
        # 0x1 == 00000001
        return self.statuses[2] & 0x1

    @property
    def inescapable(self):
        # 0x80 == 00001000
        return self.misc2 & 0x08

    @property
    def escape_difficult(self):
        if self.inescapable:
            return False
        # 0x1 == 00000001
        return self.misc2 & 0x01

    def __repr__(self):
        return ("'name': " + self.name + ", " +
            "'graphicname': " + self.graphicname + ", " +
            "'pointer': " + str(self.pointer) + ", " +
            "'itemptr': " + str(self.itemptr) + ", " +
            "'controlptr': " + str(self.controlptr) + ", " +
            "'sketchptr': " + str(self.sketchptr) + ", " +
            "'rageptr': " + str(self.rageptr) + ", " +
            "'aiptr': " + str(self.aiptr) + ", " +
            "'stats': " + str(self.stats) + ", " +
            "'moulds': " + str(self.moulds) + ", " +
            "'miny': " + str(self.miny) + ""
        )


monsterdict = {}


def monsters_from_table():
    f"""
    Reads each line from /tables/enemycodes.txt referenced in
     L{ENEMY_TABLE} and transforms into a L{MonsterBlock} object
     which is added to both the returned monsters list and the
     L{monsterdict} with int keys == index in monsters.

    example format from L{ENEMY_TABLE} file:
    Guard_____,f0000,f3000,f3d00,f4300,f4600,f8400

    L{MonsterBlock} constructor args to line map:
    name: Guard_____
    pointer: f0000
    itemptr: f3000
    controlptr: f3d00
    sketchptr: f4300
    rageptr: f4600
    aiptr: f8400

    :type: [MonsterBlock]
    :return: list of L{MonsterBlock} objects derived from L{ENEMY_TABLE} file
    """
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


if __name__ == "__main__":
    """This looks basically like a testing method for if you run this file as main"""
    for i, m in enumerate(monsters_from_table()):
        print(hex(i), m.name)