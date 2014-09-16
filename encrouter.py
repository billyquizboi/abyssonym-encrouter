from sys import argv
from monster import monsters_from_table
from formation import formations_from_rom, fsets_from_rom
from Queue import PriorityQueue

STEP_VALUE = 1


fsetdict = {}


def table_from_file(filename, hexify=False):
    table = {}
    for line in open(filename):
        line = line.strip()
        if line[0] == '#':
            continue
        while '  ' in line:
            line = line.replace('  ', ' ')
        a, b = tuple(line.split())
        if hexify:
            try:
                a = int(a, 0x10)
                b = int(b, 0x10)
            except ValueError:
                continue
        table[a] = b
    return table


def get_rng_string(filename):
    f = open(filename, 'r+b')
    f.seek(0xFD00)
    rng = map(ord, f.read(0x100))
    return rng


class Route():
    def __init__(self, seed=None, rng=None, threat=0):
        self.initialseed = seed
        self.set_seed(seed)
        self.threat = threat
        self.rng = rng
        self.cost = 0
        self.travelog = ""
        self.scriptptr = 0
        self.resetting = False
        self.boundary_flag = False
        self.overworld_threatrate = None
        #self.forced_encounters = 0
        self.last_forced_encounter = None
        self.last_reset = None
        self.num_encounters = 0
        self.xp = 0
        self.weight = 1.0
        self.seen_formations = set([])

    def __repr__(self):
        s = ""
        for attribute in ["initialseed", "stepseed", "battleseed",
                          "stepcounter", "battlecounter", "threat"]:
            s += "%s: %x\n" % (attribute, getattr(self, attribute))
        for attribute in ["cost", "num_encounters"]:
            s += "%s: %s\n" % (attribute, getattr(self, attribute))
        return s.strip()

    @property
    def previous_instr(self):
        if self.scriptptr > 0:
            return Route.script[self.scriptptr-1]
        else:
            return None

    def set_seed(self, seed):
        if seed is not None:
            seed = seed & 0xFF
        self.seed = seed
        self.veldtseed = seed
        self.stepseed = seed
        self.battleseed = seed
        self.stepcounter = seed
        self.battlecounter = seed

    def copy(self):
        new = Route()
        for attribute in ["initialseed", "stepseed", "battleseed", "veldtseed",
                          "stepcounter", "battlecounter", "threat",
                          "rng", "cost", "travelog", "scriptptr", "seed",
                          "resetting", "boundary_flag", "weight",
                          "last_forced_encounter", "last_reset",
                          "overworld_threatrate", "xp", "num_encounters"]:
            setattr(new, attribute, getattr(self, attribute))
        new.seen_formations = set(self.seen_formations)
        return new

    def get_best_river(self):
        self.travelog += "*** GO TO RETURNER SAVE POINT ***\n"
        self.reset_fourteen()
        try:
            seed = Route.leterng[self.seed]
        except KeyError:
            return False

        best = None
        cost, bestcost = 0, 0
        bestnum = 0
        for i in xrange(20):
            battlecounter = Route.riversequence[seed].count(True)
            if battlecounter <= 3:
                if best is None and battlecounter == 3:
                    temp = self.copy()
                    if temp.predict_river(seed):
                        best = seed
                        bestcost = cost
                        bestnum = i
                elif battlecounter == 2:
                    temp = self.copy()
                    if temp.predict_river(seed):
                        best = seed
                        bestcost = cost
                        bestnum = i
                        break
            #self.cost += STEP_VALUE * 2
            cost += 0.1
            seed = Route.returnerrng[seed]
        if best is None:
            return False

        self.travelog += "*** MANIPULATE LETE W/ RETURNER %s TIMES ***\n" % bestnum

        self.predict_river(best)
        self.cost += bestcost
        return True

    def predict_river(self, seed):
        sequence = Route.riversequence[seed]
        formids = [0x107, 0x108, 0x107, 0x107, 0x108, 0x107, 0x108, 0x108, 0x107]
        double_pterodon = False
        for decision, formid in zip(sequence, formids):
            if decision:
                fset = fsetdict[formid]
                self.num_encounters += 1
                formation = self.predict_formation(fset)
                if formation.formid == 0x23:
                    double_pterodon = True
                self.xp += formation.xp
                cost = formation.cost(self.weight)
                self.cost += cost
                self.travelog += "RIVER: " + str(formation) + " COST: %s" % cost + "\n"
        return double_pterodon

    def predict_formation(self, fset):
        self.increment_battle(rng=True)
        value = self.rng[self.battlecounter]
        value = (value + self.battleseed) & 0xFF
        if len(fset.formations) == 4:
            value = value / 0x50
        else:
            value = value / 0xC0
        formation = fset.formations[value]
        if formation.formid < 0x200:
            self.seen_formations.add(formation.formid)
        return formation

    def predict_battle(self):
        self.increment_step(rng=True)
        value = self.rng[self.stepcounter]
        value = (value + self.stepseed) & 0xFF
        return value < (self.threat >> 8)

    def predict_veldt_formation(self):
        self.veldtseed += 1
        while True:
            self.veldtseed = self.veldtseed & 0x3F
            pack = Route.veldtpacks[self.veldtseed]
            if set(pack) & self.seen_formations:
                break
            self.veldtseed += 1

        self.increment_battle(rng=True)
        value = self.rng[self.battlecounter]
        value = (value + self.battleseed)
        while True:
            value = value & 0x07
            formid = pack[value]
            if formid in self.seen_formations:
                break
            value += 1

        formation = Route.formations[formid]
        return formation

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

    def execute_script(self):
        if self.scriptptr == Route.scriptlength:
            raise Exception("Script pointer out of bounds.")
        instr = Route.script[self.scriptptr]
        self.scriptptr += 1
        if instr.restriction:
            if instr.value is None:
                setattr(self, instr.rtype, 0)
            else:
                value = getattr(self, instr.rtype)
                if value < instr.value:
                    return False
                else:
                    setattr(self, instr.rtype, 0)
        elif instr.travel:
            self.predict_encounters(instr)
        elif instr.event:
            self.travelog += "EVENT: %s\n" % instr.formation
            if instr.formation.formid < 0x200:
                self.seen_formations.add(instr.formation.formid)
            self.increment_battle(rng=False)
            #self.increment_battle(rng=True)
            self.overworld_threatrate = None
        elif instr.random:
            formation = self.predict_formation(instr.fset)
            self.xp += formation.xp
            cost = formation.cost(self.weight)
            self.cost += cost
            self.travelog += "RANDOM EVENT: " + str(formation) + " COST: %s" % cost + "\n"
            self.overworld_threatrate = None
        elif instr.lete:
            return self.get_best_river()
            self.overworld_threatrate = None
        elif instr.weight:
            self.weight = instr.weightval

        return True

    def predict_encounters(self, instr):
        # note: seed changes when RNG is called and counter is at 0xFF
        # battlecounter += 0x11
        # stepcounter += 0x17
        taken, total = 0, 0
        steps = instr.steps
        self.boundary_flag = False

        while True:
            steps -= 1
            taken += 1
            total += 1

            if self.take_a_step(instr):
                #self.travelog += "STEP %s: \n" % taken
                #self.travelog += "%s\n" % self
                #if steps <= 1:
                if steps <= 3:
                    self.cost += 1
                    self.boundary_flag = True
                #if taken <= 2:
                if taken <= 4:
                    self.cost += 1
                taken = 0

            if steps == 0:
                return

    def take_a_step(self, instr):
        if instr.force_threat:
            self.overworld_threatrate = instr.threatrate
            threatrate = self.overworld_threatrate
        elif instr.fset.overworld:
            if self.overworld_threatrate is None:
                self.overworld_threatrate = instr.threatrate
            threatrate = self.overworld_threatrate
        else:
            self.overworld_threatrate = None
            threatrate = instr.threatrate

        self.cost += STEP_VALUE
        self.threat += threatrate
        if self.predict_battle():
            self.num_encounters += 1
            if instr.veldt:
                formation = self.predict_veldt_formation()
            else:
                formation = self.predict_formation(instr.fset)
            self.xp += formation.xp
            if instr.veldt:
                cost = formation.cost(self.weight, avoidgau=instr.avoidgau)
            else:
                cost = formation.cost(self.weight)
            self.cost += cost
            '''
            self.travelog += "%x %x %x %x %x\n" % (
                self.stepseed, self.stepcounter, self.battleseed,
                self.battlecounter, self.threat)
            '''
            self.travelog += "ENCOUNTER: " + str(formation) + " COST: %s\n" % cost
            #self.travelog += str(self.weight) + "\n"
            #self.travelog += str(self) + "\n\n"
            self.threat = 0
            if not instr.veldt and instr.fset.overworld:
                self.overworld_threatrate = instr.threatrate

            return formation

    @property
    def force_value(self):
        if self.last_forced_encounter is None:
            return None
        diff = self.num_encounters - self.last_forced_encounter
        return diff

    def check_is_boundary(self):
        instr = None
        if (self.previous_instr and self.previous_instr.travel
                and self.previous_instr.steps >= 2):
            for i in range(self.scriptptr, self.scriptlength):
                instr = Route.script[i]
                if instr.travel:
                    break
            else:
                return False
            if (not (self.previous_instr.veldt or instr.veldt) and
                    self.previous_instr.fset == instr.fset):
                return False
        return bool(instr)

    def force_additional_encounter(self):
        if not self.boundary_flag:
            self.cost += 1
        self.boundary_flag = False
        distance = self.force_value
        if distance is not None:
            if distance < 2:
                return False

        self.travelog += "*** FORCE ADDITIONAL ENCOUNTER ***\n"
        parallel = self.copy()
        parallel.travelog = ""
        avoidance = None
        while True:
            if parallel.scriptptr == Route.scriptlength:
                break

            parallel.execute_script()
            if "ENCOUNTER:" in parallel.travelog or "RANDOM EVENT:" in parallel.travelog:
                avoidance = parallel.travelog.strip().split('\n')[-1]
                assert avoidance
                avoidance = avoidance.replace("ENCOUNTER:", "AVOIDED:")
                avoidance = avoidance.replace("RANDOM EVENT:", "AVOIDED:")
                break

        self.last_forced_encounter = self.num_encounters
        step = 0
        done = False
        instr = self.previous_instr
        while True:
            step += 1
            if self.take_a_step(instr):
                done = True

            if done and (step & 1) == 0:
                break

        if avoidance:
            self.travelog += avoidance + "\n"

        return True

    @property
    def heuristic(self):
        tempthreat = self.threat
        tempcost = self.cost
        best_encounter = None
        for i in range(self.scriptptr, Route.scriptlength):
            instruction = Route.script[i]
            if instruction.event:
                pass
            elif instruction.travel and not instruction.veldt:
                if best_encounter is None:
                    best_encounter = instruction.best_encounter
                elif instruction.best_encounter.cost(self.weight) < best_encounter.cost(self.weight):
                    best_encounter = instruction.best_encounter

                tempcost += instruction.steps * STEP_VALUE
                for i in xrange(instruction.steps):
                    tempthreat += instruction.threatrate
                    #if tempthreat >= 0xFF00:
                    #if tempthreat >= 0x8000:
                    if tempthreat >= 0x2000:
                        tempcost += best_encounter.cost(self.weight)
                        best_encounter = instruction.best_encounter
                        tempthreat = 0
        return tempcost

    @property
    def reset_value(self):
        if self.last_reset is None:
            return None
        diff = self.num_encounters - self.last_reset
        return diff

    def reset_one(self):
        self.cost += 55
        self.resetting = True
        self.set_seed(self.seed+1)
        self.travelog += "*** SAVE AND RESET TO TITLE SCREEN ***\n"

    def reset_fourteen(self):
        self.resetting = False
        self.set_seed(self.seed+14)
        self.last_reset = self.num_encounters
        self.travelog += "*** SAVE AND RELOAD ***\n"

    def menu_reset_threatrate(self):
        self.cost += 1
        instr = Route.script[self.scriptptr]
        assert instr.fset.overworld
        self.overworld_threatrate = instr.threatrate
        self.travelog += "*** OPEN MENU TO RESET THREAT RATE ***\n"

    def expand(self):
        children = []
        instr = Route.script[self.scriptptr]
        if instr.veldt:
            self.travelog += "*** ENTER THE VELDT ***\n"
        if self.resetting:
            child = self.copy()
            child.reset_one()
            children.append(child)
            child = self.copy()
            child.reset_fourteen()
            children.append(child)
            #children = [c for c in children if c.execute_script()]
            return children

        if self.check_is_boundary():
            # force encounter
            child = self.copy()
            if child.force_additional_encounter():
                if child.execute_script():
                    children.append(child)

        if instr.travel:
            '''
            if (self.overworld_threatrate and instr.fset.overworld and
                    self.overworld_threatrate != instr.threatrate):
                # change threat rate
                #child = self.copy()
                #child.menu_reset_threatrate()
                #children.append(child)
                pass
            '''
            distance = self.reset_value or 0
            if self.previous_instr.travel and (distance is None or distance >= 10):
                if ((self.overworld_threatrate and not instr.fset.overworld) or
                        (instr.fset.overworld and not self.overworld_threatrate)):
                    # reset seed
                    costval = 60
                    factor = max(0, 20 - distance)
                    costval += (2 * factor)
                    if distance is None or distance >= 5:
                        child = self.copy()
                        child.reset_one()
                        child.cost += costval
                        children.append(child)
                        child = self.copy()
                        child.reset_fourteen()
                        child.cost += costval
                        children.append(child)

        if instr.lete:
            pass

        #if self.execute_script():
        #    children.append(self)
        if self.execute_script():
            children.append(self)
        #children = [c for c in children if c.execute_script()]
        return children


class Instruction():
    def __init__(self):
        self.event, self.travel = False, False
        self.restriction = False
        self.lete = False
        self.weight = False
        self.random = False
        self.veldt = False

    def __repr__(self):
        return "event" if self.event else "travel" if self.travel else "restriction" if self.restriction else "lete" if self.lete else "None"

    def set_lete(self):
        self.lete = True

    def set_veldt(self, threatrate, steps):
        self.veldt = True
        self.travel = True
        self.threatrate = threatrate
        self.steps = steps
        self.force_threat = True
        self.avoidgau = False

    def set_weight(self, weight):
        self.weight = True
        self.weightval = weight

    def set_event(self, formation, rng=False):
        self.formation = formation
        self.event = True
        self.rng = rng

    def set_random(self, fset):
        self.fset = fset
        self.random = True

    def set_travel(self, fset, threatrate, steps, force_threat):
        self.travel = True
        self.fset = fset
        self.threatrate = threatrate
        self.steps = steps
        self.force_threat = force_threat

    def set_restriction(self, rtype, value):
        self.restriction = True
        self.rtype = rtype
        if value == 0:
            self.value = None
        else:
            self.value = value

    @property
    def best_encounter(self):
        return min(self.fset.formations, key=lambda f: f.cost())


def encounter_search(routes, number=1):
    fringe = PriorityQueue()
    for r in routes:
        fringe.put((r.heuristic, r))

    counter = 0
    progress = 0
    solutions = []
    while len(solutions) < number:
        counter += 1
        p, node = fringe.get()
        if node.scriptptr == Route.scriptlength:
            solutions.append(node)
            continue

        for child in node.expand():
            fringe.put((child.heuristic, child))

        if not counter % 1000:
            size = fringe.qsize()
            nextsize = size
            while nextsize > 25000:
            #while nextsize > 1000:
                progress += 1
                print "%s/%s" % (progress, Route.scriptlength)
                newfringe = PriorityQueue()
                while fringe.qsize() > 0:
                    p, node = fringe.get()
                    if node.scriptptr >= progress:
                        newfringe.put((p, node))
                fringe = newfringe
                nextsize = fringe.qsize()
            if nextsize != size:
                print size, nextsize
            else:
                print nextsize
            #print child.scriptlength - child.scriptptr
        if fringe.qsize() == 0:
            raise Exception("No valid solutions found.")

    seeds = set([])
    while fringe.qsize() > 0:
        p, node = fringe.get()
        seeds.add(str(node.initialseed))

    print "ALL SEEDS: %s" % " ".join(sorted(seeds))
    print "%s NODES EXPANDED" % counter
    return solutions


def format_script(fsets, formations, filename):
    Route.script = []
    for line in open(filename):
        line = line.strip()
        if line[0] == "#":
            continue
        while '  ' in line:
            line = line.replace('  ', ' ')

        parameters = tuple(line.split())
        setid, threatrate, steps = parameters

        i = Instruction()
        veldted = False
        if setid == "ev":
            steps = int(steps, 0x10)
            i.set_event(formation=formations[steps])
        elif setid == "rd":
            steps = int(steps, 0x10)
            i.set_random(fset=fsets[steps])
        elif setid == "lete":
            i.set_lete()
        elif setid == "vl":
            threatrate = int(threatrate, 0x10)
            steps = int(steps, 0x10)
            i.set_veldt(threatrate=threatrate, steps=steps)
            if not veldted:
                i.avoidgau = True
                veldted = True
        elif setid == "wt":
            i.set_weight(float(steps))
        elif setid == "re":
            value = int(steps)
            i.set_restriction(rtype=threatrate, value=value)
        elif setid == "rd":
            steps = int(steps, 0x10)
            i = None
        else:
            setid = int(setid, 0x10)
            if "-" in steps:
                steps, subtract = tuple(steps.split('-'))
                steps = int(steps) - int(subtract)
            else:
                steps = int(steps)

            if threatrate[-1] == '!':
                force_threat = True
                threatrate = threatrate.strip('!')
            else:
                force_threat = False

            threatrate = int(threatrate, 0x10)
            i.set_travel(fset=fsets[setid], threatrate=threatrate,
                         steps=steps, force_threat=force_threat)

        #print i
        Route.script.append(i)
    Route.travelscript = [i for i in Route.script if i.travel]
    Route.scriptlength = len(Route.script)

    sequence = open("tables/leteriver.txt").readlines()
    sequence = [s.strip() for s in sequence]
    sequence = [True if s == "fight" else False for s in sequence]
    assert len(sequence) == 0x100
    Route.riversequence = {}
    for i in xrange(0x100):
        subseq = [True, True] + sequence[i:i+7]
        Route.riversequence[i] = subseq

    Route.leterng = table_from_file("tables/leterng.txt", hexify=True)
    assert 2 in Route.leterng
    Route.returnerrng = table_from_file("tables/returnerrng.txt", hexify=True)
    Route.fsets = dict((f.setid, f) for f in fsets)
    Route.formations = dict((f.formid, f) for f in formations)
    Route.veldtpacks = {}
    for i in range(64):
        a = i * 8
        b = (i+1) * 8
        Route.veldtpacks[i] = range(a, b)
        for j, val in enumerate(Route.veldtpacks[i]):
            formation = Route.formations[val]
            if any(e for e in formation.present_enemies if e.id > 0xFF):
                Route.veldtpacks[i][j] = None
        assert len(Route.veldtpacks[i]) == 8


if __name__ == "__main__":
    filename = argv[1]
    routefile = argv[2]
    monsters = monsters_from_table()
    for m in monsters:
        m.read_stats(filename)
    formations = formations_from_rom(filename)
    fsets = fsets_from_rom(filename, formations)
    for fset in fsets:
        fsetdict[fset.setid] = fset
    #seed = 244
    threat = 0x0
    rng = get_rng_string(filename)
    #routes = [Route(seed, rng, threat) for seed in range(0x100)]
    #routes = [Route(244, rng, threat)]
    routes = [Route(232, rng, threat)]
    #routes = [Route(21, rng, threat)]
    #routes = [Route(seed, rng, threat) for seed in [21, 232, 244]]
    format_script(fsets, formations, routefile)
    solutions = encounter_search(routes, number=10)
    f = open("report.txt", "w+")
    for solution in solutions:
        f.write("INITIAL SEED: %s\n" % solution.initialseed)
        f.write(solution.travelog + "\n")
        f.write(str(solution) + "\n\n")
        f.write("-" * 60 + "\n")
    f.close()
