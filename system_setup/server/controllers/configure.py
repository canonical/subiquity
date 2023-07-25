# Copyright 2020 Canonical, Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import asyncio
import logging
import os
import re
import shutil
from typing import List, Optional, Tuple

from subiquity.common.errorreport import ErrorReportKind
from subiquity.common.resources import get_users_and_groups
from subiquity.common.types import ApplicationState
from subiquity.server.controller import SubiquityController
from subiquitycore.context import with_context
from subiquitycore.utils import arun_command
from system_setup.common.wsl_conf import wsl_config_update

log = logging.getLogger("system_setup.server.controllers.configure")


class ConfigureController(SubiquityController):
    default_uid = 0

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.model = app.base_model

    def start(self):
        self.install_task = asyncio.create_task(self.configure())

    def __locale_gen_cmd(self) -> Tuple[str, bool]:
        """Return a tuple of the locale-gen command path and True for
        validity. In dry-run, copy the locale-gen script, altering the
        localedef command line to output into a specified directory.
        """
        cmd = "usr/sbin/locale-gen"
        if self.app.opts.dry_run is False or self.app.opts.dry_run is None:
            return (os.path.join("/", cmd), True)

        outDir = os.path.join(self.model.root, "usr/lib/locale")
        usrSbinDir = os.path.join(self.model.root, "usr/sbin")
        os.makedirs(outDir, exist_ok=True)
        os.makedirs(usrSbinDir, exist_ok=True)
        cmdFile = os.path.join(self.model.root, cmd)
        shutil.copy(os.path.join("/", cmd), cmdFile)
        # Supply LC_* definition files to avoid complains from localedef.
        candidateSourceDirs = ["/usr/lib/locale/C.UTF-8/", "/usr/lib/locale/C.utf8/"]
        sourceDirs = [d for d in candidateSourceDirs if os.path.exists(d)]
        if len(sourceDirs) == 0:
            log.error("No available LC_* definitions found in this system")
            return ("", False)

        shutil.copytree(sourceDirs[0], outDir, dirs_exist_ok=True)
        try:
            # Altering locale-gen script to output to the desired folder.
            with open(cmdFile, "r+") as f:
                script = f.read()
                pattern = r"(localedef .+) (\|\| :; \\)"
                localeDefRe = re.compile(pattern)
                replacement = r'\1 "{}/" \2'.format(outDir)
                (fileContents, n) = localeDefRe.subn(replacement, script, count=1)
                if n != 1:
                    log.error(
                        "locale-gen script contents were unexpected."
                        " Aborting mock creation"
                    )
                    return ("", False)

                f.seek(0)
                f.write(fileContents)

            return (cmdFile, True)

        except IOError as err:
            log.error("Failed to modify %s file. %s", cmdFile, err)
            return ("", False)

    def __update_locale_cmd(self, lang) -> List[str]:
        """Add mocking cli to update-locale if in dry-run."""
        # A fixed path should be ok here since all releases (so far) ship
        # the locales package.
        updateLocCmd = [
            "/usr/sbin/update-locale",
            "LANG={}".format(lang),
            "--no-checks",
        ]
        if not self.app.opts.dry_run:
            return updateLocCmd

        defaultLocDir = os.path.join(self.model.root, "etc/default/")
        os.makedirs(defaultLocDir, exist_ok=True)
        updateLocCmd += ["--locale-file", os.path.join(defaultLocDir, "locale")]
        return updateLocCmd

    async def _activate_locale(self, lang, env, skipLocGen=False) -> bool:
        """Return true if succeed in running the last commands
        to set the locale.
        """
        (locGenCmd, ok) = self.__locale_gen_cmd()
        if not ok:
            log.error("Locale generation failed.")
            return False

        updateCmd = self.__update_locale_cmd(lang)
        cmds = [updateCmd] if skipLocGen else [[locGenCmd], updateCmd]
        for cmd in cmds:
            cp = await arun_command(cmd, env=env)
            if cp.returncode != 0:
                log.error(
                    'Command "{}" failed with return code {}'.format(
                        cp.args, cp.returncode
                    )
                )
                return False

        return True

    async def __recommended_language_packs(self, lang, env) -> Optional[List[str]]:
        """Return a list of package names recommended by
        check-language-support (or a fake list if in dryrun).
        List returned can be empty on success. None for failure.
        """
        # lang code may be separated by @, dot or spaces.
        # clsLang = lang.split('@')[0].split('.')[0].split(' ')[0]
        pattern = re.compile(r"([^.@\s]+)", re.IGNORECASE)
        matches = pattern.match(lang)
        if matches is None:
            log.error("Failed to match expected language format: %s", lang)
            return None

        langCodes = matches.groups()
        if len(langCodes) != 1:
            log.error("Only one match was expected for: %s", lang)
            return None

        clsLang = langCodes[0]
        packages = []
        # Running that command doesn't require root.
        snap_dir = os.getenv("SNAP", default="/")
        # UDI sets the SNAP env var to '.' for development purposes.
        # See:
        # https://github.com/canonical/ubuntu-desktop-installer/commit/9eb6f04
        # It is unlikely that under test or production that env var will
        # ever by just '.'. On the other hand in dry-run we want it pointing to
        # '/' if not properly set.
        snap_dir = snap_dir if snap_dir != "." else "/"
        data_dir_base = "usr/share/language-selector"
        data_dir = os.path.join(snap_dir, data_dir_base)
        # jammy does not (yet?) ship language-selector seeded.
        # being defensive to prevent crashes.
        clsCommand = "check-language-support"
        envcp = None
        if not os.path.exists(data_dir):
            log.error(
                "Language selector data dir %s seems not to be part" " of the snap.",
                data_dir,
            )
            # Try seeded L-S-C
            data_dir = os.path.join(self.model.root, data_dir_base)
            if not os.path.exists(data_dir):
                log.error("Cannot find language selector data directory.")
                return None

            # The env parameter is only needed if the package isn't in the snap
            envcp = env
            clsCommand = os.path.join("/usr/bin/", clsCommand)

        cp = await arun_command([clsCommand, "-d", data_dir, "-l", clsLang], env=envcp)
        if cp.returncode != 0:
            log.error('Command "%s" failed with return code %d', cp.args, cp.returncode)
            if not self.app.opts.dry_run:
                return None

        else:
            packages += [pkg for pkg in cp.stdout.strip().split(" ") if pkg]

        # We will always have language-pack-{baseLang}-base in dryrun.
        if len(packages) == 0 and self.app.opts.dry_run:
            baseLang = clsLang.split("_")[0]
            packages += ["language-pack-{}-base".format(baseLang)]

        return packages

    async def _install_check_lang_support_packages(self, lang, env) -> bool:
        """Install recommended packages.
        lang is expected to be one single language/locale.
        """
        packages = await self.__recommended_language_packs(lang, env)
        # Hardcoded path is necessary to ensure escaping out of the snap env.
        aptCommand = "/usr/bin/apt"
        if packages is None:
            log.error("Failed to detect recommended language packs.")
            return False

        if not self.app.opts.dry_run:
            cp = await arun_command([aptCommand, "update"], env=env)
            if cp.returncode != 0:
                log.debug("Failed to update apt cache.\n%s", cp.stderr)

        if self.app.opts.dry_run:  # only empty in dry-run on failure.
            if len(packages) == 0:
                log.error("Packages list in dry-run should never be empty.")
                return False

            log.debug(
                "%s ignored for testing.", self.model.wslsetupoptions.wslsetupoptions
            )
            packs_dir = os.path.join(self.model.root, "var/cache/apt/archives/")
            os.makedirs(packs_dir, exist_ok=True)
            try:
                for package in packages:
                    # Just write the apt simulation log if succeeds.
                    lcp = await arun_command(
                        [aptCommand, "install", package, "--simulate"], env=env
                    )
                    archive = os.path.join(packs_dir, package + ".log")
                    with open(archive, "wt") as f:
                        if lcp.returncode == 0:
                            f.write(lcp.stdout)
                        # otherwise file will be empty.

                return True

            except IOError as e:
                log.error("Failed to write file.", e)
                return False

        if len(packages) == 0:
            log.info("No missing recommended packages. Nothing to do.")
            return True

        cmd = []
        opts = self.model.wslsetupoptions.wslsetupoptions
        if opts is None or opts.install_language_support_packages is True:
            cmd = [aptCommand, "install", "-y"]

        else:
            cmd = ["/usr/bin/apt-mark", "install"]

        cmd = cmd + packages
        acp = await arun_command(cmd, env=env)

        return acp.returncode == 0

    def _update_locale_gen_file(self, localeGenPath, lang) -> bool:
        """Uncomment the line in locale.gen file matching lang,
        if found commented. A fully qualified language is expected,
        since that would have passed thru the Locale controller
        validation. e.g. en_UK.UTF-8. Return True for success.
        """
        fileContents: str
        try:
            with open(localeGenPath, "r+") as f:
                fileContents = f.read()
                lineFound = fileContents.find(lang)
                if lineFound == -1:
                    # An unsupported locale coming from our UI is a bug
                    log.error("Selected language %s not supported.", lang)
                    return False

                pattern = r"[# ]*({}.*)".format(lang)
                commented = re.compile(pattern)
                (fileContents, n) = commented.subn(r"\1", fileContents, count=1)
                if n != 1:
                    log.error("Unexpected locale.gen file contents. Aborting.")
                    return False

                f.seek(0)
                f.write(fileContents)
                return True

        except IOError as err:
            log.error("Failed to modify %s file. %s", localeGenPath, err)
            return False

    def _locale_gen_file_path(self):
        """Return the proper locale.gen path for dry or live-run."""
        localeGenPath = "/etc/locale.gen"
        if self.app.opts.dry_run is False or self.app.opts.dry_run is None:
            return localeGenPath

        # For testing purposes.
        etc_dir = os.path.join(self.model.root, "etc")
        testLocGenPath = os.path.join(etc_dir, os.path.basename(localeGenPath))
        shutil.copy(localeGenPath, testLocGenPath)
        shutil.copy(localeGenPath, "{}.test".format(testLocGenPath))
        return testLocGenPath

    async def apply_locale(self, lang, env):
        """Effectively apply the locale setup to the new system."""
        localeGenPath = self._locale_gen_file_path()
        if self._update_locale_gen_file(localeGenPath, lang) is False:
            log.error("Failed to update locale.gen")
            return

        ok = await self._install_check_lang_support_packages(lang, env)
        if not ok:
            log.error("Failed to install recommended language packs.")
            return

        # We want to run locale-gen if apt fails to install language packs,
        # so the other locale definitions match the user expectation.
        ok = await self._activate_locale(lang, env, skipLocGen=ok)
        if not ok:
            log.error("Failed to run locale activation commands.")
            return

    def __query_uid(self, etc_dir, username):
        """Finds the UID of username in etc_dir/passwd file."""
        uid = None
        with open(os.path.join(etc_dir, "passwd")) as f:
            for line in f:
                tokens = line.split(":")
                if username == tokens[0]:
                    if len(tokens) != 7:
                        raise Exception("Invalid passwd entry")

                    uid = int(tokens[2])
                    break

        return uid

    async def create_user(self, root_dir, env):
        """Helper method to create the user from the identity model
        and store it's UID."""
        wsl_id = self.model.identity.user
        username = wsl_id.username
        create_user_base = []
        assign_grp_base = []
        usergroups_list = get_users_and_groups()
        etc_dir = "/etc"  # default if not dryrun.
        if self.app.opts.dry_run:
            log.debug("creating a mock-up env for user %s", username)
            # creating folders and files for dryrun
            etc_dir = os.path.join(root_dir, "etc")
            os.makedirs(etc_dir, exist_ok=True)
            home_dir = os.path.join(root_dir, "home")
            os.makedirs(home_dir, exist_ok=True)
            pseudo_files = ["passwd", "shadow", "gshadow", "group", "subgid", "subuid"]
            for file in pseudo_files:
                filepath = os.path.join(etc_dir, file)
                open(filepath, "a").close()

            # mimic groupadd
            group_id = 1000
            for group in usergroups_list:
                group_filepath = os.path.join(etc_dir, "group")
                gshadow_filepath = os.path.join(etc_dir, "gshadow")
                shutil.copy(group_filepath, "{}-".format(group_filepath))
                with open(group_filepath, "a") as group_file:
                    group_file.write("{}:x:{}:\n".format(group, group_id))
                group_id += 1
                shutil.copy(gshadow_filepath, "{}-".format(gshadow_filepath))
                with open(gshadow_filepath, "a") as gshadow_file:
                    gshadow_file.write("{}:!::\n".format(group))

            create_user_base = ["-P", root_dir]
            assign_grp_base = ["-P", root_dir]

        create_user_cmd = (
            ["/usr/sbin/useradd"]
            + create_user_base
            + [
                "-m",
                "-s",
                "/bin/bash",
                "-c",
                wsl_id.realname,
                "-p",
                wsl_id.password,
                username,
            ]
        )
        assign_grp_cmd = (
            ["/usr/sbin/usermod"]
            + assign_grp_base
            + ["-a", "-G", ",".join(usergroups_list), username]
        )

        create_user_proc = await arun_command(create_user_cmd, env=env)
        if create_user_proc.returncode != 0:
            raise Exception(
                "Failed to create user %s: %s" % (username, create_user_proc.stderr)
            )
        log.debug("created user %s", username)

        self.default_uid = self.__query_uid(etc_dir, username)
        if self.default_uid is None:
            log.error("Could not retrieve %s UID", username)

        assign_grp_proc = await arun_command(assign_grp_cmd, env=env)
        if assign_grp_proc.returncode != 0:
            raise Exception(
                ("Failed to assign group to user %s: %s")
                % (username, assign_grp_proc.stderr)
            )

    @with_context(
        description="final system configuration", level="INFO", childlevel="DEBUG"
    )
    async def configure(self, *, context):
        """Apply the installation steps submitted by the user."""
        context.set("is-install-context", True)
        try:
            self.app.update_state(ApplicationState.WAITING)

            await self.model.wait_install()

            self.app.update_state(ApplicationState.NEEDS_CONFIRMATION)

            self.app.update_state(ApplicationState.RUNNING)

            await self.model.wait_postinstall()

            self.app.update_state(ApplicationState.WAITING)

            self.app.update_state(ApplicationState.RUNNING)

            variant = self.app.variant
            root_dir = self.model.root

            if variant == "wsl_setup":
                lang = self.model.locale.selected_language
                envcp = os.environ.copy()
                # Ensures a safe escape out of the snap environment for WSL.
                if not self.app.opts.dry_run:
                    envcp["LD_LIBRARY_PATH"] = ""
                    envcp["LD_PRELOAD"] = ""
                await self.create_user(root_dir, envcp)
                await self.apply_locale(lang, envcp)

            # update wsl.conf when it is in autoinstall mode or reconf variant.
            if variant == "wsl_configuration" or self.app.opts.autoinstall is not None:
                wsl_config_update(self.model.wslconfbase.wslconfbase, root_dir)
                wsl_config_update(self.model.wslconfadvanced.wslconfadvanced, root_dir)

            self.app.update_state(ApplicationState.DONE)

        except Exception:
            kw = {}
            self.app.make_apport_report(
                ErrorReportKind.INSTALL_FAIL, "configuration failed", **kw
            )
            raise

    def stop_uu(self):
        # This is a no-op to allow Shutdown controller to depend on this one
        pass

    # Allows passing the recently created user UID to the Shutdown controller.
    def get_default_uid(self):
        return self.default_uid
