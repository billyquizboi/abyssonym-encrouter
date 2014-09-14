from utils import read_multi
from math import log
from monster import monsterdict, monsters_from_table
from sys import argv


class Formation():
    def __init__(self, formid):
        self.formid = formid
        self.pointer = 0xf6200 + (formid*15)
        self.auxpointer = 0xf5900 + (formid*4)

    def __repr__(self):
        counter = {}
        for e in self.present_enemies:
            if e.name not in counter:
                counter[e.name] = 0
            counter[e.name] += 1
        s = ""
        for name, count in sorted(counter.items()):
            s = ', '.join([s, "%s x%s" % (name, count)])
        s = s[2:]
        #return s
        return "%s (%x) cost %s" % (s, self.formid, self.cost)

    def read_data(self, filename):
        f = open(filename, 'r+b')
        f.seek(self.pointer)
        self.mouldbyte = ord(f.read(1))
        self.mould = self.mouldbyte >> 4
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
    def inescapable(self):
        return any([e.inescapable for e in self.present_enemies])

    @property
    def escape_difficult(self):
        return any([e.escape_difficult for e in self.present_enemies])

    @property
    def cost(self):
        #return 1000
        cost = 5
        if not (self.num_enemies == 1 or self.pincer_prohibited):
            cost += 3
        if not self.back_prohibited:
            cost += 2
        if self.inescapable:
            cost += 15
        elif self.escape_difficult:
            cost += 5
        cost += self.num_enemies

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
        self.pointer = baseptr + (setid * 8)
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
        for i in xrange(4):
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
    for i in xrange(0x100):
        f = FormationSet(i)
        f.read_data(filename)
        f.set_formations(formations)
        fsets.append(f)
        #print f
        #print

    return fsets


if __name__ == "__main__":
    filename = argv[1]
    monsters = monsters_from_table()
    for m in monsters:
        m.read_stats(filename)
    formations = formations_from_rom(filename)
    for f in formations:
        print f
    fsets = fsets_from_rom(filename, formations)
    for fset in fsets:
        print fset
        print
