import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NamedVMConfigTests(unittest.TestCase):
    def shell(self, script):
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(('PRPL', 'LAB_', '_PRPL'))}
        return subprocess.run(['bash', '-euc', script], cwd=ROOT, env=environment,
                              capture_output=True, text=True, timeout=5)

    def test_defaults_are_stable_and_switching_names_isolated(self):
        result = self.shell('''
source deploy/lxd-vm/lab-config.sh demo-a
first=$PRPLMESH_PORT_BASE
test "$PRPLMESH_LXD_STORAGE" = demo-a-pool
source deploy/lxd-vm/lab-config.sh demo-b
test "$PRPLMESH_LXD_STORAGE" = demo-b-pool
test "$PRPLMESH_PORT_BASE" != "$first"
source deploy/lxd-vm/lab-config.sh demo-a
test "$PRPLMESH_PORT_BASE" = "$first"
test "$LAB_OUTER_METRICS_PORT" = "$((first + 5))"
''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_explicit_override_survives_name_switch(self):
        result = self.shell('''
source deploy/lxd-vm/lab-config.sh demo-a
PRPLMESH_PORT_BASE=51000
PRPLMESH_LXD_STORAGE=external-pool
source deploy/lxd-vm/lab-config.sh demo-b
test "$PRPLMESH_PORT_BASE" = 51000
test "$PRPLMESH_ROOM_DEMO_HOST_PORT" = 51002
test "$PRPLMESH_LXD_STORAGE" = external-pool
''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_names_ports_and_duplicates_are_rejected(self):
        for expression in ('prplmesh_instance_config ../unsafe',
                           'prplmesh_instance_config --help',
                           'PRPLMESH_PORT_BASE=08000 prplmesh_instance_config demo',
                           'PRPLMESH_PORT_BASE=65531 prplmesh_instance_config demo',
                           'PRPLMESH_UI_HOST_PORT=45001 PRPLMESH_WMEDIUMD_CONSOLE_HOST_PORT=45001 prplmesh_instance_config demo'):
            with self.subTest(expression=expression):
                result = self.shell('source deploy/lxd-vm/instance-config.sh; ' + expression)
                self.assertNotEqual(result.returncode, 0)

    def test_existing_pool_is_not_recreated(self):
        result = self.shell('''
source deploy/lxd-vm/instance-config.sh
lxc() { test "$*" = "storage show demo-pool"; }
prplmesh_ensure_storage demo-pool
''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_suite_list_is_offline_and_unknown_section_fails(self):
        result = self.shell('bash tests/run-prplmesh-suite.sh all --list')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ['static', 'webui', 'browser', 'rf', 'rf-actions', 'rooms', 'live', 'soak'])
        self.assertEqual(self.shell('bash tests/run-prplmesh-suite.sh --list').stdout.strip(), 'static')
        self.assertNotEqual(self.shell('bash tests/run-prplmesh-suite.sh bad --list').returncode, 0)

    def test_live_mutation_requires_explicit_opt_in(self):
        result = self.shell('bash tests/run-prplmesh-suite.sh rooms live')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--yes-act', result.stderr)


if __name__ == '__main__':
    unittest.main()
