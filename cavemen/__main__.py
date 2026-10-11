"""Command-line entry point: python -m cavemen [options]."""
import argparse
import json
import sys
from .config import ConfigError, Config


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="cavemen",
        description="Ice-age tribe simulation with LLM-driven agents.")
    parser.add_argument("--config", default="config.yaml",
                        help="path to config.yaml")
    parser.add_argument("--headless", type=int, default=None,
                        help="run N ticks without GUI and exit (debug/test)")
    parser.add_argument("--no-llm", action="store_true",
                        help="disable the LLM endpoint entirely")
    args = parser.parse_args(argv)

    try:
        cfg = Config(args.config)
    except ConfigError as exc:   # user-friendly config error, no traceback
        print(f"Konfigurationsfehler: {exc}")
        return 1

    if args.headless is not None:
        from .simulation.game_loop import Simulation
        sim = Simulation.new_world(cfg, slot=0, name="headless",
                                   llm_enabled=not args.no_llm)
        for report in sim.run_headless(args.headless):
            print(json.dumps(report))   # plain-ASCII JSON lines per phase
        return 0

    try:
        from .gui import app   # lazy: headless mode needs no pygame at all
        app.run(cfg)
    except Exception as exc:   # e.g. missing display or pygame installation
        print(f"GUI konnte nicht gestartet werden: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
