"""Maintainer tool: create the release key seed or sign a release's update manifest.

Uses only the RFC 8032 math in `shorekeeper_pet.update_signature`, so `cryptography`
is not needed. The seed is a raw 32-byte file kept off-repo.

    python tools/sign_update.py --generate <seed-file>
    python tools/sign_update.py --key <seed-file> <manifest.json>
"""
import argparse
import base64
import os
import pathlib
import sys

root = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from shorekeeper_pet.update_signature import PUBLIC_KEYS, public_key, sign, verify_manifest


def generate(path):
    target = pathlib.Path(path)
    if target.exists():
        raise SystemExit('Seed file already exists: %s' % target)
    target.parent.mkdir(parents=True, exist_ok=True)
    seed = os.urandom(32)
    with target.open('xb') as out:
        out.write(seed)
    print(target)
    print(public_key(seed).hex())


def sign_manifest(seed_path, manifest, allow_other_key=False):
    seed = pathlib.Path(seed_path).read_bytes()
    public = public_key(seed)
    if not allow_other_key and public not in PUBLIC_KEYS:
        raise SystemExit('This key is not trusted by this version of the pet')
    manifest = pathlib.Path(manifest)
    raw = manifest.read_bytes()
    text = base64.b64encode(sign(raw, seed)).decode('ascii')
    if not allow_other_key:
        verify_manifest(raw, text)
    target = manifest.with_name(manifest.name + '.sig')
    target.write_text(text + '\n', encoding='ascii', newline='\n')
    print(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--generate', metavar='SEED')
    parser.add_argument('--key')
    parser.add_argument('--allow-other-key', action='store_true')
    parser.add_argument('manifest', nargs='?')
    args = parser.parse_args()
    if args.generate:
        generate(args.generate)
    elif args.key and args.manifest:
        sign_manifest(args.key, args.manifest, args.allow_other_key)
    else:
        parser.error('use --generate SEED or --key SEED MANIFEST')
