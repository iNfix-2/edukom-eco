import os
import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'edukom.settings')
django.setup()
from django.urls import resolve, reverse, NoReverseMatch

BASE_DIR = Path('.')
TEMPLATE_DIR = BASE_DIR / 'temp'

url_tag_pattern = re.compile(r'{%\s*url\s+[\'"]([^\'"]+)[\'"]')
href_pattern = re.compile(r'href=[\'"]([^\'"]+)[\'"]')

url_tags = []
hardcoded_links = []
empty_links = []

for root, _, files in os.walk(TEMPLATE_DIR):
    for file in files:
        if file.endswith('.html'):
            filepath = Path(root) / file
            rel_path = filepath.relative_to(BASE_DIR)
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            for u in url_tag_pattern.findall(content):
                url_tags.append((u, str(rel_path)))
            for h in href_pattern.findall(content):
                if h in ['#', '', 'javascript:void(0)', 'javascript:;']:
                    empty_links.append((h, str(rel_path)))
                elif '127.0.0.1' in h or 'localhost' in h:
                    hardcoded_links.append((h, str(rel_path)))

print("=== CHECKING URL TAGS VALIDITY ===")
invalid_tags = []
for name, source in url_tags:
    # Some url tags take arguments, check base name
    base_name = name.split()[0]
    try:
        # Check if url name resolves in django reverse
        # If it takes arguments, reverse will fail with NoReverseMatch unless we test
        pass
    except Exception as e:
        pass

print(f"Total url tags found: {len(url_tags)}")
print(f"Unique url names: {len(set(u[0] for u in url_tags))}")

print("\n=== HARDCODED LOCALHOST / 127.0.0.1 LINKS ===")
for h, src in set(hardcoded_links):
    print(f"  {h} in {src}")

print(f"\n=== EMPTY / DEAD PLACEHOLDER LINKS (href='#' or '') ===")
print(f"Total empty/placeholder links: {len(empty_links)}")
for h, src in sorted(set(empty_links))[:15]:
    print(f"  '{h}' in {src}")

print("\n=== CHECKING COMMON URL NAMES ===")
for name in sorted(set(u[0] for u in url_tags)):
    base_name = name.split()[0]
    try:
        # Try simple reverse
        res = reverse(base_name)
        status = f"OK -> {res}"
    except NoReverseMatch as e:
        status = f"REQUIRES_ARGS_OR_INVALID: {e}"
    print(f"  {name:30} : {status}")
