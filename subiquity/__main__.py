import asyncio
import sys

if __name__ == '__main__':
    from subiquity.cmd.tui import main
    sys.exit(asyncio.run(main()))
