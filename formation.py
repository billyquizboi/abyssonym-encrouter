from utils import read_multi
from monster import monsterdict, monsters_from_table
from sys import argv


BASE_COST = 10

customcosts = {}
for line in open("tables/customcosts.txt"):
    line = line.strip()
    if line and line[0] == '#':
        continue
    while '  ' in line:
        line = line.replace('  ', ' ')
    formid, cost = tuple(line.split())
    formid = int(formid, 0x10)
    cost = int(cost)
    customcosts[formid] = cost


class Formation():
    def __init__(self, formid):
        self.formid = formid
        self.pointer = 0xf6200 + (formid*15)
        self.auxpointer = 0xf5900 + (formid*4)

    def __repr__(self):
        counter = {}
        for e in self.present_enemies:
            #name = "%s %s %s" % (e.name, e.stats['level'], e.id)
            name = e.name
            if name not in counter:
                counter[name] = 0
            counter[name] += 1
        s = ""
        for name, count in sorted(counter.items()):
            s = ', '.join([s, "%s x%s" % (name, count)])
        s = s[2:]
        #return s
        #return "%s (%x)" % (s, self.formid)
        return "%s (%x) %s" % (s, self.formid, bool(self.pincer_prohibited))

    def read_data(self, filename):
        f = open(filename, 'r+b')
        f.seek(self.pointer)
        self.mouldbyte = ord(f.read(1))
        self.enemies_present = ord(f.read(1))
        self.enemy_ids = map(ord, f.read(6))
        self.enemy_pos = map(ord, f.read(6))
        self.bosses = ord(f.read(1))

        f.seek(self.auxpointer)
        self.misc1 = ord(f.read(1))
        self.misc2 = ord(f.read(1))
        self.eventscript = ord(f.read(1))
        self.misc3 = ord(f.read(1))
        f.close()

    @property
    def mould(self):
        return self.mouldbyte >> 4

    @property
    def has_event(self):
        return bool(self.misc2 & 0x80)

    @property
    def present_enemies(self):
        return [e for e in self.enemies if e]

    @property
    def present_enemy_ids(self):
        return [e.id for e in self.present_enemies]

    def lookup_enemies(self):
        self.enemies = []
        self.big_enemy_ids = []
        for i, eid in enumerate(self.enemy_ids):
            if eid == 0xFF and not self.enemies_present & (1 << i):
                self.enemies.append(None)
                continue
            if self.bosses & (1 << i):
                eid += 0x100
            self.big_enemy_ids.append(eid)
            self.enemies.append(monsterdict[eid])
            enemy_pos = self.enemy_pos[i]
            x, y = enemy_pos >> 4, enemy_pos & 0xF
        for e in self.enemies:
            if not e:
                continue
            e.add_mould(self.mould)
        self.num_enemies = len(self.present_enemies)

    def set_big_enemy_ids(self, eids):
        self.bosses = 0
        self.enemy_ids = []
        for n, eid in enumerate(eids):
            if eid & 0x100:
                self.bosses |= (1 << n)
            if not self.enemies_present & (1 << n):
                self.bosses |= (1 << n)
            self.enemy_ids.append(eid & 0xFF)

    def read_mould(self, filename):
        mouldspecsptrs = 0x2D01A
        f = open(filename, 'r+b')
        pointer = mouldspecsptrs + (2*self.mould)
        f.seek(pointer)
        pointer = read_multi(f, length=2) | 0x20000
        for i in xrange(6):
            f.seek(pointer + (i*4))
            a, b = tuple(map(ord, f.read(2)))
            width = ord(f.read(1))
            height = ord(f.read(1))
            enemy = self.enemies[i]
            if enemy:
                enemy.update_size(width, height)

    @property
    def pincer_prohibited(self):
        return self.misc1 & 0x40

    @property
    def back_prohibited(self):
        return self.misc1 & 0x20

    @property
    def front_prohibited(self):
        return self.misc1 & 0x10

    @property
    def inescapable(self):
        return any([e.inescapable for e in self.present_enemies])

    @property
    def escape_difficult(self):
        return any([e.escape_difficult for e in self.present_enemies])

    def cost(self, weight=1.0, smokebombs=False, avoidgau=False):
        smokebombs = smokebombs and not self.inescapable
        if self.formid in customcosts:
            return customcosts[self.formid]

        if self.front_prohibited and self.back_prohibited:
            return 100 * weight

        if avoidgau and self.inescapable and self.front_prohibited:
            return BASE_COST

        cost = 1
        if not smokebombs and abs(weight) >= 1:
            cost = cost * weight * self.num_enemies
        else:
            cost = cost * weight
        if self.escape_difficult and not smokebombs:
            cost += 4 * weight
        if not self.back_prohibited:
            cost += 2
        if not (self.num_enemies == 1 or self.pincer_prohibited):
            value = 3
            if not smokebombs:
                #value = value * max(1, weight) * self.num_enemies
                value = value * self.num_enemies
            cost += value
        if self.inescapable:
            cost += 20
            if avoidgau:
                cost += 30
        cost += BASE_COST

        return cost

    @property
    def xp(self):
        xp = sum(e.stats['xp'] for e in self.present_enemies)
        #print self, xp
        return xp


class FormationSet():
    def __init__(self, setid):
        baseptr = 0xf4800
        self.setid = setid
        if self.setid <= 0xFF:
            self.pointer = baseptr + (setid * 8)
        else:
            self.pointer = baseptr + (0x100 * 8) + ((setid - 0x100) * 4)

        self.floatingcontinent = False

    @property
    def overworld(self):
        return self.setid <= 0x38

    def __repr__(self):
        s = ""
        s += "PACK ID %x\n" % self.setid
        for f in self.formations:
            s += "%s\n" % str(f)
        return s.strip()

    def read_data(self, filename):
        f = open(filename, 'r+b')
        f.seek(self.pointer)
        self.formids = []
        if self.setid <= 0xFF:
            num_encounters = 4
        else:
            num_encounters = 2
        for i in xrange(num_encounters):
            self.formids.append(read_multi(f, length=2))
        f.close()

    def set_formations(self, formations):
        self.formations = []
        for i in self.formids:
            if i & 0x8000:
                i &= 0x7FFF
                self.floatingcontinent = True
            f = [j for j in formations if j.formid == i]
            f = f[0]
            self.formations.append(f)
        self.best_formation = min(self.formations, key=lambda f: f.cost)

    def rank(self):
        return sum(f.rank() for f in self.formations) / 4.0


def formations_from_rom(filename):
    formations = [Formation(i) for i in xrange(576)]
    for f in formations:
        f.read_data(filename)
        f.lookup_enemies()
        #print f
    return formations


def fsets_from_rom(filename, formations):
    fsets = []
    for i in xrange(0x200):
        f = FormationSet(i)
        f.read_data(filename)
        f.set_formations(formations)
        fsets.append(f)

    return fsets


if __name__ == "__main__":
    filename = argv[1]
    monsters = monsters_from_table()
    for m in monsters:
        m.read_stats(filename)
    formations = formations_from_rom(filename)
    for f in formations:
        print f, f.mould
    fsets = fsets_from_rom(filename, formations)
    for fset in fsets:
        print fset
        print
