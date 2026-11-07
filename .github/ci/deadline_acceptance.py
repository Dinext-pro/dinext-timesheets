"""Exercise timesheet workflows and real Desk pages on the disposable CI bench."""

import json
import os
from pathlib import Path
import signal
import subprocess
import time
from urllib.error import URLError
from urllib.request import urlopen
import xml.etree.ElementTree as ET


bench = Path(os.environ["RUNNER_TEMP"]) / "dinext-test-bench"
artifacts = Path(os.environ["RUNNER_TEMP"]) / "deadline-acceptance"
artifacts.mkdir()
env = os.environ.copy()
env.update({
	"PYTHONUNBUFFERED": "1",
	"DEV_SERVER": "1",
	"CYPRESS_adminPassword": "ci-admin",
	"CYPRESS_reporter": "junit",
	"CYPRESS_reporterOptions": json.dumps({"mochaFile": str(artifacts / "browser-[hash].xml")}),
})
# bench run-ui-tests derives CYPRESS_baseUrl from the site's host_name.
subprocess.run([
	"bench", "--site", "ci.test", "set-config", "host_name", "http://localhost:8000",
], cwd=bench, check=True)
subprocess.run(["bench", "set-config", "-g", "server_script_enabled", "1"], cwd=bench, check=True)
subprocess.run([
	"bench", "--site", "ci.test", "set-config", "enable_parallel_workflow_approval", "1",
], cwd=bench, check=True)
subprocess.run([
	"bench", "--site", "ci.test", "run-tests", "--skip-before-tests", "--skip-test-records",
	"--module", "dinext_timesheets.tests.test_timesheet_team_lead_access",
	f"--junit-xml-output={artifacts / 'team-lead-server.xml'}",
], cwd=bench, env=env, check=True, timeout=600)

subprocess.run([
	"bench", "--site", "ci.test", "run-tests", "--skip-before-tests", "--skip-test-records",
	"--module", "dinext_timesheets.tests.test_approval_fingerprint_integration",
	"--test", "test_renaming_open_edit_transition_keeps_the_prior_approval",
	f"--junit-xml-output={artifacts / 'utp-edit-server.xml'}",
], cwd=bench, env=env, check=True, timeout=600)

with (artifacts / "web.log").open("w") as log:
	server = subprocess.Popen(
		["bench", "--site", "ci.test", "serve", "--port", "8000", "--noreload"],
		cwd=bench, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
	)
	try:
		for attempt in range(60):
			try:
				with urlopen("http://localhost:8000/api/method/ping", timeout=2) as response:
					if response.status == 200:
						break
			except (URLError, TimeoutError):
				time.sleep(2)
		else:
			raise RuntimeError("Disposable Desk server did not start")
		for config, spec in (
			("cypress.deadline.config.js", "worker_calendar_deadlines.js"),
			("cypress.config.js", "timesheet_team_lead.js"),
		):
			subprocess.run([
				"bench", "--site", "ci.test", "run-ui-tests", "dinext_timesheets",
				"--headless", "--browser", "electron", "--config-file", config,
				"--spec", f"cypress/integration/{spec}", "--config",
				f"baseUrl=http://localhost:8000,screenshotsFolder={artifacts / 'screenshots'}",
			], cwd=bench, env=env, check=True, timeout=1200)
	finally:
		os.killpg(server.pid, signal.SIGTERM)
		server.wait(timeout=30)

reports = list(artifacts.glob("browser-*.xml"))
assert reports, "Cypress did not produce JUnit evidence"
suites = [suite for path in reports for suite in ET.parse(path).iter("testsuite")]
assert sum(int(suite.get("tests", 0)) for suite in suites) == 7, "Expected all seven browser scenarios"
assert not sum(int(suite.get("failures", 0)) + int(suite.get("errors", 0)) for suite in suites)
