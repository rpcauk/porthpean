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
