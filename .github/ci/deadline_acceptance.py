"""Exercise real Desk pages on the disposable bench built by shared CI."""

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
	"CYPRESS_adminPassword": "ci-admin",
	"CYPRESS_reporter": "junit",
	"CYPRESS_reporterOptions": json.dumps({"mochaFile": str(artifacts / "browser-[hash].xml")}),
})
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
		subprocess.run([
			"bench", "--site", "ci.test", "run-ui-tests", "dinext_timesheets",
			"--headless", "--browser", "electron", "--config-file", "cypress.config.js",
			"--spec", "cypress/integration/worker_calendar_deadlines.js", "--config",
			f"baseUrl=http://localhost:8000,screenshotsFolder={artifacts / 'screenshots'}",
		], cwd=bench, env=env, check=True, timeout=1200)
	finally:
		os.killpg(server.pid, signal.SIGTERM)
		server.wait(timeout=30)

reports = list(artifacts.glob("browser-*.xml"))
assert reports, "Cypress did not produce JUnit evidence"
suites = [suite for path in reports for suite in ET.parse(path).iter("testsuite")]
assert sum(int(suite.get("tests", 0)) for suite in suites) == 6, "Expected all six browser scenarios"
assert not sum(int(suite.get("failures", 0)) + int(suite.get("errors", 0)) for suite in suites)
