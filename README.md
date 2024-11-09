# General

This codebase adds documentation to an existing tool used for step and encounter routing in FFVI. Much respect to the original author.

# How to run

*Note: The original encrouter appears to have run on python 2. This codebase contains modifications relative to the original which made it compatible with python 3.*

### Install git

Go to [git-scm.com/downloads](https://git-scm.com/downloads) to download git for your platform. Install as per the instructions or using the installer.

### Clone this git repository

If you are reading this, you should already be on the correct github repository. Get the clone link from github, open a terminal or git GUI program of your choice and use the `git clone` command to create a local copy of this repository.

### Install python 3

Go to [python3.org/downloads](https://www.python.org/downloads/) and install the latest source release for your platform.

### Running via the command line

The codebase contains 3 runnable python files. The one you probably want to run is `encounter.py` as it is the main program for this codebase. However, the other python files are also runnable. Details of each runnable file are below.

### `encounter.py`

The primary program in this codebase which runs the encounter routing logic. Relies on monster.py and formation.py.
Requires 2, 3, or 4 command line arguments in the following order:
- arg[1]: rom file name - required
- arg[2]: route file name - required
- arg[3]: report filename - optional argument with default value report.txt
- arg[4]: seed - optional argument - if you want to provide this you must also provide a report filename event if it matches the default of 'report.txt'

*Just a quick note about command line arguments: The first argument passed to the program when started is the program name/filename being run. That is arg[0] since the array starts at index 0. That means arg[1] is the first argument we define as below.*

Example usage:

```shell
# Assumes you are in a terminal or shell with same working directory as the location of the encounter.py file
# You must have a rom and a route file in the same directory ie: some_file.some_extension and route.txt or route.txt.catscratch

# Running with default report.txt output file and for ALL possible seed values
# It will run for a little while just fyi
python3 encouter.py "some_file.some_extension" "route.txt"

# Running with a specified report file name for ALL seed values - will run for a little while
python3 encouter.py "some_file.some_extension" "route.txt" "reportFileName.txt"

# Running with a specified report file name and seed value - much faster when only processing for a single seed value
# just for reference these would be the command line args at runtime during encounter.py execution
# ['/pathToThisGithubRepositoryInYourFileSystem/encrouter.py', 'some_file.some_extension', 'route.txt', 'report.txt', '244']
python3 encouter.py "some_file.some_extension" "route.txt" "reportFileName.txt" 244
```

### `monster.py`

The `monster.py` file is used by `encounter.py` to load monster data from a rom. When run directly, `monster.py` reads the file [tables/enemycodes.txt](tables/enemycodes.txt) and prints the line number in hexadecimal followed by the monster's name for example:

line 1 in enemycodes.txt
```text 
Guard_____,f0000,f3000,f3d00,f4300,f4600,f8400
```
would become
```text
0x0 Guard
```

Example usage:

```shell
# Assumes you are in a terminal or shell with same working directory as the location of the monster.py file

python3 monster.py
```

Example output:

```text
0x0 Guard
0x1 Soldier
0x2 Templar
etc...
```

### `formation.py`

The `formation.py` file is used by `encounter.py` to load formations data from a rom. When run directly, `formation.py` reads 576 formations from a rom and then prints each formation and its mould followed by all the formation sets.

Example formation output line for a formation with 1 monster with name = 'Monster Name', formation id = 0, and mould = 8:

`Monster Name x1 (0) 8`

Example usage:

```shell
# Assumes you are in a terminal or shell with same working directory as the location of the encounter.py file
# You must have a rom in the same directory ie: some_file.some_extension

python3 formation.py "some_file.some_extension"
```

Example output:
```text
Some Monster x1 (0) 0
Other Monster x2 (1) 8
New Monster x2 (2) 8
Some Monster x2, Other Monster x1 (3) 1
etc... lots more formations
A Monster x1 (23f) 6
PACK ID 0
Some Monster x1 (6)
Other Monster x1, New Monster x2 (7)
A Monster x1 (6)
Some Monster x1, Other monster x2 (7)

PACK ID 1
New Monster x2 (a)
A Monster x3 (b)
A Monster x2, New Monster x1 (c)
A Monster x3, New Monster x1 (9)

etc... lots more formation sets - note that the PACK ID # is in hexadecimal
```

**The formation id and PACK ID ( formation set id ) printed by formation.py can be used in the route.txt files to describe an encounter with a specific formation or a random encounter within a specific formation set**

# General concepts

A description of the core objects which are used in this program. Some of these are pretty obvious and some are more specific to this program. 

**Monster**: A specific enemy in the game which has particular stats and other characteristics. Called MonsterBlock in the codebase which relates to how it is stored in a rom.

**Formation**: A grouping of monster(s) which is possible to encounter in the game.

**Formation set**: A set of formations which is possible to encounter within a given area or map zone.

**Instruction**: A single instruction ( can be an instruction for the program state ie: 'wt' ), an action to take, or an event/encounter in the speedrun route roadmap. Some examples: An instruction which will generate details into the report for console resets to use at the returners hideout, an instruction to enter the veldt, an instruction to travel a specific number of steps at a given threat rate, or an instruction to set the weight used when calculating formation cost.

**Route**: After a list of instructions is produced, a Route object attempts to traverse / follow the instructions. It simulates the cost of forcing an encounter vs. not forcing an encounter ( depth of 1 ) when traveling and proceeds with the route object which has the lowest cost after each encounter or other event / instruction.

TODO: more route documentation

# Route files

*For an example see [route.txt](route.txt)*.

Each line in the route files which does not start with `#` is processed one by one in `encrouter.format_script` to create an **Instruction** object.
An **Instruction** represents a single event, encounter, or action to take on the route path. There are a number of different types of instructions.

Each processed line contains 3 values separated by one or more spaces in the below order.
- first column value - Used to identify the type of instruction. It will either be a string representing the type of the instruction ( ie: 'wt', 'vl', or others which are all documented below ) or a valid hexadecimal number which is the index to use to locate a specific formation set.
- second column value - The variable name in the code for this value is `threatrate` and sometimes it represents the threat rate as a hexadecimal number. However, it can also have string values like 'no' meaning don't search for a rage for gau or 'xp' for a restriction based on xp.
- third column value - The variable name in the code for this value is `steps` and sometimes it represents the number of steps to take ( ie: when column 1 is a hexadecimal number or on the veldt ) but it can also represent the index for a formation within the list of formations read by formation.py or the index of a formation set.

For example in the lines:
```text
# Narshe
wt  0   1.0
```

The first line is ignored because it starts with '#'. The second line is processed with the following meaning:

| column | value | type                     | description                                                                  |
|--------|-------|--------------------------|------------------------------------------------------------------------------|
| 1      | wt    | string                   | Sets the weight used when calculating formation cost                         |
| 2      | 0     | not applicable           | Not used. The value 0 here is a placeholder here used to maintain formatting |
| 3      | 1.0   | decimal number ( float ) | The actual weight value to set                                               |

So, in short, that line means set the weight used when calculating formation costs to 1.0.

## Route file instruction types

### `wt`

Short for **weight**.

example line: `wt  0   1.0`

An instruction to set the weight used when calculating formation cost to the value in the third column. The weight is used when [calculating the cost of a formation](#calculating-formation-cost).


| column | value | type                     | description                                                                  |
|--------|-------|--------------------------|------------------------------------------------------------------------------|
| 1      | wt    | string                   | Sets the weight used when calculating formation cost                         |
| 2      | 0     | not applicable           | Not used. The value 0 here is a placeholder here used to maintain formatting |
| 3      | 1.0   | decimal number ( float ) | The actual weight value to set                                               |

### `ev`

Short for **event**.

example line: `ev  0   2`

Third column value is a hexadecimal number which represents the index for a specific formation. Second column value is not used.
An **Instruction** object for an event will be created with formation matching index == column 3 in the formations list.
So which formation is that exactly? The formation at index `i` will be the formation stored in rom at byte 0xf6200 + (index * 15) and with auxiliary data at 0xf5900 + (index * 4).

| column | value | type               | description                                                                                                             |
|--------|-------|--------------------|-------------------------------------------------------------------------------------------------------------------------|
| 1      | ev    | string             | Causes an 'event' instruction to be created. Basically a specific enemy formation will be encountered                   |
| 2      | 0     | not applicable     | Not used. The value 0 here is a placeholder here used to maintain formatting                                            |
| 3      | 2     | hexadecimal number | The index of the formation which will be encountered. **This is the formation id from the formation.py printed output** |

### `rd`

Short for **random**.

example line: `rd  0   12c`

Describes a random encounter from a formation set. Which formation set is identified by the hexadecimal value of column 3.

| column | value | type               | description                                                                                                                                                                  |
|--------|-------|--------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1      | rd    | string             | Creates an instruction to encounter a random encounter from a specific formation set                                                                                         |
| 2      | 0     | not applicable     | Not used. The value 0 here is a placeholder here used to maintain formatting                                                                                                 |
| 3      | 12c   | hexadecimal number | The index of the formation set from which the random encounter formation will be picked. **This is the formation set id ( PACK ID # ) from the formation.py printed output** |


### `lete`

Short for **lete river** based on **lethe river** from the game. 

example line: `lete 0  0`

Creates an instruction which determines and adds to the report file the reset(s) required at the returners hideout before lethe river for river manipulation. Cost of resetting is considered in route cost calculation.


| column | value | type           | description                                                                              |
|--------|-------|----------------|------------------------------------------------------------------------------------------|
| 1      | lete  | string         | Creates an instruction which reports handling of river manipulation at returners hideout |
| 2      | 0     | not applicable | Not used. The value 0 here is a placeholder here used to maintain formatting             |
| 3      | 0     | not applicable | Not used. The value 0 here is a placeholder here used to maintain formatting             |


Example output in the travel log report file:
```text
*** GO TO RETURNER SAVE POINT ***
*** RESET TO GAME LOAD SCREEN ***
*** RELOAD ***
*** MANIPULATE LETE W/ RETURNER TO SEED 47 ***
```

### `vl`

Short for **veldt**.

example line: `vl  no  51`

An instruction to enter the veldt. The first time entering the veldt will have 'avoid gau' set to true and all subsequent entrances to the veldt within a route will have 'avoid gau' set to false. The veldt has a fixed threat rate of 192.

The second value is able to input as a hexadecimal value representing the rage to acquire but if it is not a valid hexadecimal value ie: 'no' it will be ignored and no rage will be sought for.

| column | value | type                       | description                                                                                      |
|--------|-------|----------------------------|--------------------------------------------------------------------------------------------------|
| 1      | vl    | string                     | Creates an instruction to enter the veldt                                                        |
| 2      | no    | hexadecimal number or 'no' | If this is a valid hexadecimal number then this is the rage which you want to get, else not used |
| 3      | 51    | hexadecimal number         | The number of steps to take                                                                      |

### `re`

Short for **restriction** ie: an xp restriction.

example line: `re  xp  151`

Creates an experience point restriction or other restriction type. Only xp restrictions are currently supported. Doesn't appear in report log so this seems to be primarily used by the internal logic of the program.

| column | value | type           | description                                                                                              |
|--------|-------|----------------|----------------------------------------------------------------------------------------------------------|
| 1      | re    | string         | Creates an instruction to require the acquisition of a specific number of experience points by this time |
| 2      | xp    | string         | The restriction type - always 'xp'                                                                       |
| 3      | 51    | decimal number | The experience points required                                                                           |

### `reset`

example line: `reset 0 0`

An instruction to reset the game one or more times.

| column | value | type           | description                              |
|--------|-------|----------------|------------------------------------------|
| 1      | reset | string         | Creates an instruction to reset the game |
| 2      | 0     | not applicable | Not used                                 |
| 3      | 0     | not applicable | Not used                                 |


### `fc`

Short for **Force**.

example line: `fc  C0  0`

Creates an instruction to force an encounter. Note that 'fc' is also a valid hexadecimal number which could cause problems if you are intending to enter the hexadecimal 'fc' instead of meaning to force an encounter.

| column | value | type           | description                                  |
|--------|-------|----------------|----------------------------------------------|
| 1      | fc    | string         | Creates an instruction to force an encounter |
| 2      | C0    | not applicable | Not used                                     |
| 3      | 0     | not applicable | Not used                                     |

Results in text like this in the report travel log:
```text
*** FORCE ADDITIONAL ENCOUNTER ***
ENCOUNTER: Repo Man x1, Vaporite x1 (1a) COST: 14.0
```

### `A hexadecimal number`

example lines:

`3c  70  17`

`2   C0! 1`

`0   60  32-4`

Creates an instruction to move a given number of steps.

| column | value | type                                                   | description                                                                                                                                                                                                                |
|--------|-------|--------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1      | 3c    | hexadecimal number                                     | Creates an instruction to move a given number of steps.                                                                                                                                                                    |
| 2      | 70    | hexadecimal number optionally suffixed with '!'        | The threat rate used along with step count to predict encounters. The optional '!' suffix is called force_threat in the codebase and results in the overworld threat rate being used to increment the threat after a step. |
| 3      | 17    | decimal number or two decimal numbers separated by '-' | The number of steps to take. If contains a '-' character separating two numbers, then the number of steps is first number - second number                                                                                  |

# Calculating the cost of a formation

This codebase calculates cost for a formation based on:

- a starting base cost of 10
- weight: an optional argument with default value of 1.0
- smoke bombs - however this is always false in the codebase - may be an unfinished or deprecated feature
- if gau should be avoided or not - in the logic here the first time in the route the veldt is entered 'avoid gau' will have value True and it is False in all following veldt entrances. 'avoiding gau' being true means the first time on the veldt.
- if front attack is prohibited
- if back attack is prohibited
- if pincer attack is prohibited
- if the encounter is inescapable
- if the encounter is difficult to escape from
- the number of enemies in the formation

and the above factors can be overridden with a custom cost by adding content to [tables/customcosts.txt](tables/customcosts.txt).

Example format for a custom cost is `formationIdHexadecimal customCost` ie:

```text
# make a custom cost of 50 for formation id hexadecimal '52'
52  50
```
*Note that lines in customcosts.txt prefixed with # are ignored ie:*
```text
#9   50
```

In pseudo-english, the logic for calculating cost of a formation is below. Note that this simplifies some things based on smokebombs always being false in the codebase.

```text
if there is a custom cost for this formation -> use the custom cost
if both front and back attack are prohibited -> return 100 * the weight
if front is prohibited, avoiding gau, and the fight is inescapable -> return 10

# subsequent calculations assume a starting cost of 1
set cost = 1
if weight >= 1 -> cost = cost * weight * number of enemies in the formation
else -> cost = cost * weight

if escaping is difficult -> add 4 * weight to the cost
if back attack is allowed -> add 2 to cost
if the number of enemies in the formation > 1 or pincer is allowed -> add 3 * the number of enemies to the cost

if the encounter is inescapable -> if avoiding gau add 30 to cost, else add 20

add 10 to the cost
return the calculated cost
```

# Reading the report files

### debug strings

example line: `--- f4 f4 f4 f4 0 0`

Contains information about the currently selected route object's internal state in this order left to right:
- stepseed
- stepcounter
- battleseed
- battlecounter
- threat
- cost

