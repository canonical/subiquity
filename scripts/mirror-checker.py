#!/usr/bin/env python3

import argparse
import concurrent.futures
import os
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

import dns.resolver
from prettytable import PrettyTable
from pycountry import countries


def run_cmd(cmd: list[str], output: TextIO = sys.stdout) -> int:
    """Run a cmd list. Return output."""
    # Print out command bash -x style
    print(f"+ {shlex.join(cmd)}", file=output)
    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
    ) as proc:
        try:
            for line in iter(proc.stdout.readline, ""):  # type: ignore
                print(line, end="", file=output, flush=True)
        except KeyboardInterrupt:
            print("Killed by user.", file=output, flush=True)
        finally:
            proc.stdout.close()  # type: ignore
            proc.wait()

        return proc.returncode


def check_mirror(
    mirror_url: str,
    release: str,
    output: TextIO = sys.stdout,
) -> int:
    """Check the health of a single mirror for a particular release.

    Uses debootstrap to create a schroot using the specified mirror_url.
    Returns a 0 on success and a 1 on failure.
    """
    # Default to 1 so if run_cmd fails then we still get a failure.
    ret = 1
    with tempfile.TemporaryDirectory() as tempdir:

        print(datetime.now(timezone.utc), file=output)
        print(f"Creating schroot in: {tempdir}", file=output)
        print(f"Targeting release: {release}", file=output)
        print(f"Using mirror: {mirror_url}", file=output)

        debootstrap_cmd = ["debootstrap", release, tempdir, mirror_url]
        ret = run_cmd(debootstrap_cmd, output=output)

    return ret


def check_country_mirror(
    country_code: str,
    release: str,
    output: TextIO = sys.stdout,
) -> int:
    """Check the health of a single country mirror for a particular release.

    Uses debootstrap to create a schroot using the specified mirror. Returns
    a 0 on success and a 1 on failure.
    """
    mirror: str = f"http://{country_code}.archive.ubuntu.com/ubuntu/"
    return check_mirror(mirror, release, output=output)


def check_primary_archive(
    release: str,
    output: TextIO = sys.stdout,
) -> int:
    mirror: str = "http://archive.ubuntu.com/ubuntu/"
    return check_mirror(mirror, release, output=output)


def get_cname(domain: str) -> str:
    """Get CNAME records for domain."""
    try:
        # There should only ever be one CNAME record
        [answer] = dns.resolver.Resolver().resolve(domain, "CNAME")
        return answer.target.to_text()
    except dns.resolver.NoAnswer:  # No record is OK
        return ""
    except ValueError as ve:  # Unpack error.
        print(f"Error: More than 1 CNAME record for {domain!r}")
        raise ve


def get_arecords(domain: str) -> set[str]:
    """Get A records (ip addrs) for domain."""
    try:
        answers = dns.resolver.Resolver().resolve(domain, "A")
        return {data.address for data in answers}
    except dns.resolver.NoAnswer:
        return set()


def get_dns_information(country_codes: list[str]) -> tuple[dict[str, Any], list[str]]:
    """Return a dns information (CNAMES and A records) for all country mirrors.

    Returns a 2-tuple containing the following information:
        - A dictionary keyed on the 2-letter country code whose value is
        another dictionary containing the domain, A records, and CNAME record,
        if any.
        - A list of 2-letter country codes which resulted in CNAME lookups
        that returned more than 1 result. This is not compliant with DNS
        specification and should be considered a mirror configuration error.
    """
    country_code_to_dns_data: dict[str, Any] = {}

    cname_errors: list[str] = []

    for cc in country_codes:
        # Don't put protocol (i.e. 'http://') in url. Only pass domain name.
        domain = f"{cc}.archive.ubuntu.com"

        cname: str = ""
        try:
            cname = get_cname(domain)
        except ValueError:
            cname_errors.append(cc)
            continue

        country_code_to_dns_data[cc] = {
            "domain": domain,
            "A": get_arecords(domain),
            "CNAME": cname,
        }

    return country_code_to_dns_data, cname_errors


def get_multi_country_mirrors(cc_to_dns: dict[str, Any]) -> dict[str, set[str]]:
    """Calculate which mirrors are an alias of another archive mirror.

    Returns a dictionary where the keys are the real archive mirrors and the
    values are the set of aliases for that mirror.
    """
    mirror_map = {cc: None for cc in cc_to_dns}
    for cc, data in cc_to_dns.items():

        if (cname := data["CNAME"]) != "":
            parts = cname.split(".")
            if parts[1:4] == ["archive", "ubuntu", "com"]:
                mirror_map[cc] = parts[0]

    mirror_to_aliases: dict[str, set[str]] = {}
    for alias, target in mirror_map.items():

        if target is None:
            if alias not in mirror_to_aliases:
                mirror_to_aliases[alias] = set()
            # else: nothing to do
            continue

        aliases = []
        curr_alias = alias
        curr_target = target
        while curr_target is not None:
            aliases.append(curr_alias)
            curr_alias = target
            curr_target = mirror_map[curr_alias]

        known_aliases = mirror_to_aliases.get(curr_alias, set())
        mirror_to_aliases[curr_alias] = known_aliases.union(set(aliases))

    # Remove mirrors with no aliases
    ret = {c: a for c, a in mirror_to_aliases.items() if len(a) > 0}

    return ret


def _print_dns_information(country_code_to_dns_data: dict[str, Any]) -> None:

    for cc, data in country_code_to_dns_data.items():
        print(f"{data["domain"]}:")
        print(f"\tCNAME: {data['CNAME']!r}")
        print("\tA records:")
        for r in data["A"]:
            print(f"\t\t{r!r}")


def filter_mirrors(
    country_code_to_dns_data: dict[str, Any],
    primary_archive: dict[str, Any],
) -> dict[str, list[str]]:
    """Filter mirrors by country mirrors, canonical mirrors, non mirrors.

    Returns a dictionary whose keys are the mirror types and the values are
    a list of country codes for that mirror type.

    Mirror Types:

    non_mirrors - For mirrors which don't exist, cc.archive.ubuntu.com will
    just fallback to the primary archive. So these mirrors are those with
    identical A records (IPs) to the primary archive.

    cname_mirrors - For actual country mirrors, these have CNAME records that
    point cc.archive.ubuntu.com domain lookups to another domain
    (e.g. ubuntu.mymirror.com).

    canonical_mirrors - There are a few special mirrors, usually "us" and "gb",
    that have no CNAME records and do not have identical A records with the
    primary archive. These appear to be Canonical hosted country mirrors.
    The union of A records for these mirrors should be the same as the A
    record results of archive.ubuntu.com.
    """

    cname_mirrors = []
    non_mirrors = []
    canonical_mirrors = []

    for cc, data in country_code_to_dns_data.items():
        if data["CNAME"] != "":
            cname_mirrors.append(cc)
        elif data["A"] == primary_archive["A"]:
            non_mirrors.append(cc)
        else:
            canonical_mirrors.append(cc)

    return {
        "non_mirrors": non_mirrors,
        "cname_mirrors": cname_mirrors,
        "canonical_mirrors": canonical_mirrors,
    }


def _print_mirror_stats(
    filtered_mirrors: dict[str, Any],
    country_codes: list[str],
    country_code_to_dns_data: dict[str, Any],
    mirror_aliases: dict[str, Any],
) -> None:

    cname_mirrors = filtered_mirrors["cname_mirrors"]
    canonical_mirrors = filtered_mirrors["canonical_mirrors"]
    non_mirrors = filtered_mirrors["non_mirrors"]
    print(f"Total country codes checked: {len(country_codes)}")
    print(f"Total mirrors with a CNAME record: {len(cname_mirrors)}")
    print(f"Total mirrors hosted by Canonical: {len(canonical_mirrors)}")
    print(f"Total country codes with no mirror: {len(non_mirrors)}")

    print("Found mirrors:")
    print("\tCanonical mirrors:")
    for mirror in canonical_mirrors:
        print(f"\t\t{mirror!r}")
    print("\tRegistered mirrors (have CNAME):")
    for mirror in cname_mirrors:
        print(f"\t\t{mirror!r} -> {country_code_to_dns_data[mirror]['CNAME']}")
    print("Alias information:")

    for mirror, aliases in mirror_aliases.items():
        if len(aliases) == 0:
            continue
        print(f"\tMirror {mirror!r} is aliased by:")
        for m in aliases:
            print(f"\t\t{m!r}")


def _multi_mirror_check(
    mirrors_to_check: set[tuple[str, str]],
    release: str,
    output_dir: Path,
    n_jobs: int,
    mirror_status: dict[str, tuple[str, str, str | Path]],
) -> None:

    def _run_check(cc: str, release: str) -> int:

        output_path: Path = output_dir / f"{cc}.txt"
        with output_path.open("w") as f:
            if cc == "primary":
                mirror = "http://archive.ubuntu.com/ubuntu/"
                print(f"checking {mirror} -> {output_path}")
                return check_primary_archive(release, output=f)
            else:
                mirror = f"http://{cc}.archive.ubuntu.com/ubuntu/"
                print(f"checking {mirror} -> {output_path}")
                return check_country_mirror(cc, release, output=f)

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_jobs) as executor:
        future_to_result = {
            executor.submit(_run_check, cc, release): (cc, d)
            for (cc, d) in mirrors_to_check
        }
        for future in concurrent.futures.as_completed(future_to_result):
            (cc, d) = future_to_result[future]
            exitcode = -1
            try:
                exitcode = future.result()
            except Exception as exc:
                print(f"{cc} generated an exception: {exc}")

            status_text = "ok" if exitcode == 0 else "not ok"

            print(f"{cc}: {status_text}")

            mirror_status[cc] = (
                status_text,
                d,
                output_dir / f"{cc}.txt",
            )


def check_all_mirrors(
    n_jobs: int,
    release: str,
    show_non_mirrors: bool,
    output_location: str,
) -> int:
    """Check the health of all country mirrors."""

    print(datetime.now(timezone.utc))
    print("Checking all mirrors...")
    country_codes: list[str] = [c.alpha_2.lower() for c in countries]

    print("Checking DNS information for mirrors...")
    country_code_to_dns_data, cname_errors = get_dns_information(country_codes)

    # Also collect IPs for the primary archive
    primary_archive = {
        "domain": "archive.ubuntu.com",
        "A": get_arecords("archive.ubuntu.com"),
        "CNAME": "",  # No CNAME for primary archive
    }

    # Print out all the mirror information found
    _print_dns_information(
        {
            **{"primary": primary_archive},
            **country_code_to_dns_data,
        }
    )

    filtered_mirrors = filter_mirrors(country_code_to_dns_data, primary_archive)

    mirror_aliases = get_multi_country_mirrors(country_code_to_dns_data)

    _print_mirror_stats(
        filtered_mirrors,
        country_codes,
        country_code_to_dns_data,
        mirror_aliases,
    )

    # Get ready to check only active mirrors
    mirror_status: dict[str, tuple[str, str, str | Path]] = {}

    header = ["Mirror", "Status", "Domain", "Log"]

    # Generate NA status result for non mirrors
    for cc in filtered_mirrors["non_mirrors"]:
        mirror_status[cc] = (
            "NA",
            "archive.ubuntu.com",
            "-",
        )

    # Generate stub for mirror aliases
    for mirror, aliases in mirror_aliases.items():
        for cc in aliases:
            mirror_status[cc] = (
                "-",  # To be updated
                f"{mirror}.archive.ubuntu.com",
                "-",  # To be updated
            )

    # Generate "not ok" status for mirrors with bad cname
    for cc in cname_errors:
        mirror_status[cc] = (
            "not ok",
            "more than 1 CNAME record",
            "-",
        )

    # Remaining mirrors are real mirrors
    mirrors_to_check = set()
    for cc in country_codes:
        if cc not in mirror_status:
            domain = country_code_to_dns_data[cc]["CNAME"]
            if domain == "":
                domain = f"{cc}.archive.ubuntu.com"
            mirrors_to_check.add((cc, domain))

    # Also check the primary archive
    mirrors_to_check.add(("primary", "archive.ubuntu.com"))

    # Setup output directories
    output_dir = Path(output_location)
    output_dir.mkdir(exist_ok=True)

    _multi_mirror_check(
        mirrors_to_check,
        release,
        output_dir,
        n_jobs,
        mirror_status,
    )

    # Fill in results for aliases
    for mirror, aliases in mirror_aliases.items():
        for cc in aliases:
            mirror_status[cc] = mirror_status[mirror]

    table = PrettyTable(header)
    table.add_row(["primary", *mirror_status.pop("primary")])
    for cc, status in sorted(mirror_status.items()):
        if cc in filtered_mirrors["non_mirrors"] and not show_non_mirrors:
            continue
        table.add_row([cc, *status])

    print(table)

    return 0


def check_handler(args: argparse.Namespace) -> int:
    """Handle the "check" subcommand and return exit code."""
    return check_country_mirror(args.country_code, args.release)


def check_all_handler(args: argparse.Namespace) -> int:
    """Handle the "check-all" subcommand and return exit code."""
    return check_all_mirrors(
        n_jobs=args.n,
        release=args.release,
        show_non_mirrors=args.all,
        output_location=args.output,
    )


def parse_args() -> tuple[argparse.Namespace, argparse.ArgumentParser]:

    parser = argparse.ArgumentParser(
        description="Use debootstrap to test mirror health. Requires root.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Set up subcommand parser.
    # set required=False so we can show help on empty command.
    subparsers = parser.add_subparsers(
        title="subcommands",
        required=False,
        dest="command",
    )

    # create parser for single mirror mode
    check = subparsers.add_parser(
        "check",
        help="check a single mirror",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    check.add_argument(
        "country_code",
        help="- two letter country code",
    )
    check.add_argument(
        "release",
        nargs="?",
        default="noble",
        help="- release",
    )
    check.set_defaults(func=check_handler)

    # create parser for check all mirrors mode
    check_all = subparsers.add_parser(
        "check-all",
        help="check all country mirrors",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    check_all.add_argument(
        "release",
        nargs="?",
        default="noble",
        help="- release",
    )
    check_all.add_argument(
        "--output",
        "-o",
        default="mirror_checker_output",
        help="- output location",
    )
    check_all.add_argument(
        "--number-jobs",
        "-n",
        type=int,
        default=1,
        help="- number of parallel jobs",
        dest="n",
    )
    check_all.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="- show country codes with no mirror",
    )
    check_all.set_defaults(func=check_all_handler)

    return parser.parse_args(), parser


def main() -> int:

    args, parser = parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if os.geteuid() != 0:
        print("mirror-checker requires sudo")
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
