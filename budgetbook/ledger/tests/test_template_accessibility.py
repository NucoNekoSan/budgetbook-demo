from pathlib import Path
import re

from django.conf import settings
from django.test import SimpleTestCase


class LedgerTableAccessibilityTemplateTest(SimpleTestCase):
    def test_ledger_tables_have_captions_and_column_scopes(self):
        template_dir = Path(settings.BASE_DIR) / 'templates' / 'ledger'
        failures: list[str] = []

        for template_path in template_dir.rglob('*.html'):
            template = template_path.read_text(encoding='utf-8')
            rel_path = template_path.relative_to(settings.BASE_DIR)

            for table_match in re.finditer(r'<table\b[^>]*>', template):
                line_no = template.count('\n', 0, table_match.start()) + 1
                before_thead = template[table_match.end():].split('<thead', 1)[0]
                if '<caption' not in before_thead:
                    failures.append(f'{rel_path}:{line_no} table missing caption')

            for th_match in re.finditer(r'<th\b(?![^>]*\bscope=)[^>]*>', template):
                line_no = template.count('\n', 0, th_match.start()) + 1
                failures.append(f'{rel_path}:{line_no} th missing scope')

        self.assertEqual(failures, [])
