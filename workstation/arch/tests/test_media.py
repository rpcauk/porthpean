import os
import pathlib
import subprocess
import tempfile
import unittest

HELPER=pathlib.Path(__file__).resolve().parents[1]/'files/porthpean-media'

class Media(unittest.TestCase):
    def test_prefers_playing_source_and_escapes_its_markup(self):
        with tempfile.TemporaryDirectory() as tmp:
            command=pathlib.Path(tmp)/'playerctl'
            command.write_text('''#!/bin/bash
if [[ $1 == -l ]]; then printf 'mpd\n<browser>.instance\n';
elif [[ $2 == mpd ]]; then echo Paused;
else echo Playing; fi
''')
            command.chmod(0o755)
            result=subprocess.run(['python3',str(HELPER)],env=dict(os.environ,PATH=tmp+':'+os.environ['PATH']),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.strip(),'&lt;browser&gt; | Playing')

    def test_silent_when_no_source_is_playing_or_playerctl_fails(self):
        for response in ('Paused', 'Stopped', '', 'failure'):
            with self.subTest(response=response), tempfile.TemporaryDirectory() as tmp:
                command = pathlib.Path(tmp) / 'playerctl'
                command.write_text('#!/bin/sh\n' + (
                    'exit 1\n' if response == 'failure' else
                    'if [ "$1" = -l ]; then echo mpd; else echo "' + response + '"; fi\n'))
                command.chmod(0o755)
                result = subprocess.run(['python3', str(HELPER)],
                    env=dict(os.environ, PATH=tmp + ':' + os.environ['PATH']), capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, '')
