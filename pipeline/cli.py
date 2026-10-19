import argparse


def cli(prog, args, fn, argv=None):
    a = argparse.ArgumentParser(prog=prog)
    for names, kw in args:
        a.add_argument(*names, **kw)
    print(fn(a.parse_args(argv)))
