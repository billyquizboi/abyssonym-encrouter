from sys import argv
from monster import monsters_from_table
from formation import formations_from_rom, fsets_from_rom
from Queue import PriorityQueue

STEP_VALUE = 0.1
#STEP_VALUE = 1


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

    def __repr__(self):
        s = ""
        for attribute in ["stepseed", "battleseed", "stepcounter",
                          "battlecounter", "threat", "initialseed",
                          "num_encounters"]:
            s += "%s: %x\n" % (attribute, getattr(self, attribute))
        s += "cost: %s\n" % self.cost
        return s.strip()

    @property
    def previous_instr(self):
        if self.scriptptr > 0:
            return Route.script[self.scriptptr-1]
        else:
            return None

    def set_seed(self, seed):
        self.seed = seed
        self.stepseed = seed
        self.battleseed = seed
        self.stepcounter = seed
        self.battlecounter = seed

    def copy(self):
        new = Route()
        for attribute in ["initialseed", "stepseed", "battleseed",
                          "stepcounter", "battlecounter", "threat",
                          "rng", "cost", "travelog", "scriptptr", "seed",
                          "resetting", "boundary_flag",
                          "last_forced_encounter", "last_reset",
                          "overworld_threatrate", "xp", "num_encounters"]:
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
            self.increment_battle(rng=False)
            self.overworld_threatrate = None

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
                if steps == 0:
                    self.cost += 1
                    self.boundary_flag = True
                if taken == 1:
                    self.cost += 1
                taken = 0

            if steps == 0:
                return

    def take_a_step(self, instr):
        if instr.fset.overworld:
            if instr.force_threat or self.overworld_threatrate is None:
                self.overworld_threatrate = instr.threatrate
            threatrate = self.overworld_threatrate
        else:
            self.overworld_threatrate = None
            threatrate = instr.threatrate

        self.cost += STEP_VALUE
        self.threat += threatrate
        self.increment_step()
        if self.predict_battle():
            self.increment_battle()
            self.num_encounters += 1
            formation = self.predict_formation(instr.fset)
            self.xp += formation.xp
            self.cost += formation.cost
            self.travelog += "ENCOUNTER: " + str(formation) + "\n"
            self.threat = 0
            if instr.fset.overworld:
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
            if self.previous_instr.fset == instr.fset:
                return False
        return bool(instr)

    def force_additional_encounter(self):
        if not self.boundary_flag:
            self.cost += 1
        distance = self.force_value
        if distance is not None:
            if distance < 10:
                return False
            else:
                factor = max(0, 20 - distance)
                self.cost += (2 ** factor)
        #self.forced_encounters += 1
        #self.cost += (5 ** self.forced_encounters)
        instr = self.previous_instr
        self.last_forced_encounter = self.num_encounters
        step = 0
        done = False
        self.travelog += "*** FORCE ADDITIONAL ENCOUNTER ***\n"
        while True:
            step += 1
            if self.take_a_step(instr):
                done = True

            if done and (step & 1) == 0:
                break

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
            elif instruction.travel:
                if best_encounter is None:
                    best_encounter = instruction.best_encounter
                elif instruction.best_encounter.cost < best_encounter.cost:
                    best_encounter = instruction.best_encounter

                tempcost += instruction.steps * STEP_VALUE
                for i in xrange(instruction.steps):
                    tempthreat += instruction.threatrate
                    #if tempthreat >= 0xFF00:
                    #if tempthreat >= 0x8000:
                    if tempthreat >= 0x2000:
                        tempcost += best_encounter.cost
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
        self.cost += 25
        self.resetting = True
        self.set_seed(self.seed+1)
        self.travelog += "*** SAVE AND RESET TO TITLE SCREEN ***\n"

    def reset_fifteen(self):
        self.resetting = False
        self.set_seed(self.seed+15)
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
        if self.resetting:
            child = self.copy()
            child.reset_one()
            children.append(child)
            child = self.copy()
            child.reset_fifteen()
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
            if (self.overworld_threatrate and instr.fset.overworld and
                    self.overworld_threatrate != instr.threatrate):
                # change threat rate
                #child = self.copy()
                #child.menu_reset_threatrate()
                #children.append(child)
                pass
            distance = self.reset_value
            if self.previous_instr.travel and (distance is None or distance >= 10):
                if ((self.overworld_threatrate and not instr.fset.overworld) or
                        (instr.fset.overworld and not self.overworld_threatrate)):
                    # reset seed
                    costval = 20
                    if distance is not None:
                        factor = max(0, 20 - distance)
                        costval += (2 ** factor)
                    child = self.copy()
                    child.reset_one()
                    child.cost += costval
                    children.append(child)
                    child = self.copy()
                    child.reset_fifteen()
                    child.cost += costval
                    children.append(child)

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

    def __repr__(self):
        return "event" if self.event else "travel" if self.travel else "restriction" if self.restriction else "None"

    def set_event(self, formation, rng=False):
        self.formation = formation
        self.event = True
        self.rng = rng

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
        return min(self.fset.formations, key=lambda f: f.cost)


def encounter_search(routes):
    fringe = PriorityQueue()
    for r in routes:
        fringe.put((r.heuristic, r))

    counter = 0
    while True:
        counter += 1
        p, node = fringe.get()
        if node.scriptptr == Route.scriptlength:
            return node

        for child in node.expand():
            fringe.put((child.heuristic, child))

        if not counter % 1000:
            print fringe.qsize()
            #print child.scriptlength - child.scriptptr
        if fringe.qsize() == 0:
            raise Exception("No valid solutions found.")


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
        if setid == "ev":
            steps = int(steps, 0x10)
            i.set_event(formation=formations[steps])
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

        Route.script.append(i)
    Route.travelscript = [i for i in Route.script if i.travel]
    Route.scriptlength = len(Route.script)


if __name__ == "__main__":
    filename = argv[1]
    routefile = argv[2]
    monsters = monsters_from_table()
    for m in monsters:
        m.read_stats(filename)
    formations = formations_from_rom(filename)
    fsets = fsets_from_rom(filename, formations)
    #seed = 244
    threat = 0x0
    rng = get_rng_string(filename)
    routes = [Route(seed, rng, threat) for seed in range(0x100)]
    #routes = [Route(244, rng, threat)]
    format_script(fsets, formations, routefile)
    solution = encounter_search(routes)
    print solution
    print solution.travelog
    '''
    routes = []
    format_script(fsets, formations, routefile)
    for seed in range(0x100):
        r = Route(seed, rng, threat)
        while r.scriptptr < Route.scriptlength:
            r.execute_script()
        routes.append(r)
    routes = sorted(routes, key=lambda r: r.cost)
    print routes[0]
    print routes[0].travelog
    '''
