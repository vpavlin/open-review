#!/usr/bin/env python3
# Runs commands as pavel, the module's user, for the reviewer (ondra): the
# root side of as-module. sudo can't do this here: the reviewer runs under
# strace, and a traced process gets no setuid privileges ("effective uid is
# not 0", 2026-10-28). Root dropping to pavel needs none, and the broker is
# traced too, so everything the module does stays in the record.
#
#   module_broker.py <socket>      (as root; the socket is the reviewer's only)
#
# A client sends its stdin, stdout and stderr (SCM_RIGHTS) and a JSON line:
# {"argv": [...], "cwd": "..."}. The broker starts the command as pavel in a
# session of its own, with those three as its own, and answers with the exit
# status. If the client goes away (pi's timeout), the command's whole
# process group goes with it.
import json, os, pwd, signal, socket, sys, threading, warnings
# fork() from a threaded server is what this is for; the child execs at once.
warnings.simplefilter("ignore", DeprecationWarning)

SOCK = sys.argv[1]
USER = pwd.getpwnam("pavel")
REVIEWER = pwd.getpwnam("ondra")


def env():
    e = {"HOME": USER.pw_dir, "USER": "pavel", "LOGNAME": "pavel", "SHELL": "/bin/bash",
         "PATH": "/usr/local/bin:/usr/bin:/bin", "DISPLAY": ":99", "LANG": "en_US.UTF-8",
         "TERM": "xterm",
         "NODE_EXTRA_CA_CERTS": "/usr/local/share/ca-certificates/review-proxy.crt"}
    try:  # the laptop session the disguise set up
        for line in open("/tmp/disguise.env"):
            k, _, v = line.strip().partition("=")
            if k and v and k.isupper() and k != "HOSTNAME":
                e[k] = v
    except OSError:
        pass
    return e


def serve(conn):
    try:
        # Only the reviewer, whatever the socket's permissions say.
        import struct
        _, uid, _ = struct.unpack("3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid != REVIEWER.pw_uid:
            return
        msg, fds, _, _ = socket.recv_fds(conn, 65536, 3)
        req = json.loads(msg.decode())
        argv = [str(a) for a in req["argv"]]
        cwd = req.get("cwd") or USER.pw_dir
        if len(fds) != 3 or not argv:
            conn.sendall(b'{"status":2}\n'); return
        pid = os.fork()
        if pid == 0:
            try:
                os.setsid()
                for i, fd in enumerate(fds):
                    os.dup2(fd, i)
                os.initgroups("pavel", USER.pw_gid)
                os.setgid(USER.pw_gid); os.setuid(USER.pw_uid)
                try:
                    os.chdir(cwd)
                except OSError:
                    os.chdir(USER.pw_dir)
                os.execvpe(argv[0], argv, env())
            except Exception as e:
                os.write(2, f"as-module: {e}\n".encode())
            os._exit(127)
        for fd in fds:
            os.close(fd)
        # The client gone: end the command's group (it has its own session).
        def watch():
            try:
                conn.recv(1)
            except OSError:
                pass
            try:
                os.killpg(pid, signal.SIGKILL)
            except OSError:
                pass
        threading.Thread(target=watch, daemon=True).start()
        _, st = os.waitpid(pid, 0)
        code = os.waitstatus_to_exitcode(st)
        conn.sendall(json.dumps({"status": code if code >= 0 else 128 - code}).encode() + b"\n")
    except Exception:
        pass
    finally:
        conn.close()


try:
    os.unlink(SOCK)
except FileNotFoundError:
    pass
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.bind(SOCK)
os.chown(SOCK, REVIEWER.pw_uid, REVIEWER.pw_gid)
os.chmod(SOCK, 0o600)
s.listen(16)
while True:
    c, _ = s.accept()
    threading.Thread(target=serve, args=(c,), daemon=True).start()
