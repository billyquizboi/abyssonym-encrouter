from sys import argv
from monster import monsters_from_table
from formation import formations_from_rom, fsets_from_rom
from queue import PriorityQueue

JAPAN = False
STEP_VALUE = 0.5
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
    rng = list(f.read(0x100))
    return rng


def get_reset_bunch(node, ones=2, fourteens=2):
    if JAPAN:
        ones += 1
        fourteens += 1
    prev = node.copy()
    prev.cost += 20
    resetted = [prev]
    for i in range(ones):
        child = prev.copy()
        child.reset_one()
        resetted.append(child)
        prev = child

    resetted2 = []
    for child in resetted:
        for i in range(fourteens):
            child.reset_fourteen()
            child2 = child.copy()
            resetted2.append(child2)

    return resetted2


class Route():
    scriptlength = 0
    script = []
    fsets = {}
    formations = {}
    travelscript = []
    riversequence = {}
    leterng = {}
    returnerrng = {}
    veldtpacks = {}

    def __init__(self, seed=None, rng=None, threat=0):
        self.initialseed = seed
        self.set_seed(seed)
        self.threat = threat
        self.rng = rng
        self.cost = 0
        self.travelog = ""
        self.scriptptr = 0 # the index of the Instruction within Route.script which will be processed next
        self.boundary_flag = False
        self.overworld_threatrate = None
        #self.forced_encounters = 0
        self.last_forced_encounter = None
        self.last_reset = None
        self.num_encounters = 0
        self.xp = 0
        self.weight = 1.0
        self.smokebombs = False
        self.seen_formations = set([])
        self.gau_encounters = 0

    def __lt__(self, other):
        if isinstance(other, Route):
            return self.heuristic < other.heuristic
        else:
            return NotImplemented

    def __gt__(self, other):
        if isinstance(other, Route):
            return self.heuristic > other.heuristic
        else:
            return NotImplemented

    def __eq__(self, other):
        if isinstance(other, Route):
            return self.heuristic == other.heuristic
        else:
            return NotImplemented

    def __repr__(self):
        s = ""
        for attribute in ["initialseed", "stepseed", "battleseed",
                          "stepcounter", "battlecounter", "threat"]:
            s += "%s: %x\n" % (attribute, getattr(self, attribute))
        for attribute in ["cost", "num_encounters"]:
            s += "%s: %s\n" % (attribute, getattr(self, attribute))
        return s.strip()

    @property
    def debug_string(self):
        debug_string = "--- %x %x %x %x %x %s\n" % (
            self.stepseed, self.stepcounter, self.battleseed,
            self.battlecounter, self.threat, self.cost)
        return debug_string

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
                          "boundary_flag", "weight", "smokebombs",
                          "last_forced_encounter", "last_reset",
                          "overworld_threatrate", "xp", "num_encounters",
                          "gau_encounters"]:
            setattr(new, attribute, getattr(self, attribute))
        new.seen_formations = set(self.seen_formations)
        return new

    def get_best_river(self, battles=1):
        #self.reset_fourteen()
        self.overworld_threatrate = None
        try:
            seed = Route.leterng[self.seed]
        except KeyError:
            return False

        best = None
        cost, bestcost = 0, 0
        bestnum = 0
        for i in range(0x100):
            battlecounter = Route.riversequence[seed].count(True)
            if battlecounter == 2 + battles:
                temp = self.copy()
                if temp.predict_river(seed):
                    best = seed
                    bestcost = cost
                    bestnum = i
                    break
            #self.cost += STEP_VALUE * 2
            #cost += 0.1
            seed = Route.returnerrng[seed]
        if best is None:
            return False

        self.travelog += "*** MANIPULATE LETE W/ RETURNER TO SEED %s ***\n" % (best)
        self.predict_river(best)
        self.cost += bestcost
        self.scriptptr += 1
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
                cost = formation.cost(self.weight, self.smokebombs)
                self.cost += cost
                self.travelog += "RIVER: " + str(formation) + " COST: %s" % cost + "\n"
        return True
        return double_pterodon

    def predict_formation(self, fset):
        """
        Predicts the formation which will encountered in a battle
        :param fset:
        :return:
        """
        self.increment_battle(rng=True)
        value = self.rng[self.battlecounter]
        value = (value + self.battleseed) & 0xFF # values between 0 and 255 inclusive
        if len(fset.formations) == 4:
            value = value // 0x50
        else:
            value = value // 0xC0
        formation = fset.formations[value]
        if formation.formid < 0x200:
            self.seen_formations.add(formation.formid)
        return formation

    def predict_battle(self):
        """
        Predicts if a battle will be encountered based on the step counter, step seed, threat, and rng string
        :return:
        """
        self.increment_step(rng=True)
        value = self.rng[self.stepcounter]
        value = (value + self.stepseed) & 0xFF
        return value < (self.threat >> 8)

    def predict_veldt_formation(self):
        """
        Predicts a veldt battle monster formation which will be encountered
        :return:
        """
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
        """
        Value of rng is ALWAYS True at runtime
        :param rng: always True
        :return:
        """
        # I assume the battlecounter has a max size of 255 so this masking allows handles keeping battlecounter: 0 >= value <= 255
        self.battlecounter = (self.battlecounter+1) & 0xFF
        if self.battlecounter == 0 and rng:
            self.battleseed += 0x17 # += 23 I am guessing for some reason internal to the logic of the game
            self.battleseed = self.battleseed & 0xFF # values allowed are between 0 and 255

    def execute_script(self, debug=True):
        """
        Processes a single instruction ( for some types of instructions ) in the route
        often adding information to the travel log and/or updating internal state of the
        Route object based on the Instruction.
        :param debug:
        :return:
        """
        if (self.previous_instr and self.previous_instr.veldt
                and not self.previous_instr.avoidgau):
            # look for gau
            while self.gau_encounters <= 1:
                self.force_additional_encounter(show_avoided=False)

        if self.scriptptr == Route.scriptlength:
            raise Exception("Script pointer out of bounds.")
        if debug:
            self.travelog += self.debug_string
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
            formations = self.predict_encounters(instr, debug=debug)
            if instr.veldt and not instr.avoidgau:
                if instr.seek_rage:
                    for f in formations:
                        if f.formid in instr.desired_formations:
                            break
                    else:
                        for _ in range(10):
                            f = self.force_additional_encounter(show_avoided=False)
                            if f:
                                formations.append(f)
                                if f.formid in instr.desired_formations:
                                    break
                        else:
                            return False

                    cost = 0
                    if f == formations[0]:
                        cost += 1000
                    elif f == formations[-1] and len(formations) <= 2:
                        self.force_additional_encounter()
                    if hasattr(self, "veldt_up") and self.veldt_up:
                        cost += self.veldt_up
                    if cost > 0:
                        self.cost += cost
                        self.travelog += "*** VELDT PENALTY +%s ***\n" % cost

                return True
        elif instr.event:
            self.travelog += "EVENT: %s\n" % instr.formation
            if instr.formation.formid < 0x200:
                self.seen_formations.add(instr.formation.formid)
            self.increment_battle(rng=True)
            self.overworld_threatrate = None
        elif instr.random:
            formation = self.predict_formation(instr.fset)
            self.xp += formation.xp
            cost = formation.cost(self.weight, self.smokebombs)
            self.cost += cost
            self.travelog += "RANDOM EVENT: " + str(formation) + " COST: %s" % cost + "\n"
            self.overworld_threatrate = None
        elif instr.weight:
            self.weight = instr.weightval
            #if self.weight <= 0.09:
            #    self.smokebombs = True
        elif instr.lete:
            return False
        elif instr.reset:
            return False
        elif instr.force:
            prevtrav = [i for i in self.script[:self.scriptptr] if i.travel][-1]
            instr.force_threat = prevtrav.force_threat
            instr.fset = prevtrav.fset
            instr.threatrate = prevtrav.threatrate
            self.force_additional_encounter()
            return True

        return True

    def predict_encounters(self, instr, steps=None, debug=True):
        """
        Takes a given number of steps and returns the formations encountered.
        :param instr:
        :param steps:
        :param debug:
        :return:
        """
        # note: seed changes when RNG is called and counter is at 0xFF
        # battlecounter += 0x11
        # stepcounter += 0x17
        taken, total = 0, 0
        steps = instr.steps if steps is None else steps
        self.boundary_flag = False
        if steps and hasattr(instr, "fset"):
            self.travelog += "%s threat steps in encounter zone %x.\n" % (steps, instr.fset.setid)

        formations = []
        while True:
            if steps == 0:
                return formations

            steps -= 1
            taken += 1
            total += 1

            formation = self.take_a_step(instr, debug=debug)
            if formation:
                #self.travelog += "STEP %s: \n" % taken
                #self.travelog += "%s\n" % self
                #if steps <= 1:
                if steps <= 3:
                    self.cost += 0.1
                    self.boundary_flag = True
                #if taken <= 2:
                if taken <= 4:
                    self.cost += 0.1
                taken = 0
                formations.append(formation)

    def take_a_step(self, instr, debug=True):
        """
        Simulates taking a step and returns a formation if encountered else None
        :param instr:
        :param debug:
        :return:
        """
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
            if instr.veldt:
                '''
                self.travelog += "%x %x %x %x %x\n" % (
                    self.stepseed, self.stepcounter, self.battleseed,
                    self.battlecounter, self.threat)
                '''

            self.num_encounters += 1
            if instr.veldt:
                formation = self.predict_veldt_formation()
                if not instr.avoidgau:
                    self.gau_encounters += 1
            else:
                formation = self.predict_formation(instr.fset)
            self.xp += formation.xp
            if instr.veldt:
                cost = formation.cost(self.weight, self.smokebombs, avoidgau=instr.avoidgau)
            else:
                cost = formation.cost(self.weight, self.smokebombs)
            self.cost += cost
            self.travelog += "ENCOUNTER: " + str(formation) + " COST: %s\n" % cost
            if debug:
                debug_string = self.debug_string
                self.travelog += debug_string
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

    def force_additional_encounter(self, show_avoided=True):
        """
        Simulates forcing an additional encounter and returns the formation which will be encountered.
        Simulates and prints encounters which will be met if NOT forcing an encounter if show_avoided is true.
        :param show_avoided: compute and print the avoided encounters if true
        :return: a formation which will result from taking steps
        """
        if self.boundary_flag:
            self.cost += 0.9
        else:
            self.cost += 1
        self.boundary_flag = False
        self.travelog += "*** FORCE ADDITIONAL ENCOUNTER ***\n"
        if show_avoided:
            parallel = self.copy()
            parallel.travelog = ""
            avoidance = None
            while True:
                if parallel.scriptptr == Route.scriptlength:
                    break

                if not parallel.execute_script(debug=False):
                    break

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
            if not done:
                formation = self.take_a_step(instr)
            else:
                self.take_a_step(instr)

            if formation:
                done = True

            if done and (step & 1) == 0:
                break

        if show_avoided and avoidance:
            self.travelog += avoidance + "\n"

        return formation

    @property
    def heuristic(self):
        #return (self.num_encounters << 16) + self.cost + (self.threat >> 12)
        # Note that self.threat appears to always have value 0 at runtime so heuristic returns cost at the moment
        return self.cost + (self.threat >> 12)

        '''
        tempthreat = self.threat
        tempcost = self.cost
        tempcost += ((self.threat >> 8) / 32.0)
        best_encounter = None
        for i in range(self.scriptptr, Route.scriptlength):
            instruction = Route.script[i]
            if instruction.event:
                pass
            elif instruction.travel and not instruction.veldt:
                if best_encounter is None:
                    best_encounter = instruction.best_encounter
                elif instruction.best_encounter.cost(self.weight, self.smokebombs) < best_encounter.cost(self.weight, self.smokebombs):
                    best_encounter = instruction.best_encounter

                tempcost += instruction.steps * STEP_VALUE
                for i in range(instruction.steps):
                    tempthreat += instruction.threatrate
                    #if tempthreat >= 0xFF00:
                    #if tempthreat >= 0x8000:
                    if tempthreat >= 0x2000:
                        tempcost += best_encounter.cost(self.weight, self.smokebombs)
                        best_encounter = instruction.best_encounter
                        tempthreat = 0
        return tempcost
        '''

    @property
    def reset_value(self):
        if self.last_reset is None:
            return None
        diff = self.num_encounters - self.last_reset
        return diff

    def reset_one(self):
        if JAPAN:
            self.cost += 10
        else:
            self.cost += 25
        self.set_seed(self.seed+1)
        self.travelog += "*** RESET TO GAME LOAD SCREEN ***\n"

    def reset_fourteen(self):
        if JAPAN:
            self.cost += 15
        else:
            self.cost += 30
        self.set_seed(self.seed+14)
        self.last_reset = self.num_encounters
        self.travelog += "*** RELOAD ***\n"

    def menu_reset_threatrate(self):
        self.cost += 1
        instr = Route.script[self.scriptptr]
        assert instr.fset.overworld
        self.overworld_threatrate = instr.threatrate
        self.travelog += "*** OPEN MENU TO RESET THREAT RATE ***\n"

    def expand(self):
        """
        Drives the processing of a single Instruction located at Route.script[self.scriptptr].
        Each instruction is processed according to its type.
        Returns a list of Route objects - will either contain 'self', a copy of 'self', or some
        number of copies of self route with cost modified because of resetting.
        :return:
        """
        if self.scriptptr == 24:
            if " 420 " not in self.debug_string and False:
                return []
        children = []
        instr = Route.script[self.scriptptr]
        if instr.veldt:
            self.travelog += "*** ENTER THE VELDT ***\n"
            '''
            self.travelog += "%x %x %x %x %x\n" % (
                self.stepseed, self.stepcounter, self.battleseed,
                self.battlecounter, self.threat)
            '''

        #if self.check_is_boundary():
        if (self.previous_instr and self.previous_instr.travel
                and self.previous_instr.steps >= 2):
            # force encounter
            distance = self.force_value
            if distance is not None and distance < 2:
                pass
            elif self.scriptptr < (Route.scriptlength-1):
                child = self.copy()
                if child.force_additional_encounter():
                    if child.execute_script():
                        children.append(child)
                    #children.append(child)

        if instr.travel and hasattr(instr, 'fset'):
            if (self.overworld_threatrate and instr.fset.overworld and
                    self.overworld_threatrate > instr.threatrate and
                    not instr.force_threat):
                # I think this function relates to some times/places in the route where
                # on the overworld the threat rate is incorrect and the route instructs to open the menu
                # in order to reset/correct the threat rate ie: to force an encounter between phantom train and piranha fight before veldt
                # change threat rate
                child = self.copy()
                child.menu_reset_threatrate()
                children.append(child)

            distance = self.reset_value or 0
            if self.previous_instr.travel:
                if (self.previous_instr.threatrate < instr.threatrate and
                        self.previous_instr.steps >= 2):
                    for steps in [10, 8, 6, 4, 2]:
                        if steps > instr.steps:
                            continue

                        child = self.copy()
                        child.travelog += "*** TAKE %s EXTRA STEPS ***\n" % steps
                        formations = child.predict_encounters(self.previous_instr, steps=steps)
                        if not formations:
                            parallel1 = self.copy()
                            parallel2 = child.copy()
                            formations1 = parallel1.predict_encounters(instr, steps=steps, debug=False)
                            formations2 = parallel2.predict_encounters(instr, steps=steps, debug=False)
                            if not formations1:
                                break

                            if len(formations1) > len(formations2) and child.execute_script():
                                children.append(child)

                if ((self.overworld_threatrate and not instr.fset.overworld) or
                        (instr.fset.overworld and not self.overworld_threatrate)):
                    # reset seed
                    if distance is not None and distance >= 10 and False:
                        resetted = get_reset_bunch(self)
                        children.extend(resetted)

        if instr.lete:
            #DESIRED_FORMATIONS = set([0x14, 0x15, 0x16, 0x18])
            #caught = len(DESIRED_FORMATIONS & self.seen_formations)
            #if caught == 0:
            #    return []
            #if caught >= 2:
            #    self.veldt_up = 10 * (caught-1)
            #    self.cost -= self.veldt_up
            self.travelog += "*** GO TO RETURNER SAVE POINT ***\n"
            resetted = get_reset_bunch(self)
            for node in resetted:
                child = node.copy()
                #if child.get_best_river(battles=1) and child.execute_script():
                if child.get_best_river(battles=0) and child.execute_script():
                    children.append(child)
                # The commented code below in this for loop was previously uncommented but unreachable so this is
                # identical functionality but a little less confusing. Left commented in case it should be added back in at some point
                # with the continue statement indented one more level
                # continue
                # child = node
                # if child.get_best_river(battles=1) and child.execute_script():
                #     children.append(child)
        elif instr.reset:
            children = []
            resetted = get_reset_bunch(self, ones=13, fourteens=5)
            for node in resetted:
                child = node.copy()
                child.execute_script()
                children.append(child)
        elif instr.force and False:
            instr.force_threat = self.previous_instr.force_threat
            instr.fset = self.previous_instr.fset
            instr.threatrate = self.previous_instr.threatrate
            self.force_additional_encounter()
            children.append(self)
        elif self.execute_script():
            children.append(self)

        return children


class Instruction():
    def __init__(self):
        self.event, self.travel = False, False
        self.restriction = False
        self.lete = False
        self.weight = False
        self.random = False
        self.veldt = False
        self.reset = False
        self.force = False

    def __repr__(self):
        return "event" if self.event else "travel" if self.travel else "restriction" if self.restriction else "lete" if self.lete else "None"

    def set_lete(self):
        self.lete = True

    def set_reset(self):
        self.reset = True

    def set_force(self):
        self.force = True

    def set_veldt(self, threatrate, steps, desired_rage):
        self.veldt = True
        self.travel = True
        self.threatrate = threatrate
        self.steps = steps
        self.force_threat = True
        self.avoidgau = False
        if desired_rage is not None:
            self.seek_rage = True
            formations = [f.formid for f in Route.formations.values()
                          if desired_rage in f.present_enemy_ids]
            self.desired_formations = formations
        else:
            self.seek_rage = False

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


def encounter_search(routes, number=1, anynode=True, maxsize=25000):
    """
    For fixed seed value, routes will have size 1. For all seeds will have size 255.
    TODO: add more documentation
    :param routes: the route(s) read in from route.txt and similar route files. One Route object per seed value it looks like.
    :param number: the number of solutions to make
    :param anynode: always false at runtime
    :param maxsize: the max allowed priority queue size
    :return:
    """
    fringe = PriorityQueue()
    for r in routes:
        fringe.put((r.heuristic, r))

    counter = 0
    progress = 0
    highest = 0
    solutions = []
    while len(solutions) < number:
        counter += 1
        # TODO: build a debug log so I can inspect the optimization process more
        print("{solutions length: " + str(solutions) + ", number: " + str(number) + ", counter: " + str(counter) + ", fringe: " + str(fringe.qsize()) + ",\nqueue: " + str(fringe.queue) + "\n")
        print("COUNTER: " + str(counter))
        p, node = fringe.get()
        highest = max(highest, node.scriptptr)
        if node.scriptptr == Route.scriptlength:
            if anynode or len([s for s in solutions if s.initialseed == node.initialseed]) < 2:
                solutions.append(node)

            if fringe.qsize() == 0:
                break
            else:
                continue
        childCount = 0
        for child in node.expand():
            childCount += 1
            print("EXPANDED CHILD: " + str(childCount) + " " + str(child) + "\n")
            fringe.put((child.heuristic, child))

        print("EXPANDED CHILD COUNT: " + str(childCount) + "\n")

        if not counter % 1000:
            print("count mod 1000 is " + str(counter % 1000) + "\n")
            size = fringe.qsize()
            nextsize = size
            while nextsize > maxsize:
                progress += 1 # TODO: is this right? we are not guaranteed to have always processed the same amount of script items for any given node as times through the encounter_search while loop
                print("{progress: %s, highest: %s, Route.scriptlength: %s}\n" % (progress, highest, Route.scriptlength))
                newfringe = PriorityQueue()
                seen_seeds = set([])
                seen_sigs = set([])
                toggler = [False] * 0x100 # list of 256 False items ie: [False, False, False, ...] size == 256
                seencount = 0
                fringesize = fringe.qsize()
                while fringe.qsize() > 0:
                    p, node = fringe.get() # we know we are working in order of least cost
                    seencount += 1
                    signature = (node.initialseed, node.scriptptr)
                    if (node.scriptptr >= progress or
                            node.initialseed not in seen_seeds or
                            (node.scriptptr >= progress * 0.5 and
                             signature not in seen_sigs)): # in order of least cost so this picks the route with less cost for that signature
                        newfringe.put((p, node))
                        seen_sigs.add(signature)
                        seen_seeds.add(node.initialseed)
                    elif (toggler[node.initialseed] is False # allows saving up to 2 of the same seed
                            or (node.scriptptr == highest
                                and seencount < fringesize / 2)): # either this is the furthest progress in the script OR in the first half of the priority queue ie: top 50% of routes by cost
                        newfringe.put((p, node))
                        seen_sigs.add(signature)
                        seen_seeds.add(node.initialseed)
                        toggler[node.initialseed] = True
                    else:
                        toggler[node.initialseed] = False # means the next one of that seed in the queue would be allowed?
                        print("DELETING NODE: " + str(node) + "\n")
                        del(node)
                del(fringe)
                fringe = newfringe
                nextsize = fringe.qsize()
            if nextsize != size:
                print("{highest: " + str(highest) + ", size: " + str(size) + ", nextsize: " + str(nextsize) + "}")
            else:
                print("{highest: " + str(highest) + ", nextsize: " + str(nextsize) + "}")
            #print(child.scriptlength - child.scriptptr)
        if fringe.qsize() == 0:
            raise Exception("No valid solutions found.")

    seeds = set([])
    while fringe.qsize() > 0:
        p, node = fringe.get()
        seeds.add(str(node.initialseed))

    print("ALL SEEDS: %s" % " ".join(sorted(seeds)))
    print("%s NODES EXPANDED" % counter)
    return solutions


def format_script(fsets, formations, filename):
    """
    Reads the route txt and for each uncommented line ( not starting with # )
    it creates an instruction object. It builds the Route data which is required
    for later processing of the instructions and reporting of the travel log.
    :param fsets: list of FormationSet objects
    :param formations: list of formation objects
    :param filename: the route file ie: route.txt
    :return:
    """
    Route.script = []
    Route.fsets = dict((f.setid, f) for f in fsets)
    Route.formations = dict((f.formid, f) for f in formations)
    veldted = False
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
        elif setid == "rd":
            steps = int(steps, 0x10)
            i.set_random(fset=fsets[steps])
        elif setid == "lete":
            i.set_lete()
        elif setid == "vl":
            try:
                desired_rage = int(threatrate, 0x10)
            except ValueError:
                desired_rage = None
            threatrate = 0xC0
            steps = int(steps)
            i.set_veldt(threatrate=threatrate, steps=steps,
                        desired_rage=desired_rage)
            if not veldted:
                i.avoidgau = True
                veldted = True
        elif setid == "wt":
            i.set_weight(float(steps))
        elif setid == "re":
            value = int(steps)
            i.set_restriction(rtype=threatrate, value=value)
        elif setid == "reset":
            i.set_reset()
        elif setid == "fc":
            i.set_force()
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

        #print(i)
        Route.script.append(i)
    Route.travelscript = [i for i in Route.script if i.travel]
    Route.scriptlength = len(Route.script)

    sequence = open("tables/leteriver.txt").readlines()
    sequence = [s.strip() for s in sequence]
    sequence = [True if s == "fight" else False for s in sequence]
    assert len(sequence) == 0x100
    Route.riversequence = {}
    for i in range(0x100):
        subseq = [True, True] + sequence[i:i+7]
        Route.riversequence[i] = subseq

    Route.leterng = table_from_file("tables/leterng.txt", hexify=True)
    assert 2 in Route.leterng
    Route.returnerrng = table_from_file("tables/returnerrng.txt", hexify=True)
    Route.veldtpacks = {}
    for i in range(64):
        a = i * 8
        b = (i+1) * 8
        Route.veldtpacks[i] = list(range(a, b))
        for j, val in enumerate(Route.veldtpacks[i]):
            formation = Route.formations[val]
            if any(e for e in formation.present_enemies if e.id > 0xFF):
                Route.veldtpacks[i][j] = None
        assert len(Route.veldtpacks[i]) == 8


if __name__ == "__main__":
    filename = argv[1]
    routefile = argv[2]
    if len(argv) >= 4:
        outfile = argv[3]
    else:
        outfile = "report.txt"
    if len(argv) >= 5:
        seed = int(argv[4])
    else:
        seed = None
    monsters = monsters_from_table()
    for m in monsters:
        m.read_stats(filename)
    formations = formations_from_rom(filename)
    fsets = fsets_from_rom(filename, formations)
    for fset in fsets:
        fsetdict[fset.setid] = fset
    rng = get_rng_string(filename)

    threats = [0, 0x540, 0x1080, 0x2160, 0x5555]
    #threats = [0x5555]
    #threats = [0xC0 * i for i in range(80, 160)]
    threats = [0]
    if seed is None:
        #routes = [Route(seed, rng, t) for t in threats for seed in [96]]
        routes = [Route(seed, rng, t) for t in threats for seed in range(0x100)]
        #routes = [Route(seed, rng, t) for t in threats for seed in [108, 142, 143, 171, 198, 199, 201, 202, 232, 238, 239]]
        #routes = [Route(seed, rng, t) for t in threats for seed in [108, 143, 171, 198, 199, 201, 202, 232, 238, 239]]
        #routes = [Route(seed, rng, t) for t in threats for seed in [238]]
        #routes = [Route(seed, rng, t) for t in threats for seed in [244]]
        #routes = [Route(seed, rng, t) for t in threats for seed in [0xb9, 0xb8, 0xf4]]
    else:
        routes = [Route(seed, rng, t) for t in threats]
    format_script(fsets, formations, routefile)
    maxsize = 10000
    solutions = encounter_search(routes, number=20, anynode=False, maxsize=maxsize)
    '''
    import pdb; pdb.set_trace()
    print(len(solutions))
    solutions = [s for s in solutions if "Were-Rat x3" in s.travelog]
    print(len(solutions))
    solutions = [s for s in solutions if "Repo Man x1, Vaporite x1" in s.travelog]
    print(len(solutions))
    solutions = [s for s in solutions if "Vaporite x2" not in s.travelog]
    print(len(solutions))
    solutions = [s for s in solutions if "Were-Rat x2" not in s.travelog]
    print(len(solutions))
    solutions = [s for s in solutions if "Areneid x2, Sand Ray x1" in s.travelog]
    print(len(solutions))
    '''
    '''
    seeds = sorted(set([s.initialseed for s in solutions]))
    #assert len(seeds) <= 20
    #threats = [0xC0 * i for i in range(80, 160)]
    threats = [0]
    routes = [Route(seed, rng, t) for t in threats for seed in seeds]
    del(solutions)
    solutions = encounter_search(routes, number=20, anynode=False, maxsize=maxsize)
    '''

    f = open(outfile, "w+")
    for solution in solutions:
        f.write("INITIAL SEED: %s\n" % solution.initialseed)
        f.write(solution.travelog + "\n")
        f.write(str(solution) + "\n\n")
        f.write("-" * 60 + "\n")
    f.close()

# interesting... because of the way FF6's RNG works, it's possible to "eat" an encounter by taking extra steps in a low-rate zone, shifting the RNG pointer past a dangerous value
