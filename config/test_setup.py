"""Install guard probes use isolated directories, no network or database commands."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from django.test import SimpleTestCase

SETUP=Path(__file__).resolve().parents[1]/'scripts'/'setup.sh'


class SetupGuardTests(SimpleTestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'scripts').mkdir();shutil.copyfile(SETUP,self.root/'scripts'/'setup.sh')
        (self.root/'requirements.txt').write_text('controlled fixture; never installed\n')
        self.log=self.root/'actions.jsonl'
        self.real=sys.executable

    def wrapper(self,path,version=None,delegate=None):
        """Controlled version probes; actual temporary venvs, mocked pip/management."""
        child='#!'+self.real+'\n'+"""
import json, os, pathlib, sys
args=sys.argv[1:]
if args[:2]==['-m','pip'] or (args and args[0]=='manage.py'):
    with pathlib.Path(os.environ['SETUP_TEST_LOG']).open('a') as handle:
        handle.write(json.dumps(args)+'\\n')
    sys.exit(0)
interpreter=__ENV_PYTHON__
os.execv(interpreter,[interpreter,*args])
"""
        code="""#!__ROOT_SHEBANG__
import json, os, pathlib, subprocess, sys
ROOT_PYTHON=__ROOT_VALUE__
CHILD=__CHILD_VALUE__
VERSION=__VERSION_VALUE__
DELEGATE=__DELEGATE_VALUE__
args=sys.argv[1:]
if args[:2]==['-m','venv']:
    with pathlib.Path(os.environ['SETUP_TEST_LOG']).open('a') as handle:
        handle.write(json.dumps(args)+'\\n')
    subprocess.run([ROOT_PYTHON,'-m','venv','--without-pip',args[2]],check=True)
    binary=pathlib.Path(args[2])/'bin'/'python'
    real=binary.with_name('python-real')
    binary.rename(real)
    binary.write_text(CHILD.replace('__ENV_PYTHON__',repr(str(real.absolute()))))
    binary.chmod(0o700)
    sys.exit(0)
if args and args[0]=='-c' and VERSION is not None:
    print(VERSION);sys.exit(0)
interpreter=DELEGATE or ROOT_PYTHON
os.execv(interpreter,[interpreter,*args])
""".replace('__ROOT_SHEBANG__',self.real).replace('__ROOT_VALUE__',repr(self.real)).replace('__CHILD_VALUE__',repr(child)).replace('__VERSION_VALUE__',repr(version)).replace('__DELEGATE_VALUE__',repr(str(delegate)) if delegate else 'None')
        path.write_text(code);path.chmod(0o700)
        return path

    def run_setup(self,python):
        env=os.environ.copy();env.update(SHOPHOT_PYTHON=str(python),SETUP_TEST_LOG=str(self.log))
        return subprocess.run(['bash','scripts/setup.sh'],cwd=self.root,env=env,capture_output=True,text=True,timeout=30)

    def actions(self):
        return [json.loads(row) for row in self.log.read_text().splitlines()] if self.log.exists() else []

    def existing(self):
        subprocess.run([self.real,'-m','venv','--without-pip',str(self.root/'.venv')],check=True,capture_output=True,timeout=20)
        return self.root/'.venv'

    def test_below_required_version_refuses_before_existing_or_new_environment_writes(self):
        chosen=self.wrapper(self.root/'python311',version='3.11')
        result=self.run_setup(chosen)
        self.assertNotEqual(result.returncode,0);self.assertIn('低于要求的 3.12',result.stderr)
        self.assertFalse((self.root/'.venv').exists());self.assertEqual(self.actions(),[])
        (self.root/'.venv').mkdir();(self.root/'.venv'/'marker').write_text('keep')
        self.assertNotEqual(self.run_setup(chosen).returncode,0)
        self.assertEqual((self.root/'.venv'/'marker').read_text(),'keep');self.assertEqual(self.actions(),[])

    def test_missing_or_invalid_selected_executable_is_visible_and_does_not_mutate(self):
        result=self.run_setup(self.root/'no-python')
        self.assertNotEqual(result.returncode,0);self.assertIn('找不到所选 Python',result.stderr)
        result=self.run_setup(self.wrapper(self.root/'malformed',version='invalid output'))
        self.assertNotEqual(result.returncode,0);self.assertIn('无法核对',result.stderr)
        self.assertEqual(self.actions(),[]);self.assertFalse((self.root/'.venv').exists())

    def test_existing_different_major_minor_is_rejected_without_rewriting_cfg(self):
        if sys.version_info[:2]<(3,12):self.skipTest('Positive venv fixtures require Python3.12+')
        env=self.existing();before=(env/'pyvenv.cfg').read_bytes()
        chosen=self.wrapper(self.root/'different',version=f'{sys.version_info.major}.{sys.version_info.minor+1}')
        result=self.run_setup(chosen)
        self.assertNotEqual(result.returncode,0);self.assertIn('主次版本不同',result.stderr)
        self.assertEqual((env/'pyvenv.cfg').read_bytes(),before);self.assertEqual(self.actions(),[])

    def test_mixed_configuration_and_runtime_is_rejected_before_installation(self):
        if sys.version_info[:2]<(3,12):self.skipTest('Positive venv fixtures require Python3.12+')
        env=self.existing();cfg=env/'pyvenv.cfg'
        text=cfg.read_text().replace(f'version = {sys.version_info.major}.{sys.version_info.minor}', 'version = 3.11')
        cfg.write_text(text);before=cfg.read_bytes()
        result=self.run_setup(self.real)
        self.assertNotEqual(result.returncode,0);self.assertIn('配置与实际 Python 不一致',result.stderr)
        self.assertEqual(cfg.read_bytes(),before);self.assertEqual(self.actions(),[])

    def test_broken_existing_environment_file_and_symlink_are_not_overwritten(self):
        if sys.version_info[:2]<(3,12):self.skipTest('Selected runtime must meet3.12')
        env=self.root/'.venv';env.write_text('keep original')
        result=self.run_setup(self.real)
        self.assertNotEqual(result.returncode,0);self.assertIn('不是完整',result.stderr);self.assertEqual(env.read_text(),'keep original')
        env.unlink();env.symlink_to(self.root/'missing-env',target_is_directory=True)
        result=self.run_setup(self.real)
        self.assertNotEqual(result.returncode,0);self.assertTrue(env.is_symlink());self.assertEqual(self.actions(),[])

    def test_new_environment_runs_exact_fixed_install_migrate_check_without_accounts(self):
        if sys.version_info[:2]<(3,12):self.skipTest('Positive venv fixtures require Python3.12+')
        chosen=self.wrapper(self.root/'chosen python')
        result=self.run_setup(chosen)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.actions(),[['-m','venv','.venv'],['-m','pip','install','--disable-pip-version-check','-r','requirements.txt'],['manage.py','migrate','--noinput'],['manage.py','check']])
        self.assertTrue((self.root/'.venv'/'pyvenv.cfg').is_file())
        before=(self.root/'.venv'/'pyvenv.cfg').read_bytes();self.log.unlink()
        result=self.run_setup(chosen)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.actions()[0],['-m','pip','install','--disable-pip-version-check','-r','requirements.txt'])
        self.assertEqual(len(self.actions()),3)
        self.assertEqual((self.root/'.venv'/'pyvenv.cfg').read_bytes(),before)
