#
# Makefile for subiquity
#

ui-view:
	PYTHONPATH=$(shell pwd):$(PYTHONPATH) bin/subiquity
