"""External script wiring must remain valid under the production CSP."""
from pathlib import Path
import re
import unittest


class WebAssetTests(unittest.TestCase):
    def test_external_scripts_have_separate_tags_and_existing_files(self):
        root=Path(__file__).resolve().parents[1]/'web'
        page=(root/'index.html').read_text()
        scripts=re.findall(r'<script\b([^>]*)>(.*?)</script>',page,re.S)
        paths=[]
        for attributes,body in scripts:
            match=re.search(r'src="(/[^\"]+)"',attributes)
            self.assertIsNotNone(match)
            self.assertFalse(body.strip(),'External script tags cannot swallow another script element')
            self.assertTrue((root/match.group(1).lstrip('/')).is_file())
            paths.append(match.group(1))
        self.assertIn('/planning.js',paths)
        self.assertLess(paths.index('/purchases.js'),paths.index('/planning.js'))
