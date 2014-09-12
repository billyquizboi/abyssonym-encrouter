from sys import argv
from monster import monsters_from_table
from formation import formations_from_rom, fsets_from_rom


def get_rng_string(filename):
    f = open(filename, 'r+b')
    f.seek(0xFD00)
    rng = map(ord, f.read(0x100))
    return rng


class Route():
    def __init__(self, seed=None, rng=None, threat=0):
        self.stepseed = seed
        self.battleseed = seed
        self.stepcounter = seed
        self.battlecounter = seed
        self.threat = threat
        self.rng = rng
        self.cost = 0

    def __repr__(self):
        s = ""
        for attribute in ["stepseed", "battleseed", "stepcounter",
                          "battlecounter", "threat", "cost"]:
            s += "%s: %x\n" % (attribute, getattr(self, attribute))
        return s.strip()

    def copy(self):
        new = Route()
        for attribute in ["stepseed", "battleseed", "stepcounter",
                          "battlecounter", "threat", "rng", "cost"]:
            setattr(new, attribute, getattr(self, attribute))
        return new

    def predict_formation(self, fset):
        value = self.rng[self.battlecounter]
        value = (value + self.battleseed) & 0xFF
        value = value / 0x50
        return fset.formations[value]

    def predict_battle(self):
        value = self.rng[self.stepcounter]
        value = (value + self.stepseed) & 0xFF
        return value < (self.threat >> 8)

    def increment_step(self, rng=True):
        self.stepcounter = (self.stepcounter+1) & 0xFF
        if self.stepcounter == 0 and rng:
            self.stepseed += 0x11
            self.stepseed = self.stepseed & 0xFF

    def increment_battle(self, rng=True):
        self.battlecounter = (self.battlecounter+1) & 0xFF
        if self.battlecounter == 0 and rng:
            self.battleseed += 0x17
            self.battleseed = self.battleseed & 0xFF

    def predict_encounters(self, fset, steps, threatrate, force_threat=False):
        # note: seed changes when RNG is called and counter is at 0xFF
        # battlecounter += 0x11
        # stepcounter += 0x17
        taken, total = 0, 0
        encounters = []
        s = ""
        while True:
            steps -= 1
            taken += 1
            total += 1
            if fset.overworld:
                if force_threat or self.overworld_threatrate is None:
                    self.overworld_threatrate = threatrate
                self.threat += self.overworld_threatrate
            else:
                self.overworld_threatrate = None
                self.threat += threatrate

            self.increment_step()
            if self.predict_battle():
                self.threat = 0
                #s += "%s STEPS: " % taken
                self.increment_battle()
                formation = self.predict_formation(fset)
                s += "ENCOUNTER: " + str(formation) + "\n"
                encounters.append((total, formation))
                taken = 0
                if fset.overworld:
                    self.overworld_threatrate = threatrate
                #if steps < 0:
                #    return encounters
            if steps == 0:
                #print "%x" % self.overworld_threatrate if self.overworld_threatrate else None
                return s.strip()

    def execute_route(self, fsets, formations, line):
        force_threat = False
        line = line.strip()
        while '  ' in line:
            line = line.replace('  ', ' ')
        parameters = tuple(line.split())
        if len(parameters) == 2:
            setid, steps = parameters
        elif len(parameters) == 3:
            setid, threatrate, steps = parameters
            if threatrate[-1] == '!':
                force_threat = True
                threatrate = threatrate.strip('!')
            threatrate = int(threatrate, 0x10)

        if setid == "ev":
            steps = int(steps, 0x10)
            s = "EVENT: %s" % str(formations[steps])
            self.increment_battle(rng=False)
        elif setid == "rd":
            steps = int(steps, 0x10)
            self.increment_battle(rng=True)
        else:
            if "-" in steps:
                steps, subtract = tuple(steps.split('-'))
                steps = int(steps) - int(subtract)
            else:
                steps = int(steps)

            setid = int(setid, 0x10)
            fset = fsets[setid]
            s = self.predict_encounters(fset, steps, threatrate,
                                        force_threat=force_threat)
        return s


if __name__ == "__main__":
    filename = argv[1]
    monsters = monsters_from_table()
    formations = formations_from_rom(filename)
    fsets = fsets_from_rom(filename, formations)
    #for fset in fsets:
    #    print fset
    #    print
    seed = 244
    #seed = 0x95
    threat = 0x0
    rng = get_rng_string(filename)
    route = Route(seed, rng, threat)
    #route.predict_encounters(fset=fsets[7], steps=0x30)
    print route
    print
    for line in open(argv[2]):
        line = line.strip()
        if line[0] == "#":
            continue
        #print line
        s = route.execute_route(fsets, formations, line)
        if s:
            print s
        #print route
        #print
    print
    print route
    print
