from datetime import datetime
from sys import argv
from monster import monsters_from_table
from formation import formations_from_rom, fsets_from_rom
from queue import PriorityQueue
import logging
from inspect import currentframe, getframeinfo

JAPAN = False
STEP_VALUE = 0.5
fsetdict = {}

logging.basicConfig(filename="./logs/main.log", level=logging.DEBUG, format='%(asctime)s %(name)s %(levelname)s:%(message)s')
logger = logging.getLogger(__name__)

# turn this to true to allow large amounts of queue logging of some target queue items - will make this get set from command line arg
ALLOW_QUEUE_LOGGING = False

# turn on to produce logging output - will make this set from command line arg
ALLOW_DEBUG_LOGGING = False

def log_info(method_name, route, instr, line_num=None, queue_size=None, selected_node=None, queue=None, message=None):
    """
    Standardize log output format for easier tracing of events and smaller log files
    :param method_name:
    :param route:
    :param instr:
    :param line_num:
    :param queue_size:
    :param selected_node:
    :param queue:
    :param message:
    :return:
    """
    logger.info("%s| route: { id: %s, init_seed: %s, cost: %s, scriptptr: %s, step_seed: %s, step_counter: %s, rng: %s, threat: %s, overworld_rate: %s } | instr: { id: %s, type: %s, threat_rate: %s } | queue_size: %s | selected: %s |%s" % (
                                    ("%s:%s" % (method_name, line_num)).ljust(30),
                                    str(route.id).ljust(5) if route else None,
                                    str(route.initialseed).ljust(3) if route else None,
                                    str(round(route.cost, 2)).ljust(6) if route else None,
                                    str(route.scriptptr).ljust(4) if route else None,
                                    str(route.stepseed).ljust(4) if route else None,
                                    str(route.stepcounter).ljust(4) if route else None,
                                    str(route.rng[route.stepcounter]).ljust(4) if (route and route.stepcounter and route.rng) else None,
                                    str(route.threat).ljust(4) if route else None,
                                    str(route.overworld_threatrate).ljust(4) if route else None,
                                    str(instr.id).ljust(5) if instr else str("None").ljust(5),
                                    str(instr.type).ljust(11) if instr else str("None").ljust(11),
                                    str(instr.threatrate).ljust(4) if (instr and hasattr(instr, 'threatrate')) else str("None").ljust(4),
                                    str(queue_size).ljust(6) if queue_size else str("None").ljust(6),
                                    str(selected_node.short_string).ljust(90) if selected_node else str("None").ljust(90),
                                    # get_queue_other_items(selected_node, queue),
                                    message))

def get_queue_other_items(selected_node, queue):
    """
    Allows logging queue items which have a higher script ptr but also a higher cost within some given boundary.
    Could log a lot of data so be prepared for multi GB log files.
    :param selected_node:
    :param queue:
    :return:
    """
    if selected_node and queue:
        if not ALLOW_QUEUE_LOGGING:
            return None
        sub_queue = []
        for item in queue:
            if item.scriptptr > selected_node.scriptptr and ( item.cost == selected_node.cost or item.cost < selected_node.cost + 30 ):
                sub_queue.append(item)
        return str(sub_queue)
    else:
        return None


class MethodContextLogger:
    """
    Used to simplify logging standard info which includes enclosing method, line number, route, and instruction context
    as well as an optional free-form message
    """
    def __init__(self, method_name=None, route=None, instr=None):
        self.method_name = method_name
        self.route = route
        self.instr = instr

    def log(self, message=None):
        if ALLOW_DEBUG_LOGGING:
            line_num = currentframe().f_back.f_lineno
            log_info(method_name=self.method_name, route=self.route, instr=self.instr, line_num=line_num, queue_size=None,
                     selected_node=None, queue=None, message=message)

    def lqueue(self, selected_node=None, queue_size=None, queue=None, message=None):
        if ALLOW_DEBUG_LOGGING:
            line_num = currentframe().f_back.f_lineno
            log_info(method_name=self.method_name, route=self.route, instr=self.instr, line_num=line_num, queue_size=queue_size,
                     selected_node=selected_node, queue=queue, message=message)


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
    method_logger = MethodContextLogger("get_reset_bunch")
    method_logger.log("Start get_reset_bunch")
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

    method_logger.log("Returning resetted2: %s" % str(resetted2))
    method_logger.log("End get_reset_bunch")
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
    next_id = 0

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
        self.id = Route.next_id
        Route.next_id += 1

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
    def log_string(self):
        return str({
            'class': self.__class__.__name__,
            'id': self.id,
            'initialseed': self.initialseed,
            'seed': self.seed,
            'veldtseed': self.veldtseed,
            'stepseed': self.stepseed,
            'battleseed': self.battleseed,
            'stepcounter': self.stepcounter,
            'battlecounter': self.battlecounter,
            'threat': self.threat,
            'cost': self.cost,
            'travelog': self.travelog,
            'scriptptr': self.scriptptr,
            'boundary_flag': self.boundary_flag,
            'overworld_threatrate': self.overworld_threatrate,
            'last_forced_encounter': self.last_forced_encounter,
            'last_reset': self.last_reset,
            'num_encounters': self.num_encounters,
            'xp': self.xp,
            'weight': self.weight,
            'smokebombs': self.smokebombs,
            'seen_formations': self.seen_formations,
            'gau_encounters': self.gau_encounters,
        })

    @property
    def short_string(self):
        return "(id: %s, cost: %s, script_ptr: %s, num_encounters: %s)" % (self.id, round(self.cost, 2), self.scriptptr, self.num_encounters)

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
        method_logger = MethodContextLogger("get_best_river", self, Route.script[self.scriptptr])
        method_logger.log("Start get_best_river")
        #self.reset_fourteen()
        self.overworld_threatrate = None
        try:
            seed = Route.leterng[self.seed]
            method_logger.log("seed %s" % seed)
        except KeyError:
            method_logger.log("seed not found!")
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
        method_logger.log("%s -> %s" % (best, cost))
        method_logger.log("End get_best_river")
        return True

    def predict_river(self, seed):
        method_logger = MethodContextLogger("predict_river", self, Route.script[self.scriptptr])
        method_logger.log("Start predict_river")
        sequence = Route.riversequence[seed]
        method_logger.log("Sequence %s" % sequence)
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
                method_logger.log("{decision: %s, formation: %s, xp: %s, cost: %s, fset: %s}" % (decision, formation, formation.xp, cost, fset))
        method_logger.log("End predict_river")
        return True
        #return double_pterodon # unreachable code I commented out

    def predict_formation(self, fset):
        """
        Predicts the formation which will encountered in a battle
        :param fset:
        :return:
        """
        method_logger = MethodContextLogger("predict_formation", self, Route.script[self.scriptptr])
        method_logger.log("Start predict_formation")
        self.increment_battle(rng=True)
        value = self.rng[self.battlecounter]
        value = (value + self.battleseed) & 0xFF # values between 0 and 255 inclusive
        method_logger.log("{ value: %s, battlecounter: %s, battleseed: %s self.rng[self.battlecounter]: %s }" % (value, self.battlecounter, self.battleseed, self.rng[self.battlecounter]))
        if len(fset.formations) == 4:
            value = value // 0x50
        else:
            value = value // 0xC0
        formation = fset.formations[value]
        method_logger.log("Predicted formation %s" % formation)
        if formation.formid < 0x200:
            method_logger.log("Adding formation.formid %s to seen formations" % formation.formid)
            self.seen_formations.add(formation.formid)
        method_logger.log("Returning formation %s" % formation)
        method_logger.log("End predict_formation")
        return formation

    def predict_battle(self):
        """
        Predicts if a battle will be encountered based on the step counter, step seed, threat, and rng string
        :return:
        """
        method_logger = MethodContextLogger("predict_battle", self, Route.script[self.scriptptr])
        method_logger.log("Predicting battle from step counter")
        self.increment_step(rng=True)
        value = self.rng[self.stepcounter]
        value = (value + self.stepseed) & 0xFF
        is_battle_predicted = value < (self.threat >> 8)
        if is_battle_predicted:
            method_logger.log("Battle is predicted")
        else:
            method_logger.log("Battle is NOT predicted")
        return is_battle_predicted

    def predict_veldt_formation(self):
        """
        Predicts a veldt battle monster formation which will be encountered
        :return:
        """
        method_logger = MethodContextLogger("predict_veldt_formation", self, Route.script[self.scriptptr])
        method_logger.log("Start predict_veldt_formation with veldtseed=%d" % self.veldtseed)
        self.veldtseed += 1
        while True:
            self.veldtseed = self.veldtseed & 0x3F
            pack = Route.veldtpacks[self.veldtseed]
            method_logger.log("Veldt pack is %s" % pack)
            if set(pack) & self.seen_formations:
                break

            self.veldtseed += 1

        method_logger.log("updated veldtseed is %s" % self.veldtseed)
        self.increment_battle(rng=True)
        value = self.rng[self.battlecounter]
        value = (value + self.battleseed)
        method_logger.log("self.rng[self.battlecounter] + self.battleseed is %s" % value)
        while True:
            value = value & 0x07
            method_logger.log("Value for pack selection is %s" % value)
            formid = pack[value]
            method_logger.log("Formation id is %s" % formid)
            if formid in self.seen_formations:
                method_logger.log("Breaking as formation id was seen. formation %s" % formid)
                break
            value += 1

        formation = Route.formations[formid]
        method_logger.log("Returning formation %s" % formation)
        method_logger.log("End predict_veldt_formation")
        return formation

    def increment_step(self, rng=True):
        method_logger = MethodContextLogger("increment_step", self, Route.script[self.scriptptr])
        method_logger.log("Start increment_step with { rng: %s, stepcounter: %s, stepseed: %s }" % (rng, self.stepcounter, self.stepseed))
        self.stepcounter = (self.stepcounter+1) & 0xFF
        method_logger.log("Updated stepcounter to %s" % self.stepcounter)
        if self.stepcounter == 0 and rng:
            self.stepseed += 0x11
            self.stepseed = self.stepseed & 0xFF
            method_logger.log("Updated stepseed to %s" % self.stepseed)
        method_logger.log("End increment_step")

    def increment_battle(self, rng=True):
        """
        Value of rng is ALWAYS True at runtime
        :param rng: always True
        :return:
        """
        method_logger = MethodContextLogger("increment_battle", self, Route.script[self.scriptptr])
        method_logger.log("Start increment_battle with {rng: %s, battlecounter: %s, battleseed: %s}" % (rng, self.battlecounter, self.battleseed))
        # I assume the battlecounter has a max size of 255 so this masking allows handles keeping battlecounter: 0 >= value <= 255
        self.battlecounter = (self.battlecounter+1) & 0xFF
        method_logger.log("Updated battlecounter to %s" % self.battlecounter)
        if self.battlecounter == 0 and rng:
            self.battleseed += 0x17 # += 23 I am guessing for some reason internal to the logic of the game
            self.battleseed = self.battleseed & 0xFF # values allowed are between 0 and 255
            method_logger.log("Updated battleseed to %s" % self.battleseed)
        method_logger.log("End increment_battle")

    def execute_script(self, debug=True):
        """
        Processes a single instruction ( for some types of instructions ) in the route
        often adding information to the travel log and/or updating internal state of the
        Route object based on the Instruction.
        :param debug:
        :return:
        """
        method_logger = MethodContextLogger("execute_script", self, Route.script[self.scriptptr])
        method_logger.log("Start execute_script with { debug: %s }" % debug)
        if (self.previous_instr and self.previous_instr.veldt
                and not self.previous_instr.avoidgau):
            # look for gau
            method_logger.log("Looking for gau. Current num_encounters = %s" % self.num_encounters)
            starting_num_encounters = self.num_encounters
            while self.gau_encounters <= 1:
                method_logger.log("Gau not found! num_encounters = %s" % self.num_encounters)
                self.force_additional_encounter(show_avoided=False)
            method_logger.log("Gau found after %s extra encounters" % (self.num_encounters - starting_num_encounters))

        if self.scriptptr == Route.scriptlength:
            raise Exception("Script pointer out of bounds.")
        if debug:
            self.travelog += self.debug_string
        instr = Route.script[self.scriptptr]
        method_logger.log("Located instruction { scriptptr: %s, instruction: %s }" % (self.scriptptr, instr))
        self.scriptptr += 1

        if instr.restriction:
            method_logger.log("Restriction instruction found { rtype: %s, value: %s }" % (instr.rtype if hasattr(instr, 'rtype') else None, instr.value if hasattr(instr, 'value') else None))
            if instr.value is None:
                setattr(self, instr.rtype, 0)
            else:
                value = getattr(self, instr.rtype)
                if value < instr.value:
                    method_logger.log("Restriction not met: { value: %s, required_value: %s }" % (value, instr.value))
                    return False
                else:
                    method_logger.log("Restriction satisfied: { value: %s, required_value: %s }" % (value, instr.value))
                    setattr(self, instr.rtype, 0)
        elif instr.travel:
            method_logger.log("Travel instruction found { veldt: %s, avoidgau: %s, steps: %s, threatrate: %s, force_threat: %s, fset: %s }" % (
                instr.veldt if hasattr(instr, 'veldt') else None,
                instr.avoidgau if hasattr(instr, 'avoidgau') else None,
                instr.steps if hasattr(instr, 'steps') else None,
                instr.threatrate if hasattr(instr, 'threatrate') else None,
                instr.force_threat if hasattr(instr, 'force_threat') else None,
                instr.fset.log_string if hasattr(instr, 'fset') and instr.fset is not None else None
            ))
            formations = self.predict_encounters(instr, debug=debug)
            if instr.veldt and not instr.avoidgau:
                if instr.seek_rage:
                    method_logger.log("Seeking a rage %s" % instr.seek_rage)
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

                method_logger.log("Completed on veldt and not avoiding gau %s")
                return True
        elif instr.event:
            method_logger.log("Event instruction found { formation: %s, instruction: %s }" % (instr.formation, instr.log_string))
            self.travelog += "EVENT: %s\n" % instr.formation
            if instr.formation.formid < 0x200:
                method_logger.log("Add formation to seend_formations: formation: %s" % instr.formation)
                self.seen_formations.add(instr.formation.formid)
            self.increment_battle(rng=True)
            self.overworld_threatrate = None
            method_logger.log("Zero overworld threat")
        elif instr.random:
            method_logger.log("Random encounter instruction found { fset: %s, instruction: %s }" % (instr.fset, instr.log_string))
            formation = self.predict_formation(instr.fset)
            self.xp += formation.xp
            cost = formation.cost(self.weight, self.smokebombs)
            self.cost += cost
            self.travelog += "RANDOM EVENT: " + str(formation) + " COST: %s" % cost + "\n"
            self.overworld_threatrate = None
            method_logger.log("Random encounter details: { cost: %s, xp: %s, formation: %s }" % (cost, formation.xp, formation))
        elif instr.weight:
            method_logger.log("Weight instruction found %s" % instr.weightval)
            self.weight = instr.weightval
            #if self.weight <= 0.09:
            #    self.smokebombs = True
        elif instr.lete:
            method_logger.log("Lete instruction found - noop here %s" % instr.log_string)
            return False
        elif instr.reset:
            method_logger.log("Reset instruction found - noop here %s" % instr.log_string)
            return False
        elif instr.force:
            method_logger.log("Force instruction found %s" % instr.log_string)
            prevtrav = [i for i in self.script[:self.scriptptr] if i.travel][-1]
            instr.force_threat = prevtrav.force_threat
            instr.fset = prevtrav.fset
            instr.threatrate = prevtrav.threatrate
            method_logger.log("Forcing additional encounter: { force_threat: %s, threatrate: %s, fset: %s }" % (instr.force_threat, instr.threatrate, instr.fset))
            self.force_additional_encounter()
            method_logger.log("Completed forcing additional encounter")
            return True
        method_logger.log("End execute_script - default exit")
        return True

    def predict_encounters(self, instr, steps=None, debug=True):
        """
        Takes a given number of steps and returns the formations encountered.
        :param instr:
        :param steps:
        :param debug:
        :return:
        """
        method_logger = MethodContextLogger("predict_encounters", self, instr)
        method_logger.log("Start predict_encounters with { steps: %s, debug: %s, instr.steps: %s }" % (steps, debug, instr.steps if instr is not None and instr.steps is not None else None))
        # note: seed changes when RNG is called and counter is at 0xFF
        # battlecounter += 0x11
        # stepcounter += 0x17
        taken, total = 0, 0
        steps = instr.steps if steps is None else steps
        self.boundary_flag = False
        if steps and hasattr(instr, "fset"):
            method_logger.log("Instruction has fset %s" % instr.fset.log_string)
            self.travelog += "%s threat steps in encounter zone %x.\n" % (steps, instr.fset.setid)

        formations = []
        while True:
            if steps == 0:
                method_logger.log("Return formations: %s" % str(formations))
                method_logger.log("End predict_encounters")
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
                method_logger.log("Encountered formation { steps: %s, taken: %s, total: %s, formations.size: %s, formation: %s }" % (steps, taken, total, len(formations), formation))

    def take_a_step(self, instr, debug=True):
        """
        Simulates taking a step and returns a formation if encountered else None
        :param instr:
        :param debug:
        :return:
        """
        method_logger = MethodContextLogger("take_a_step", self, instr)
        method_logger.log("Start take_a_step")

        if instr.force_threat:
            method_logger.log("force threat")
            self.overworld_threatrate = instr.threatrate
            threatrate = self.overworld_threatrate
        elif instr.fset.overworld:
            method_logger.log("fset.overworld=True")
            if self.overworld_threatrate is None:
                method_logger.log("overworld_threatrate is None")
                self.overworld_threatrate = instr.threatrate
            threatrate = self.overworld_threatrate
            method_logger.log("resulting threatrate=%s" % threatrate)
        else:
            self.overworld_threatrate = None
            threatrate = instr.threatrate
            method_logger.log("not force threat or fset.overworld so threatrate=%s" % threatrate)

        self.cost += STEP_VALUE
        self.threat += threatrate
        method_logger.log("increment cost by STEP_VALUE=%s and threat by threatrate=%s" % (STEP_VALUE, threatrate))
        if self.predict_battle():
            method_logger.log("Battle is predicted")
            # if instr.veldt: # commented out as it is no-op
            #     '''
            #     self.travelog += "%x %x %x %x %x\n" % (
            #         self.stepseed, self.stepcounter, self.battleseed,
            #         self.battlecounter, self.threat)
            #     '''
            #     logger.info("take_a_step: Veldt battle predicted for %s" % (route_instruction_log_string(self, instr)))
            self.num_encounters += 1
            method_logger.log("Increment num_encounters to %d" % self.num_encounters)
            if instr.veldt:
                formation = self.predict_veldt_formation()
                if not instr.avoidgau:
                    self.gau_encounters += 1
                method_logger.log("Veldt battle predicted. avoidgau=%s, gau_encounters=%s, formation=%s" % (instr.avoidgau, self.gau_encounters, formation))
            else:
                formation = self.predict_formation(instr.fset)
                method_logger.log("Not a veldt battle. formation=%s" % formation)
            self.xp += formation.xp
            method_logger.log("Gained %s xp for total_xp=%s from formation=%s" % (formation.xp, self.xp, formation))
            if instr.veldt:
                cost = formation.cost(self.weight, self.smokebombs, avoidgau=instr.avoidgau)
            else:
                cost = formation.cost(self.weight, self.smokebombs)
            self.cost += cost
            method_logger.log("formation.cost=%s, route_current_cost=%s" % (cost, self.cost))
            self.travelog += "ENCOUNTER: " + str(formation) + " COST: %s\n" % cost
            if debug:
                debug_string = self.debug_string
                self.travelog += debug_string
            self.threat = 0
            method_logger.log("Zero the threat")
            if not instr.veldt and instr.fset.overworld:
                self.overworld_threatrate = instr.threatrate
                method_logger.log("Set overworld_threatrate=%s" % self.overworld_threatrate)

            method_logger.log("Returning formation=%s" % formation)
            method_logger.log("End take_a_step")
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
        method_logger = MethodContextLogger("force_additional_encounter", self, Route.script[self.scriptptr])
        method_logger.log("Start force_additional_encounter. show_avoided=%s" % show_avoided)
        if self.boundary_flag:
            method_logger.log("Boundary flag")
            self.cost += 0.9
        else:
            method_logger.log("No boundary flag")
            self.cost += 1
        self.boundary_flag = False
        self.travelog += "*** FORCE ADDITIONAL ENCOUNTER ***\n"
        if show_avoided:
            parallel = self.copy()
            parallel.travelog = ""
            avoidance = None
            method_logger.log("Made parallel copy with id %d" % parallel.id)
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
        method_logger.log("Previous instruction %s" % instr.log_string if instr else None)
        while True:
            step += 1
            method_logger.log("Step %d" % step)
            if not done:
                formation = self.take_a_step(instr)
                method_logger.log("Formation %s" % formation)
            else:
                method_logger.log("Done and taking a step")
                self.take_a_step(instr) # this takes a step after formation has happened ( maybe this is completing a step after the battle or something? )

            if formation:
                done = True

            if done and (step & 1) == 0: # step & 1 -> I assume this means steps is odd?
                method_logger.log("Break out as done and step %d & 1 == 0" % step)
                break

        if show_avoided and avoidance:
            method_logger.log("Avoidance: %s" % avoidance)
            self.travelog += avoidance + "\n"

        method_logger.log("Returning formation: %s" % formation)
        method_logger.log("End force_additional_encounter")
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
        method_logger = MethodContextLogger("reset_value", self)
        method_logger.log("Start reset_value { num_encounters: %s, last_reset: %s }" % (self.num_encounters, self.last_reset))
        if self.last_reset is None:
            return None
        diff = self.num_encounters - self.last_reset
        method_logger.log("Returning difference: %s" % diff)
        method_logger.log("End reset_value")
        return diff

    def reset_one(self):
        method_logger = MethodContextLogger("reset_one", self, Route.script[self.scriptptr])
        method_logger.log("Start reset_one { cost: %s, seed: %s }" % (self.cost, self.seed))
        if JAPAN:
            self.cost += 10
        else:
            self.cost += 25
        self.set_seed(self.seed+1)
        method_logger.log("End reset_one { cost: %s, seed: %s }" % (self.cost, self.seed))
        self.travelog += "*** RESET TO GAME LOAD SCREEN ***\n"

    def reset_fourteen(self):
        method_logger.log("Start reset_fourteen { cost: %s, seed: %s, last_reset: %s }" % (self.cost, self.seed, self.last_reset))
        if JAPAN:
            self.cost += 15
        else:
            self.cost += 30
        self.set_seed(self.seed+14)
        self.last_reset = self.num_encounters
        method_logger.log("End reset_fourteen { cost: %s, seed: %s, last_reset: %s }" % (self.cost, self.seed, self.last_reset))
        self.travelog += "*** RELOAD ***\n"

    def menu_reset_threatrate(self):
        method_logger = MethodContextLogger("menu_reset_threatrate", self, Route.script[self.scriptptr])
        self.cost += 1
        instr = Route.script[self.scriptptr]
        method_logger.log("Start menu_reset_threatrate { cost: %s, overworld_threatrate: %s, instr.threatrate: %s }" % (self.cost, self.overworld_threatrate, instr.threatrate))
        assert instr.fset.overworld
        self.overworld_threatrate = instr.threatrate
        self.travelog += "*** OPEN MENU TO RESET THREAT RATE ***\n"
        method_logger.log("End menu_reset_threatrate { cost: %s, overworld_threatrate: %s, instr.threatrate: %s }" % (self.cost, self.overworld_threatrate, instr.threatrate))

    def expand(self):
        """
        Drives the processing of a single Instruction located at Route.script[self.scriptptr].
        Each instruction is processed according to its type.
        Returns a list of Route objects - will either contain 'self', a copy of 'self', or some
        number of copies of self route with cost modified because of resetting.
        In usage this always returns 1 or 2 nodes
        :return:
        """
        method_logger = MethodContextLogger("expand", self, Route.script[self.scriptptr])
        method_logger.log("Start expand")
        if self.scriptptr == 24:
            method_logger.log("Script pointer is 24")
            if " 420 " not in self.debug_string and False:
                method_logger.log("420 is not in the debug string. Not sure of the significance of this but returning empty expanded nodes list")
                return []
        children = []
        instr = Route.script[self.scriptptr]
        if instr.veldt:
            method_logger.log("Entering veldt")
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
            method_logger.log("Instruction has previous travel instruction with steps > 2. distance=%s, previous_instruction=%s" % (self.force_value, self.previous_instr.log_string))
            if distance is not None and distance < 2:
                pass
            elif self.scriptptr < (Route.scriptlength-1):
                child = self.copy()
                method_logger.log("Made child copy %s" % child.short_string)
                if child.force_additional_encounter():
                    if child.execute_script():
                        method_logger.log("execute_script was true for child copy %s" % child.short_string)
                        children.append(child)
                    #children.append(child)

        if instr.travel and hasattr(instr, 'fset'):
            method_logger.log("Travel instruction hasAttr fset %s" % instr.fset.log_string)
            if (self.overworld_threatrate and instr.fset.overworld and
                    self.overworld_threatrate > instr.threatrate and
                    not instr.force_threat):
                method_logger.log("Instruction resetting overworld threat")
                # I think this function relates to some times/places in the route where
                # on the overworld the threat rate is incorrect and the route instructs to open the menu
                # in order to reset/correct the threat rate ie: to force an encounter between phantom train and piranha fight before veldt
                # change threat rate
                child = self.copy()
                method_logger.log("Child copy made while resetting overworld threat %s" % child.log_string)
                child.menu_reset_threatrate()
                children.append(child)

            distance = self.reset_value or 0
            method_logger.log("Distance: %s" %distance)
            if self.previous_instr.travel:
                method_logger.log("Previous instruction was travel")
                if (self.previous_instr.threatrate < instr.threatrate and
                        self.previous_instr.steps >= 2):
                    method_logger.log("Previous instruction was travel")
                    for steps in [10, 8, 6, 4, 2]:
                        if steps > instr.steps:
                            continue

                        child = self.copy()
                        child.travelog += "*** TAKE %s EXTRA STEPS ***\n" % steps
                        formations = child.predict_encounters(self.previous_instr, steps=steps)
                        method_logger.log("Predicted formations %s" % formations)
                        if not formations:
                            parallel1 = self.copy()
                            parallel2 = child.copy()
                            formations1 = parallel1.predict_encounters(instr, steps=steps, debug=False)
                            formations2 = parallel2.predict_encounters(instr, steps=steps, debug=False)
                            if not formations1:
                                break

                            if len(formations1) > len(formations2) and child.execute_script():
                                method_logger.log("Appending child: %s" % child.log_string)
                                children.append(child)

                if ((self.overworld_threatrate and not instr.fset.overworld) or
                        (instr.fset.overworld and not self.overworld_threatrate)):
                    method_logger.log("Entering condition where fset overworld and overworld_threatrate don't matchup which will never execute. Not sure of the primary intention here.")
                    # reset seed
                    # I commented this out because 'and False' in the if condition means it will never execute
                    # if distance is not None and distance >= 10 and False:
                    #     resetted = get_reset_bunch(self)
                    #     children.extend(resetted)

        if instr.lete:
            method_logger.log("Lete instruction found %s" % instr.log_string)
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
                    method_logger.log("Adding best river child %s" % child)
                    children.append(child)
                # The commented code below in this for loop was previously uncommented but unreachable so this is
                # identical functionality but a little less confusing. Left commented in case it should be added back in at some point
                # with the continue statement indented one more level
                # continue
                # child = node
                # if child.get_best_river(battles=1) and child.execute_script():
                #     children.append(child)
        elif instr.reset:
            method_logger.log("Reset instruction found %s" % instr.log_string)
            children = []
            resetted = get_reset_bunch(self, ones=13, fourteens=5)
            method_logger.log("Processing resetted %s" % resetted)
            for node in resetted:
                child = node.copy()
                child.execute_script()
                children.append(child)
        elif instr.force and False:
            instr.force_threat = self.previous_instr.force_threat
            instr.fset = self.previous_instr.fset
            instr.threatrate = self.previous_instr.threatrate
            method_logger.log("Force instruction found { force_threat: %s, threatrate: %s, fset: %s, instruction: %s}" % (
                instr.force_threat,
                instr.threatrate,
                instr.fset,
                instr.log_string))
            self.force_additional_encounter()
            method_logger.log("Finished force additional encounter and appending self %s" % self.log_string)
            children.append(self)
        elif self.execute_script():
            method_logger.log("Executed script and appending %s" % self.log_string)
            children.append(self)

        method_logger.log("Returning expanded children %s" % str(list(map(lambda x: x.short_string, children))) if children else None)
        method_logger.log("End expand")
        return children


class Instruction():
    next_id = 0

    def __init__(self):
        self.event, self.travel = False, False
        self.restriction = False
        self.lete = False
        self.weight = False
        self.random = False
        self.veldt = False
        self.reset = False
        self.force = False
        self.id = Instruction.next_id
        Instruction.next_id += 1

        # a bunch of stuff that is used later but I want it always loggable
        # self.threatrate = None
        # self.steps = None
        # self.force_threat = None
        # self.avoidgau = None
        # self.steps = None
        # self.force_threat = None
        # self.event = None
        # self.rng = None
        # self.restriction = None
        # self.rtype = None
        # self.value = None
        # self.lete = None
        # self.weight = None
        # self.weightVal = None
        # self.random = None
        # self.fset = {}
        # self.veldt = None
        # self.avoidgau = None
        # self.seek_rage = None
        # self.desired_formations = []
        # self.reset = None
        # self.force = None
        # self.formation = None

    def __repr__(self):
        return "event" if self.event else "travel" if self.travel else "restriction" if self.restriction else "lete" if self.lete else "None"

    @property
    def type(self):
        if (self.travel):
            return "travel"
        elif (self.event):
            return "event"
        elif (self.restriction):
            return "restriction"
        elif (self.lete):
            return "lete"
        elif (self.weight):
            return "weight"
        elif (self.random):
            return "random"
        elif (self.veldt):
            return "veldt"
        elif (self.reset):
            return "reset"
        elif (self.force):
            return "force"
        else:
            "unknown"

    @property
    def log_string(self):
        return str(
            {
                'class': self.__class__.__name__,
                'id': self.id,
                'instr_type': self.type,
                'travel' : self.travel,
                'threatrate' : self.threatrate if hasattr(self, 'threatrate') else None,
                'steps' : self.steps if hasattr(self, 'steps') else None,
                'force_threat' : self.force_threat if hasattr(self, 'force_threat') else None,
                'event' : self.event if hasattr(self, 'event') else None,
                'rng' : self.rng if hasattr(self, 'rng') else None,
                'restriction' : self.restriction if hasattr(self, 'restriction') else None,
                'restrictiontype' : self.rtype if hasattr(self, 'rtype') else None,
                'value' : self.value if hasattr(self, 'value') else None,
                'lete' : self.lete if hasattr(self, 'lete') else None,
                'weight' : self.weight if hasattr(self, 'weight') else None,
                'weightVal' : self.weightval if hasattr(self, 'weightval') else None,
                'random' : self.random if hasattr(self, 'random') else None,
                'fset' : self.fset.log_string if hasattr(self, 'fset') else None,
                'veldt' : self.veldt if hasattr(self, 'veldt') else None,
                'avoidgau' : self.avoidgau if hasattr(self, 'avoidgau') else None,
                'seek_rage' : self.seek_rage if hasattr(self, 'seek_rage') else None,
                'desired_formations' : self.desired_formations if hasattr(self, 'desired_formations') else None,
                'reset' : self.reset if hasattr(self, 'reset') else None,
                'force' : self.force if hasattr(self, 'force') else None,
                'best_encounter' : self.best_encounter if hasattr(self, 'best_encounter') and hasattr(self, 'fset') else None,
                'formation' : self.formation if hasattr(self, 'formation') else None,
            }
        )

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
    method_logger = MethodContextLogger("encounter_search")
    method_logger.log("Start encounter_search")
    method_logger.log("Searching %s routes to make %s solutions anyNode=%s, maxsize=%s, Route.scriptlength=%s" % (len(routes), number, anynode, maxsize, Route.scriptlength))
    for r in routes:
        method_logger.log("Add %s to priority queue " % r.short_string)
        fringe.put((r.heuristic, r))

    method_logger.log("Initial priority queue size is %d" % fringe.qsize())
    counter = 0
    progress = 0
    highest = 0
    solutions = []
    while len(solutions) < number:
        counter += 1
        p, node = fringe.get()
        highest = max(highest, node.scriptptr)
        method_logger.route = node
        method_logger.log("{ counter: %s, max_script_ptr: %s, total_script_length: %s, selected: %s }" % (counter, highest, Route.scriptlength, node.short_string))
        method_logger.lqueue(node, fringe.qsize(), fringe.queue)
        if node.scriptptr == Route.scriptlength:
            if anynode or len([s for s in solutions if s.initialseed == node.initialseed]) < 2:
                method_logger.log("Appending solution %s" % node.short_string)
                solutions.append(node)

            if fringe.qsize() == 0:
                method_logger.log("Breaking out as queue is empty")
                break
            else:
                method_logger.log("Continuing on as queue has size %d" % fringe.qsize())
                continue

        childCount = 0
        for child in node.expand():
            childCount += 1
            method_logger.log("Adding expanded child %d to queue %s" % (childCount, child.log_string))
            fringe.put((child.heuristic, child))

        method_logger.log("Expanded %d nodes" % childCount)

        if not (counter % 1000):
            method_logger.log("Counter value %d mod 1000 == 0 for queue size %d" % (counter, fringe.qsize()))
            size = fringe.qsize()
            nextsize = size
            while nextsize > maxsize:
                progress += 1 # TODO: is this right? we are not guaranteed to have always processed the same amount of script items for any given node as times through the encounter_search while loop
                print("%s/%s/%s" % (progress, highest, Route.scriptlength))
                method_logger.log("nextsize %d > maxsize %d for progress=%d, highest=%d, scriptlength=%d" % (nextsize, maxsize, progress, highest, Route.scriptlength))
                newfringe = PriorityQueue()
                seen_seeds = set([])
                seen_sigs = set([])
                toggler = [False] * 0x100 # list of 256 False items ie: [False, False, False, ...] size == 256
                seencount = 0
                fringesize = fringe.qsize()
                method_logger.log("{ seen_count: %d, seend_seeds: %s, seen_signatures: %s }" % (seencount, str(seen_seeds), str(seen_sigs)))
                while fringe.qsize() > 0:
                    p, node = fringe.get() # we know we are working in order of least cost
                    seencount += 1
                    signature = (node.initialseed, node.scriptptr)
                    method_logger.route = node
                    method_logger.log("Processing if node should remain in queue")
                    if (node.scriptptr >= progress or
                            node.initialseed not in seen_seeds or
                            (node.scriptptr >= progress * 0.5 and
                             signature not in seen_sigs)): # in order of least cost so this picks the route with less cost for that signature
                        newfringe.put((p, node))
                        seen_sigs.add(signature)
                        seen_seeds.add(node.initialseed)
                        method_logger.log("Selected %s with signature=%s for new queue" % (node.short_string, signature))
                    elif (toggler[node.initialseed] is False # allows saving up to 2 of the same seed
                            or (node.scriptptr == highest
                                and seencount < fringesize / 2)): # either this is the furthest progress in the script OR in the first half of the priority queue ie: top 50% of routes by cost
                        newfringe.put((p, node))
                        seen_sigs.add(signature)
                        seen_seeds.add(node.initialseed)
                        toggler[node.initialseed] = True
                        method_logger.log(
                            "Selected %s because %s with signature=%s for new queue" % (
                                node.short_string,
                                "toggler " if highest != node.scriptptr else "highest",
                                signature))
                    else:
                        toggler[node.initialseed] = False # means the next one of that seed in the queue would be allowed?
                        method_logger.log("Deleting node! signature=%s, %s" % (signature, node.short_string))
                        del(node)
                del(fringe)
                fringe = newfringe
                nextsize = fringe.qsize()
            if nextsize != size:
                print(highest, size, nextsize)
                method_logger.log("Highest: %s. Reduced the queue size from %d to %d" % (highest, size, nextsize))
            else:
                print(highest, nextsize)
                method_logger.log("highest %s. nextsize still equal to size %d" % (highest, size))
            print(child.scriptlength - child.scriptptr)
        if fringe.qsize() == 0:
            method_logger.log("ERROR NO VALID SOLUTIONS FOUND!")
            raise Exception("No valid solutions found.")

    seeds = set([])
    select_order = 0
    while fringe.qsize() > 0:
        select_order += 1
        p, node = fringe.get()
        seeds.add(str(node.initialseed))
        method_logger.log("{ selected: %s, order: %d, initial_seed: %d, full: %s }" % (node.short_string, select_order, node.initialseed, node.log_string))

    method_logger.log("ALL SEEDS: %s" % " ".join(sorted(seeds)))
    print("ALL SEEDS: %s" % " ".join(sorted(seeds)))
    method_logger.log("%s NODES EXPANDED" % counter)
    print("%s NODES EXPANDED" % counter)
    return solutions


def map_routes_to_log_strings(iter):
    """
    Helper method for mapping iterable of Route objects to r.log_string
    for output to the log
    :param iter:
    :return:
    """
    result = []
    if iter is not None:
        for r in iter:
            if isinstance(r, Route):
                result.append(r.log_string)
            elif isinstance(r, tuple):
                result.append(r[1].log_string)
    return result


def route_instruction_log_string(route, instruction):
    """
    Helper method to get a map of the unique route id and instruction id + type
    :param route:
    :param instruction:
    :return:
    """
    result = {}
    if route is not None:
        result['route_id'] = route.id
    else:
        result['route_id'] = None
    if instruction is not None:
        result['instruction_id'] = instruction.id
        result['instruction_type'] = instruction.type
    else:
        result['instruction_id'] = None
        result['instruction_type'] = None
    return str(result)


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
    date = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    method_logger = MethodContextLogger("__main__")
    method_logger.log("STARTING MAIN!")
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
    if len(argv) >= 6:
        print("INFO: ALLOW_DEBUG_LOGGING is currently a disabled feature. Argument argv[5] '%s' will be ignored. This is due to the size of resulting debug log files as currently implemented being estimated to exceed 10 GB." % argv[5])
        # ALLOW_DEBUG_LOGGING = 'true' == (argv[5].lower() if argv[5] else 'false')
        # print("ALLOW_LOGGING = %s" % ALLOW_DEBUG_LOGGING)
        # if not ALLOW_DEBUG_LOGGING:
        #     print("Did you mean to provide a falsey argument '%s' for ALLOW_DEBUG_LOGGING? It is false by default..." % argv[5])
        # else:
        #     print("WARNING: Setting ALLOW_DEBUG_LOGGING to true will make I estimate a 10-20 GB size log file at ./logs/main.log. If you need to kill the program just type ctrl + c in a bash window or whatever steps kill a program on your device ie: task manager/command prompt if needed.")
    if len(argv) >= 7:
        print("INFO: ALLOW_QUEUE_LOGGING is currently a disabled feature. Argument argv[6] '%s' will be ignored. This is due to the size of resulting debug log files as currently implemented being estimated to exceed 10 GB." %
              argv[6])
        # ALLOW_QUEUE_LOGGING = 'true' == (argv[5].lower() if argv[6] else 'false')
        # print("ALLOW_QUEUE_LOGGING = %s" % ALLOW_QUEUE_LOGGING)
        # if not ALLOW_QUEUE_LOGGING:
        #     print("Did you mean to provide a falsey argument for ALLOW_QUEUE_LOGGING? It is false by default...")
        # elif ALLOW_QUEUE_LOGGING and not ALLOW_DEBUG_LOGGING:
        #     print("Setting ALLOW_QUEUE_LOGGING to true without ALLOW_DEBUG_LOGGING being true is noop")
        # else:
        #     print("WARNING: Setting ALLOW_DEBUG_LOGGING and ALLOW_QUEUE_LOGGING to true will make multi-GB log file at ./logs/main.log. If you need to kill the program just type ctrl + c in a bash window or whatever steps kill a program on your device ie: task manager/command prompt if needed.")
    monsters = monsters_from_table()
    for m in monsters:
        m.read_stats(filename)
    method_logger.log("Loaded %s monsters from table" % len(monsters))
    formations = formations_from_rom(filename)
    method_logger.log("Loaded: %s formations from rom" % len(formations))
    fsets = fsets_from_rom(filename, formations)
    method_logger.log("Loaded: %s formation sets from rom" % len(fsets))
    for fset in fsets:
        fsetdict[fset.setid] = fset
    rng = get_rng_string(filename)
    method_logger.log("Loaded: rng string of length %s. %s" % (len(rng), str(rng)))
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
    method_logger.log("Completed program")

# interesting... because of the way FF6's RNG works, it's possible to "eat" an encounter by taking extra steps in a low-rate zone, shifting the RNG pointer past a dangerous value
