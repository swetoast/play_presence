from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'install.sh'

def test_bootstrap_shell_syntax():
 subprocess.run(['sh','-n',str(SCRIPT)],check=True)

def test_bootstrap_is_executable():
 assert SCRIPT.stat().st_mode & 0o111

def test_bootstrap_uses_expected_repository_and_volatile_workspace():
 text=SCRIPT.read_text()
 assert 'swetoast/play_presence' in text
 assert '/tmp/play-presence-install.$$' in text
 assert 'archive/refs/heads/$BRANCH.tar.gz' in text
 assert 'deploy/install.py' in text
 assert 'python3 deploy/install.py "$@"' in text
 assert 'trap cleanup EXIT INT TERM HUP' in text
 assert '/dev/tty' in text
 assert 'stty -echo' in text
 assert 'first installation needs --password-file' in text

def test_compatibility_sensitive_identifiers_remain_unchanged():
 assert (ROOT/'src/play_presence').is_dir()
 unit=(ROOT/'deploy/play-presence.service').read_text()
 assert 'play_presence' in unit
 assert '/opt/play-presence' in unit
 config=(ROOT/'src/play_presence/config.py').read_text()
 assert "f'{self.topic_prefix}/state'" in config
 assert "f'{self.topic_prefix}/artwork'" in config
