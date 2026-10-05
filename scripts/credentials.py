"""The Chess-Results login, kept in the operating system's credential store.

One entry serves every host that starts this server — Claude Code, Codex, a
terminal — so the password is stored once and never in a file, a config or a
conversation. It is written by `cli.py login`, which asks for it hidden in the
user's own terminal.

Where it is looked for, first hit wins:

1. CHESS_RESULTS_PNO and CHESS_RESULTS_PASSWORD in the environment — for a host or
   machine without a credential store (CI, a server);
2. on macOS, the login keychain through Apple's `security` tool;
3. elsewhere, the system store through the `keyring` package (Windows Credential
   Manager, Linux Secret Service).

On macOS the entry is written and read by the same program, /usr/bin/security,
which is on the entry's access list, so reading it never shows an authorization
dialog while the login keychain is unlocked (i.e. while the user is logged in).
`keyring` is deliberately not used there: the reader would be the Python binary,
and macOS would ask again after every Python update.

The store holds one generic password under the service "chess-results": the
account is the Chess-Results personal number, the secret the password. Nothing
here ever prints the password.
"""
import os
import platform
import shutil
import subprocess

SERVICE = 'chess-results'


class CredentialError(Exception):
    pass


def _keyring():
    try:
        import keyring
        return keyring
    except ImportError:
        return None


def _security():
    return shutil.which('security') if platform.system() == 'Darwin' else None


def backend():
    """Where credentials are kept on this machine, for messages."""
    if _security():
        return 'macOS Keychain'
    if _keyring():
        return 'system credential store (keyring)'
    return None


def _keychain_account():
    """The personal number stored with the Keychain entry (its account field)."""
    out = subprocess.run([_security(), 'find-generic-password', '-s', SERVICE],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith('"acct"'):
            return line.split('=', 1)[1].strip().strip('"') or None
    return None


def _keychain_password(pno):
    """The stored password. Read with -g rather than -w: -w prints a password with
    non-ASCII characters (umlauts) as bare hex, indistinguishable from a password
    that is hex; -g marks that case as 0x… and is decoded here."""
    out = subprocess.run([_security(), 'find-generic-password', '-s', SERVICE, '-a', pno, '-g'],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    for line in out.stderr.splitlines():
        if line.startswith('password: '):
            value = line[len('password: '):]
            if value.startswith('0x'):
                return bytes.fromhex(value[2:].split()[0]).decode('utf-8')
            if value.startswith('"') and value.endswith('"'):
                return value[1:-1].replace('\\"', '"').replace('\\\\', '\\')
            return value or None
    return None


def load():
    """(personal number, password), or raise CredentialError saying how to set them."""
    pno, password = os.environ.get('CHESS_RESULTS_PNO'), os.environ.get('CHESS_RESULTS_PASSWORD')
    if pno and password:
        return pno, password
    if _security():
        pno = _keychain_account()
        if pno:
            password = _keychain_password(pno)
            if password:
                return pno, password
    elif _keyring():
        kr = _keyring()
        pno = kr.get_password(SERVICE, '__account__')
        password = kr.get_password(SERVICE, pno) if pno else None
        if pno and password:
            return pno, password
    raise CredentialError(
        'No Chess-Results login stored. Run, in your own terminal: '
        'python3 <plugin>/server/cli.py login  (or set CHESS_RESULTS_PNO and CHESS_RESULTS_PASSWORD).')


def store(pno, password):
    """Save the login, replacing any earlier one."""
    if not pno or not password:
        raise CredentialError('Both the personal number and the password are needed.')
    forget()
    if _security():
        # The value goes on stdin through `security -i`, so it never appears in the
        # process list. -T names /usr/bin/security as trusted: the reader is then
        # always the writer, and macOS reads the entry without asking.
        cmd = (f'add-generic-password -U -s {SERVICE} -a {pno} -l "Chess-Results" '
               f'-T {_security()} -w "{_quote(password)}"\n')
        out = subprocess.run([_security(), '-i'], input=cmd, capture_output=True, text=True)
        if out.returncode != 0:
            raise CredentialError('The Keychain refused the entry: ' + (out.stderr.strip() or 'unknown error'))
        return backend()
    kr = _keyring()
    if kr:
        kr.set_password(SERVICE, '__account__', pno)
        kr.set_password(SERVICE, pno, password)
        return backend()
    raise CredentialError('No credential store on this system. Install it with: pip install keyring '
                          '(or set CHESS_RESULTS_PNO and CHESS_RESULTS_PASSWORD).')


def _quote(text):
    return text.replace('\\', '\\\\').replace('"', '\\"')


def forget():
    """Remove a stored login, if there is one."""
    kr = None if _security() else _keyring()
    if kr:
        pno = kr.get_password(SERVICE, '__account__')
        for account in filter(None, (pno, '__account__')):
            try:
                kr.delete_password(SERVICE, account)
            except Exception:
                pass
    elif _security():
        while subprocess.run([_security(), 'delete-generic-password', '-s', SERVICE],
                             capture_output=True).returncode == 0:
            pass


def status():
    """What is configured, without revealing the password."""
    source = 'environment' if os.environ.get('CHESS_RESULTS_PNO') and os.environ.get(
        'CHESS_RESULTS_PASSWORD') else backend()
    try:
        pno, _ = load()
        return dict(stored=True, source=source, account=pno)
    except CredentialError as e:
        return dict(stored=False, source=backend(), hint=str(e))
