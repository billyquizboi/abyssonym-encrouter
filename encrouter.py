from sys import argv
from monster import monsters_from_table
from formation import fsets_from_rom

if __name__ == "__main__":
    filename = argv[1]
    monsters = monsters_from_table()
    fsets = fsets_from_rom(filename)
    for fset in fsets:
        print fset
        print
