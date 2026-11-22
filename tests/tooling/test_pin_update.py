# SPDX-License-Identifier: Apache-2.0
"""Checks of the automated pin update: scripts/pin_evidence.py, which writes the body of the pin pull
request and puts the CI evidence of step 3 into it, the GitHub workflow crux-pin-update.yml and the
Jenkins example. The Crux scripts that the workflow calls are not in this repository."""

import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import pin_evidence  # noqa: E402

WORKFLOWS = ROOT / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "crux-pin-update.yml"
JENKINS = ROOT / "Jenkinsfile.example"
LOCK = ROOT / "scripts" / "crux-pin-requirements.txt"
PIN_SCRIPTS = ("crux-pin-bot.py", "update-crux-pin.py", "open-pin-pr.py")
BRANCH = "bot/crux-pin"

HEAD = "fedcba9876543210fedcba9876543210fedcba98"
IMAGE = "a" * 64
IDENTITY = "b" * 64

# As `gh run view --log` prints it: job, step and a timestamp before each line.
RELEASE_LOG = (
    "Release dry run (publishes nothing)\tPrint the release manifest\t"
    "2026-11-22T03:10:00.0000000Z ##[group]Run cat bundle/release-manifest.json\n"
    "Release dry run (publishes nothing)\tPrint the release manifest\t"
    "2026-11-22T03:10:00.1000000Z {\n"
    "Release dry run (publishes nothing)\tPrint the release manifest\t"
    f'2026-11-22T03:10:00.1000000Z   "firmware_identity": "{IDENTITY}",\n'
    "Release dry run (publishes nothing)\tPrint the release manifest\t"
    '2026-11-22T03:10:00.1000000Z   "target": "mimxrt1060_evk@B//qspi",\n'
    "Release dry run (publishes nothing)\tPrint the release manifest\t"
    f'2026-11-22T03:10:00.1000000Z   "zephyr_bin_sha256": "{IMAGE}"\n'
    "Release dry run (publishes nothing)\tPrint the release manifest\t"
    "2026-11-22T03:10:00.1000000Z }\n"
)


def budget_log(step, flash_used="123456"):
    prefix = f"Budget {step}\tCollect, check and summarise\t2026-11-22T03:20:00.0000000Z "
    lines = [
        f"### {step}",
        f"| {step} region | Used (B) | Size (B) | Free (%) |",
        "| --- | ---: | ---: | ---: |",
        f"| FLASH | {flash_used} | 8388608 | 98.5 |",
        "| RAM | 65536 | 524288 | 87.5 |",
        "```json",
    ]
    return "".join(prefix + line + "\n" for line in lines)


class ReleaseValues(unittest.TestCase):
    def test_the_hash_and_the_identity_are_read_from_the_printed_manifest(self):
        self.assertEqual({"zephyr_bin_sha256": IMAGE, "firmware_identity": IDENTITY},
                         pin_evidence.release_values(RELEASE_LOG))

    def test_a_plain_log_without_prefixes_is_read_too(self):
        plain = f'  "zephyr_bin_sha256": "{IMAGE}"\n  "firmware_identity": "{IDENTITY}",\n'
        self.assertEqual(IMAGE, pin_evidence.release_values(plain)["zephyr_bin_sha256"])

    def test_a_log_without_the_manifest_gives_nothing(self):
        self.assertEqual({}, pin_evidence.release_values("the job failed\n"))

    def test_two_different_values_are_refused(self):
        other = RELEASE_LOG.replace(IMAGE, "c" * 64)
        with self.assertRaises(ValueError):
            pin_evidence.release_values(RELEASE_LOG + other)

    def test_a_value_that_is_not_a_sha256_is_ignored(self):
        bad = '  "zephyr_bin_sha256": "<script>",\n  "firmware_identity": "abc"\n'
        self.assertEqual({}, pin_evidence.release_values(bad))


class BudgetTables(unittest.TestCase):
    def test_the_tables_of_each_step_are_read(self):
        tables = pin_evidence.budget_tables(budget_log("S0") + budget_log("S2"))
        self.assertEqual(["S0", "S2"], sorted(tables))
        self.assertEqual([("FLASH", 123456, 8388608, "98.5"), ("RAM", 65536, 524288, "87.5")],
                         tables["S2"])

    def test_steps_sort_by_number(self):
        tables = pin_evidence.budget_tables(budget_log("S10") + budget_log("S2"))
        self.assertEqual(["S2", "S10"], pin_evidence.step_order(tables))

    def test_a_row_that_is_not_a_region_line_ends_the_table(self):
        log = budget_log("S1").replace("| RAM | 65536 |", "| RAM; rm -rf / | 65536 |")
        self.assertEqual([("FLASH", 123456, 8388608, "98.5")], pin_evidence.budget_tables(log)["S1"])

    def test_the_last_table_of_a_step_wins(self):
        tables = pin_evidence.budget_tables(budget_log("S2", "1") + budget_log("S2", "2"))
        self.assertEqual(2, tables["S2"][0][1])

    def test_the_table_that_budgets_check_prints_is_read_back(self):
        sys.path.insert(0, str(ROOT / "budgets"))
        import check

        measurement = {"step": "S3", "regions": {
            "FLASH": {"used": 900, "size": 1000}, "RAM": {"used": 1100, "size": 1000},
            "EMPTY": {"used": 0, "size": 0}}}
        log = "".join(f"Budget S3\tCollect, check and summarise\t2026-11-22T03:20:00.0Z {line}\n"
                      for line in check.table(measurement).splitlines())
        self.assertEqual([("EMPTY", 0, 0, "nan"), ("FLASH", 900, 1000, "10.0"), ("RAM", 1100, 1000, "-10.0")],
                         pin_evidence.budget_tables(log)["S3"])

    def test_a_log_without_tables_gives_nothing(self):
        self.assertEqual({}, pin_evidence.budget_tables("no table here\n"))


class Body(unittest.TestCase):
    def test_the_review_text_says_what_a_person_checks_and_holds_the_empty_section(self):
        body = pin_evidence.review_body()
        for needle in ("CHANGELOG.md", "west.yml", "budgets/limits.json", "does not merge"):
            self.assertIn(needle, body)
        self.assertIn(pin_evidence.START, body)
        self.assertIn(pin_evidence.END, body)
        self.assertIn("not available", body)

    def test_the_section_of_the_review_text_is_replaced_by_the_evidence(self):
        body = pin_evidence.splice(pin_evidence.review_body(), pin_evidence.section(HEAD, RELEASE_LOG, None))
        self.assertIn(f"`{IMAGE}`", body)
        self.assertEqual(1, body.count(pin_evidence.START))
        self.assertIn("does not merge", body)


class Evidence(unittest.TestCase):
    def test_the_section_holds_the_hash_the_identity_the_tables_and_the_commit(self):
        section = pin_evidence.section(HEAD, RELEASE_LOG, budget_log("S0") + budget_log("S2"))
        self.assertIn(f"`{HEAD}`", section)
        self.assertIn(f"`{IMAGE}`", section)
        self.assertIn(f"`{IDENTITY}`", section)
        self.assertIn("| S2 region | Used (B) | Size (B) | Free (%) |", section)
        self.assertIn("| FLASH | 123456 | 8388608 | 98.5 |", section)
        self.assertTrue(section.startswith(pin_evidence.START))
        self.assertTrue(section.rstrip().endswith(pin_evidence.END))

    def test_missing_logs_are_said_not_hidden(self):
        section = pin_evidence.section(HEAD, None, None)
        self.assertIn("not available", section)
        self.assertNotIn("| S2 region", section)

    def test_the_section_replaces_the_old_one_and_keeps_the_rest(self):
        body = f"intro\n\n{pin_evidence.START}\nold evidence\n{pin_evidence.END}\n\nend\n"
        new = pin_evidence.splice(body, pin_evidence.section(HEAD, RELEASE_LOG, None))
        self.assertTrue(new.startswith("intro\n"))
        self.assertTrue(new.endswith("end\n"))
        self.assertNotIn("old evidence", new)
        self.assertEqual(1, new.count(pin_evidence.START))

    def test_a_body_without_the_markers_gets_the_section_appended(self):
        new = pin_evidence.splice("written by hand\n", pin_evidence.section(HEAD, None, None))
        self.assertTrue(new.startswith("written by hand\n"))
        self.assertIn(pin_evidence.START, new)

    def test_splicing_twice_gives_the_same_body(self):
        section = pin_evidence.section(HEAD, RELEASE_LOG, budget_log("S2"))
        once = pin_evidence.splice("intro\n", section)
        self.assertEqual(once, pin_evidence.splice(once, section))


class CommandLine(unittest.TestCase):
    def run_script(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "pin_evidence.py"), *args],
                              capture_output=True, text=True)

    def test_body_then_evidence_through_the_command_line(self):
        with tempfile.TemporaryDirectory() as directory:
            work = pathlib.Path(directory)
            body = self.run_script("body")
            self.assertEqual(0, body.returncode, body.stderr)
            (work / "body.md").write_text(body.stdout)
            (work / "release.log").write_text(RELEASE_LOG)
            (work / "budget.log").write_text(budget_log("S2"))
            done = self.run_script("evidence", "--body", str(work / "body.md"), "--head", HEAD,
                                   "--release-log", str(work / "release.log"),
                                   "--budget-log", str(work / "budget.log"))
            self.assertEqual(0, done.returncode, done.stderr)
            self.assertIn(f"`{IMAGE}`", done.stdout)
            self.assertIn("does not merge", done.stdout)

    def test_a_bad_head_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            body = pathlib.Path(directory) / "body.md"
            body.write_text("x\n")
            result = self.run_script("evidence", "--body", str(body), "--head", "HEAD")
            self.assertEqual(2, result.returncode)


def triggers(data):
    # PyYAML reads the key `on` as the boolean True.
    return data.get("on", data.get(True))


class Workflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text()
        cls.data = yaml.safe_load(cls.text)
        cls.jobs = cls.data["jobs"]

    def commands(self, job):
        return "\n".join(step.get("run", "") for step in self.jobs[job]["steps"])

    def test_runs_daily_by_hand_and_after_the_release_and_budget_runs_of_the_bot_branch(self):
        on = triggers(self.data)
        self.assertEqual({"schedule", "workflow_dispatch", "workflow_run"}, set(on))
        self.assertEqual(1, len(on["schedule"]))
        self.assertRegex(on["schedule"][0]["cron"], r"^\d+ \d+ \* \* \*$")
        self.assertEqual({"release", "budget"}, set(on["workflow_run"]["workflows"]))
        self.assertEqual(["completed"], on["workflow_run"]["types"])
        self.assertEqual([BRANCH], on["workflow_run"]["branches"])
        names = {yaml.safe_load((WORKFLOWS / f"{n}.yml").read_text())["name"] for n in ("release", "budget")}
        self.assertEqual({"release", "budget"}, names)

    def test_the_automatic_token_can_only_read_except_for_the_evidence_edit(self):
        # The pin branch is pushed and the pull request opened with CRUX_PIN_TOKEN, not with it.
        self.assertEqual({"contents": "read"}, self.data["permissions"])
        self.assertEqual({"update", "evidence"}, set(self.jobs))
        self.assertNotIn("permissions", self.jobs["update"])
        self.assertEqual({"actions": "read", "contents": "read", "pull-requests": "write"},
                         self.jobs["evidence"]["permissions"])

    def test_one_secret_and_no_fallback_to_the_automatic_token_for_the_push(self):
        self.assertEqual({"CRUX_PIN_TOKEN"}, set(re.findall(r"secrets\.([A-Z_]+)", self.text)))
        self.assertNotRegex(self.text, r"secrets\.CRUX_PIN_TOKEN *\|\|")
        update = self.jobs["update"]
        self.assertNotIn("github.token", yaml.safe_dump(update))
        # Only the steps that need the token see it; not the checkout, pip or west.
        self.assertNotIn("env", update)
        holders = [s.get("name") or s.get("uses") for s in update["steps"]
                   if "CRUX_PIN_TOKEN" in yaml.safe_dump(s)]
        self.assertEqual(["Check that the token is set", "Move the pin and refresh the pull request"], holders)
        self.assertIn("--token-env CRUX_PIN_TOKEN", self.commands("update"))

    def test_the_checkout_leaves_no_credential_in_the_git_config_for_pip_and_west(self):
        checkout = next(s for s in self.jobs["update"]["steps"] if s.get("uses", "").startswith("actions/checkout"))
        self.assertIs(False, checkout["with"]["persist-credentials"])
        self.assertNotIn("token", checkout["with"])

    def test_the_push_credential_lives_only_inside_the_bot_step(self):
        bot = next(s for s in self.jobs["update"]["steps"] if "crux-pin-bot.py --host" in s.get("run", ""))
        run = bot["run"]
        header = "http.https://github.com/.extraheader"
        self.assertIn(f"git config --local {header}", run)
        self.assertIn("::add-mask::", run)
        # Removed again on every exit, before the step ends.
        self.assertRegex(run, rf"trap '[^']*git config --local --unset-all {re.escape(header)}[^']*' EXIT")
        self.assertLess(run.index("trap "), run.index(f"git config --local {header} "))
        self.assertLess(run.index(f"git config --local {header} "), run.index("crux-pin-bot.py --host"))

    def test_no_build_runs_in_the_update_job(self):
        # The token job runs only reviewed code: the pinned Crux bot and this repository's hook.
        # The new pin is built by the pull request's own workflows, which hold no CRUX_PIN_TOKEN.
        commands = self.commands("update")
        for word in ("west build", "cmake", "ninja", "twister", "make "):
            self.assertNotIn(word, commands)
        for name in ("ci", "budget", "release", "rebuild", "devcontainer"):
            self.assertNotIn("secrets.", (WORKFLOWS / f"{name}.yml").read_text())

    def test_the_update_job_runs_only_on_the_default_branch(self):
        cond = self.jobs["update"]["if"]
        # A schedule event carries no repository payload, so the condition must not read it.
        self.assertNotIn("github.event.repository", cond)
        self.assertIn("github.event_name == 'schedule'", cond)
        self.assertIn("github.ref == 'refs/heads/main'", cond)
        self.assertIn("github.event_name != 'workflow_run'", cond)

    def test_the_evidence_job_ignores_pull_requests_from_forks(self):
        evidence = self.commands("evidence")
        self.assertIn("isCrossRepository", evidence)
        self.assertIn("select(.isCrossRepository == false)", evidence)

    def test_nothing_merges_itself(self):
        for word in ("gh pr merge", "--auto", "automerge", "auto-merge", "git push"):
            self.assertNotIn(word, self.text.replace("no auto-merge", ""), word)

    def test_the_crux_scripts_come_from_the_pinned_crux_and_never_from_crux_main(self):
        update = self.commands("update")
        self.assertIn("west update crux-pilot", update)
        self.assertIn("crux-pilot/scripts/crux-pin-bot.py --host github", update)
        for word in ("update-crux-pin.py", "open-pin-pr.py"):
            self.assertNotIn(word, update)
        for step in self.jobs["update"]["steps"]:
            self.assertNotIn("repository", step.get("with", {}))
        self.assertLess(update.index("west update crux-pilot"), update.index("crux-pin-bot.py"))

    def test_a_pinned_crux_without_the_bot_fails_with_a_short_message(self):
        update = self.commands("update")
        self.assertIn("test -f crux-pilot/scripts/crux-pin-bot.py", update)
        self.assertIn("CONTRIBUTING.md", update)
        self.assertLess(update.index("test -f crux-pilot/scripts/crux-pin-bot.py"),
                        update.index("crux-pilot/scripts/crux-pin-bot.py --host"))

    def test_the_review_text_is_appended_and_the_branch_is_the_bot_branch(self):
        update = self.commands("update")
        self.assertIn("scripts/pin_evidence.py body", update)
        self.assertIn("--append-body", update)
        self.assertIn(f"--branch {BRANCH}", update)
        self.assertNotIn("crux-pin/update", self.text)

    def test_the_evidence_job_also_runs_after_each_refresh(self):
        # A refresh rewrites the body, so the evidence is put back right after it.
        evidence = self.jobs["evidence"]
        self.assertEqual("update", evidence["needs"])
        condition = evidence["if"]
        self.assertIn("!cancelled()", condition)
        self.assertIn("needs.update.result == 'success'", condition)

    def test_the_evidence_job_reads_only_runs_of_the_bot_branch_of_this_repository(self):
        condition = self.jobs["evidence"]["if"]
        for needle in ("workflow_run", BRANCH, "head_repository.full_name == github.repository",
                       "github.event.workflow_run.event == 'pull_request'"):
            self.assertIn(needle, condition)
        self.assertIn("workflow_run", self.jobs["update"]["if"])
        evidence = self.commands("evidence")
        self.assertIn("scripts/pin_evidence.py evidence", evidence)
        self.assertIn("gh pr edit", evidence)
        self.assertIn('"$EVENT_HEAD" != "$head"', evidence)

    def test_the_evidence_job_runs_no_code_of_the_pull_request(self):
        for step in self.jobs["evidence"]["steps"]:
            self.assertNotIn("ref", step.get("with", {}))
        self.assertNotIn("head_sha }}", self.commands("evidence"))

    def test_no_repository_gate_on_the_schedule(self):
        # A copy turns the schedule off in its CI settings instead.
        self.assertNotIn("github.repository ==", self.text)

    def test_every_action_is_pinned_by_a_full_commit_sha_of_the_version_ci_yml_uses(self):
        # A tag can be moved; a commit SHA cannot. The comment names the release the SHA belongs to.
        ci = dict(re.findall(r"uses: ([\w.-]+/[\w.-]+)@v(\d+)", (WORKFLOWS / "ci.yml").read_text()))
        lines = [line.strip() for line in self.text.splitlines() if re.match(r"\s*(- )?uses:", line)]
        self.assertTrue(lines)
        for line in lines:
            match = re.fullmatch(r"(?:- )?uses: ([\w.-]+/[\w.-]+)@([0-9a-f]{40}) # v(\d+)\.\d+\.\d+", line)
            self.assertIsNotNone(match, line)
            name, _, major = match.groups()
            self.assertIn(name, ci, line)
            self.assertEqual(ci[name], major, line)
        for step in (s for job in self.jobs.values() for s in job["steps"] if "uses" in s):
            self.assertRegex(step["uses"], r"@[0-9a-f]{40}$")

    def test_the_tools_come_from_the_hash_lock_only(self):
        install = next(s for s in self.jobs["update"]["steps"] if "pip install" in s.get("run", ""))
        self.assertEqual("python -m pip install --require-hashes -r crux-controller/scripts/crux-pin-requirements.txt",
                         install["run"].strip())
        self.assertNotRegex(self.commands("update"), r"pip install [^\n]*==")

    def test_it_uploads_nothing_and_runs_no_board_command(self):
        for word in ("upload-artifact", "west flash", "west debug", "west build"):
            self.assertNotIn(word, self.text)


class HashLock(unittest.TestCase):
    """scripts/crux-pin-requirements.txt: every tool of the pin job and its dependencies, with hashes."""

    def requirements(self):
        text = re.sub(r"\\\n", " ", LOCK.read_text())
        lines = [" ".join(line.split("#", 1)[0].split()) for line in text.splitlines()]
        return [line for line in lines if line]

    def test_every_requirement_is_pinned_with_sha256_hashes(self):
        found = {}
        for line in self.requirements():
            match = re.fullmatch(r"([a-z0-9][a-z0-9._-]*)==([^\s]+)((?: --hash=sha256:[0-9a-f]{64})+)", line)
            self.assertIsNotNone(match, line)
            self.assertNotIn(match.group(1), found, line)
            found[match.group(1)] = match.group(2)
        # west, PyYAML and what west 1.4.0 pulls in, in the versions the dev container pins.
        self.assertEqual({"colorama", "docopt", "packaging", "pykwalify", "python-dateutil", "pyyaml",
                          "ruamel.yaml", "tzdata", "west"}, set(found))
        tools = dict(re.findall(r"(?m)^([a-z0-9.-]+)==(\S+)$", (ROOT / ".devcontainer" / "requirements-tools.txt").read_text()))
        for name in ("west", "pyyaml"):
            self.assertEqual(tools[name], found[name], name)

    def test_the_jenkins_example_installs_from_it_too(self):
        self.assertIn('/venv/bin/pip" install -q --require-hashes -r crux-controller/scripts/crux-pin-requirements.txt',
                      JENKINS.read_text())
        self.assertNotRegex(JENKINS.read_text(), r"pip install [^\n]*==")


class ArchitectureNamesTheFiles(unittest.TestCase):
    @staticmethod
    def row(start):
        for line in (ROOT / "docs" / "architecture.md").read_text().splitlines():
            if line.startswith(start):
                return line
        raise AssertionError(f"docs/architecture.md has no row {start}")

    def test_the_workflows_row_names_every_workflow(self):
        row = self.row("| `.github/workflows/` |")
        for path in sorted(WORKFLOWS.glob("*.yml")):
            self.assertIn(f"`{path.name}`", row)

    def test_the_top_level_files_row_names_the_jenkins_example(self):
        self.assertIn("`Jenkinsfile.example`", self.row("| `README.md`, `CONTRIBUTING.md`"))


class Contributing(unittest.TestCase):
    def test_the_pin_paragraph_says_what_stays_manual_and_the_jenkins_gap(self):
        text = " ".join((ROOT / "CONTRIBUTING.md").read_text().split())
        self.assertNotIn("does the rest of steps 1 and 2", text)
        self.assertIn("stay manual", text)
        self.assertIn("no evidence step", text)


def hook_quotes():
    """The QUOTES table of scripts/crux-pin-hook, which has no .py suffix to import by."""
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader("crux_pin_hook", str(ROOT / "scripts" / "crux-pin-hook"))
    spec = importlib.util.spec_from_loader("crux_pin_hook", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.QUOTES


def allow_paths(text):
    return re.findall(r"--allow-path (\S+)", text)


class AllowList(unittest.TestCase):
    """The bot commits only the paths given with --allow-path; they must be what the hook edits."""

    def expected(self):
        return {"west.yml"} | {name for name, _, _ in hook_quotes()}

    def test_the_workflow_and_the_jenkins_example_allow_exactly_the_files_of_the_pin_move(self):
        update = "\n".join(s.get("run", "") for s in yaml.safe_load(WORKFLOW.read_text())["jobs"]["update"]["steps"])
        for name, text in (("workflow", update), ("Jenkinsfile.example", JENKINS.read_text())):
            found = allow_paths(text)
            self.assertEqual(len(found), len(set(found)), name)
            self.assertEqual(self.expected(), set(found), name)
            self.assertNotIn("<", " ".join(found), name)

    def test_the_files_the_hook_changes_on_a_copy_of_the_repository_are_allowed(self):
        import os
        import shutil

        with tempfile.TemporaryDirectory() as directory:
            copy = pathlib.Path(directory) / "crux-controller"
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", "build", "__pycache__"))
            before = {p.relative_to(copy).as_posix(): p.read_bytes() for p in copy.rglob("*") if p.is_file()}
            west = copy / "west.yml"
            old = re.search(r"(?m)^\s*revision: ([0-9a-f]{40})$", west.read_text()).group(1)
            new = "0123456789abcdef0123456789abcdef01234567"
            west.write_text(west.read_text().replace(f"revision: {old}", f"revision: {new}"))
            result = subprocess.run([sys.executable, str(copy / "scripts" / "crux-pin-hook")], cwd=copy,
                                    env=dict(os.environ, CRUX_PIN_OLD=old, CRUX_PIN_NEW=new),
                                    capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            after = {p.relative_to(copy).as_posix(): p.read_bytes() for p in copy.rglob("*") if p.is_file()}
        changed = {name for name in set(before) | set(after) if before.get(name) != after.get(name)}
        self.assertIn("west.yml", changed)
        self.assertEqual(self.expected(), changed)

    def test_generated_files_are_written_outside_the_checkout(self):
        # The bot fails on an untracked file outside --allow-path, so nothing is written into it.
        update = yaml.safe_load(WORKFLOW.read_text())["jobs"]["update"]["steps"]
        bot = next(s for s in update if "crux-pin-bot.py --host" in s.get("run", ""))
        self.assertEqual("crux-controller", bot["working-directory"])
        self.assertIn('pin_evidence.py body > "$RUNNER_TEMP/review.md"', bot["run"])
        self.assertIn('pin_evidence.py body > "$T/review.md"', JENKINS.read_text())
        self.assertIn("dir('crux-controller')", JENKINS.read_text())

    def test_the_comments_say_the_token_never_reaches_git(self):
        self.assertIn("never gives the token to Git", WORKFLOW.read_text())
        self.assertIn("never gives the token to Git", JENKINS.read_text())


class BudgetLogHasTheTables(unittest.TestCase):
    def test_the_budget_job_prints_its_summary_to_the_log_as_well(self):
        job = yaml.safe_load((WORKFLOWS / "budget.yml").read_text())["jobs"]["budget"]
        step = next(s for s in job["steps"] if s.get("name") == "Collect, check and summarise")
        self.assertIn('| tee -a "$GITHUB_STEP_SUMMARY"', step["run"])
        self.assertIn("check.table", step["run"])

    def test_the_release_dry_run_prints_the_manifest(self):
        job = yaml.safe_load((WORKFLOWS / "release.yml").read_text())["jobs"]["dry-run"]
        runs = [s.get("run", "") for s in job["steps"]]
        self.assertIn("cat bundle/release-manifest.json", "\n".join(runs))


class JenkinsExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = JENKINS.read_text()

    GUARD = "when { beforeAgent true; allOf { branch 'main'; not { changeRequest() } } }"

    def test_it_runs_only_on_main_and_never_for_a_pull_request_or_the_bot_branch(self):
        self.assertIn("agent none", self.text)
        self.assertEqual(1, self.text.count(self.GUARD))
        # The guarded stage holds the agent and every step, so nothing runs before the guard.
        guard = self.text.index(self.GUARD)
        self.assertLess(guard, self.text.index("dockerfile {"))
        self.assertLess(guard, self.text.index('crux-pin-bot.py" --host'))
        self.assertIn("own scheduled", self.text)
        self.assertIn("BRANCH_NAME", self.text)

    def test_the_push_gets_its_credentials_explicitly(self):
        self.assertIn("gitUsernamePassword(credentialsId: '<", self.text)
        self.assertNotIn("credentials of the checkout", self.text)

    def test_the_credential_stage_runs_no_build_and_the_fetch_stage_holds_no_credential(self):
        fetch, move = self.text.split("stage('Move the pin and refresh the pull request')")
        self.assertNotIn("withCredentials", fetch)
        for word in ("west build", "cmake", "ninja", "twister"):
            self.assertNotIn(word, move)
        self.assertIn("Run no build in this stage", move)

    def test_it_says_the_evidence_step_is_missing(self):
        self.assertIn("no evidence step", self.text)

    def test_it_is_an_example_and_not_an_active_pipeline(self):
        self.assertFalse((ROOT / "Jenkinsfile").exists())
        self.assertIn("Example only", "\n".join(self.text.splitlines()[:5]))

    def test_it_runs_the_bot_of_the_pinned_crux_in_the_dev_container_image_on_a_schedule(self):
        for needle in ("cron(", "dockerfile", ".devcontainer", '/venv/bin/west" update crux-pilot',
                       '"$T/scripts/crux-pin-bot.py" --host bitbucket-cloud',
                       "scripts/pin_evidence.py body", "--append-body", f"--branch {BRANCH}",
                       "CRUX_PIN_TOKEN"):
            self.assertIn(needle, self.text)
        for word in ("git clone", "crux-pin/update", "crux-pilot/scripts/crux-pin-bot.py --host", "../.venv"):
            self.assertNotIn(word, self.text)

    def test_it_starts_from_an_empty_workspace_on_an_agent_of_its_own(self):
        # A workspace kept from an earlier run, or shared with pull request builds of an unreviewed
        # Crux, could hold a planted venv, Crux checkout or Git setting.
        self.assertIn("skipDefaultCheckout()", self.text)
        self.assertRegex(self.text, r"agent \{ label '<[^>]*not shared with pull request builds[^>]*>' \}")
        start = self.text.index("stage('Start clean')")
        clean = self.text[start:self.text.index("stage('Fetch the pinned Crux')")]
        self.assertIn("deleteDir()", clean)
        self.assertIn("dir(env.WORKSPACE_TMP) { deleteDir() }", clean)
        self.assertLess(clean.index("deleteDir()"), clean.index("checkout scm"))
        self.assertLess(start, self.text.index('pip" install'))

    def test_each_code_stage_has_its_own_container_without_host_access(self):
        self.assertEqual(2, self.text.count("reuseNode true"))
        for word in ("docker.sock", "--pid", "--ipc", "--privileged", "--volumes-from", "--network host", "args "):
            self.assertNotIn(word, self.text.split("pipeline {", 1)[1])
        for word in ("docker socket", "--pid=host", "--privileged", "container-local /tmp", "--volumes-from"):
            self.assertIn(word, self.text.split("pipeline {", 1)[0])

    def test_the_pin_scripts_are_copied_from_the_pinned_revision_after_the_checks(self):
        fetch = self.text[self.text.index("stage('Fetch the pinned Crux')"):
                          self.text.index("stage('Move the pin and refresh the pull request')")]
        steps = ['T="$WORKSPACE_TMP/crux-pin"', 'python3 -m venv "$T/venv"', '/venv/bin/west" update crux-pilot',
                 "export GIT_NO_REPLACE_OBJECTS=1",
                 'test "$(git -C crux-pilot rev-parse HEAD)" = "$rev"',
                 'test -z "$(git -C crux-pilot status --porcelain --ignored)"',
                 'git -C crux-pilot cat-file -e "$rev:scripts/crux-pin-bot.py"',
                 'git -C crux-pilot show "$rev:scripts/$script" > "$T/scripts/$script"']
        at = [fetch.index(step) for step in steps]
        self.assertEqual(sorted(at), at)
        self.assertIn(f"for script in {' '.join(PIN_SCRIPTS)}; do", fetch)
        self.assertIn("""/venv/bin/west" list -f '{revision}' crux-pilot""", fetch)
        self.assertIn("CONTRIBUTING.md", fetch)
        move = self.text.split("stage('Move the pin and refresh the pull request')", 1)[1]
        self.assertIn('T="$WORKSPACE_TMP/crux-pin"', move)
        self.assertIn('"$T/venv/bin/python" "$T/scripts/crux-pin-bot.py" --host', move)
        self.assertNotIn("crux-pilot/", move)

    def test_credentials_come_from_jenkins_and_no_host_is_named(self):
        self.assertIn("withCredentials", self.text)
        self.assertNotRegex(self.text, r"https?://")
        self.assertNotRegex(self.text.lower(), r"(password|token)\s*[:=]\s*['\"][^<$]")
        for word in ("gh pr merge", "--auto", "automerge"):
            self.assertNotIn(word, self.text)


class JenkinsCopyBlock(unittest.TestCase):
    """Runs the check-and-copy part of the fetch stage, taken verbatim from Jenkinsfile.example, on a
    local Crux checkout. The part before it (venv, pip, west init and update) needs the network."""

    @classmethod
    def setUpClass(cls):
        text = JENKINS.read_text()
        fetch = text[text.index("stage('Fetch the pinned Crux')"):]
        block = fetch[fetch.index("sh '''") + 6:fetch.index("'''", fetch.index("sh '''") + 6)]
        cls.block = 'set -eu\nT="$WORKSPACE_TMP/crux-pin"\nmkdir -p "$T/scripts"\n' + \
            block.split('/venv/bin/west" update crux-pilot\n', 1)[1]

    def setUp(self):
        import os
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = pathlib.Path(self.temp.name)
        self.work, self.tmp = base / "ws", base / "ws@tmp"
        self.crux = self.work / "crux-pilot"
        (self.crux / "scripts").mkdir(parents=True)
        self.env = dict(os.environ, WORKSPACE_TMP=str(self.tmp), GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t.invalid",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t.invalid", GIT_CONFIG_GLOBAL="/dev/null",
                        GIT_CONFIG_NOSYSTEM="1")
        self.git("init", "-q")
        for script in PIN_SCRIPTS:
            (self.crux / "scripts" / script).write_text(f"# {script} of the pinned Crux\n")
        (self.crux / ".gitignore").write_text("*.log\n")
        self.git("add", ".")
        self.git("commit", "-qm", "pinned")
        self.rev = self.git("rev-parse", "HEAD")
        self.fake_west(self.rev)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.crux), *args], env=self.env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def fake_west(self, revision):
        west = self.tmp / "crux-pin" / "venv" / "bin" / "west"
        west.parent.mkdir(parents=True, exist_ok=True)
        west.write_text(f"#!/bin/sh\necho {revision}\n")
        west.chmod(0o755)

    def run_block(self):
        return subprocess.run(["sh", "-c", self.block], cwd=self.work, env=self.env, capture_output=True, text=True)

    def copied(self, script):
        return (self.tmp / "crux-pin" / "scripts" / script).read_text()

    def test_a_clean_checkout_at_the_pin_gives_the_three_scripts(self):
        result = self.run_block()
        self.assertEqual(0, result.returncode, result.stderr)
        for script in PIN_SCRIPTS:
            self.assertEqual(f"# {script} of the pinned Crux\n", self.copied(script))

    def test_a_changed_untracked_or_ignored_file_stops_it(self):
        for name, change in (("changed", lambda: (self.crux / "scripts" / "open-pin-pr.py").write_text("x\n")),
                             ("untracked", lambda: (self.crux / "stray.py").write_text("x\n")),
                             ("ignored", lambda: (self.crux / "build.log").write_text("x\n"))):
            with self.subTest(name):
                self.git("checkout", "-q", "-f", self.rev)
                self.git("clean", "-qfdx")
                change()
                self.assertNotEqual(0, self.run_block().returncode)

    def test_a_checkout_away_from_the_pin_stops_it(self):
        (self.crux / "scripts" / "crux-pin-bot.py").write_text("# moved\n")
        self.git("commit", "-qam", "moved")
        self.assertNotEqual(0, self.run_block().returncode)

    def test_a_pin_that_is_not_a_full_sha_stops_it(self):
        for revision in (self.rev[:12], "main", self.rev.upper()):
            with self.subTest(revision):
                self.fake_west(revision)
                result = self.run_block()
                self.assertNotEqual(0, result.returncode)
                self.assertIn("not a full commit SHA", result.stderr)

    def test_a_pin_without_the_bot_says_to_move_it_by_hand(self):
        self.git("rm", "-q", "scripts/crux-pin-bot.py")
        self.git("commit", "-qm", "no bot")
        self.fake_west(self.git("rev-parse", "HEAD"))
        result = self.run_block()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("CONTRIBUTING.md", result.stderr)

    def test_a_replace_ref_does_not_change_the_copied_scripts(self):
        planted = subprocess.run(["git", "-C", str(self.crux), "hash-object", "-w", "--stdin"], input="# planted\n",
                                 env=self.env, check=True, capture_output=True, text=True).stdout.strip()
        original = self.git("rev-parse", f"{self.rev}:scripts/crux-pin-bot.py")
        self.git("replace", original, planted)
        self.assertEqual("# planted", self.git("show", f"{self.rev}:scripts/crux-pin-bot.py"))
        result = self.run_block()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("# crux-pin-bot.py of the pinned Crux\n", self.copied("crux-pin-bot.py"))

if __name__ == "__main__":
    unittest.main()
