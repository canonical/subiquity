#!/usr/bin/python3

# Run the input file through ruamel yaml to obtain a more consistent result.

import argparse

from ruamel.yaml import YAML


parser = argparse.ArgumentParser()
parser.add_argument('infile', help='yaml file to normalize')
args = parser.parse_args()

yaml = YAML()
yaml.default_flow_style = False
yaml.pure = True
yaml.indent(mapping=2, sequence=2, offset=2)

with open(args.infile, 'r') as fp:
    data = yaml.load(fp)
with open(args.infile, 'w') as fp:
    yaml.dump(data, fp)
